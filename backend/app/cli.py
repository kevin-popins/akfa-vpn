import argparse
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.security import decrypt_secret, encrypt_secret, hash_password, new_totp_secret
from app.db.session import SessionLocal
from app.models import Admin, AdminRole
from app.services.access_profiles import seed_default_access_profiles


def seed_admin(email: str, password: str, enable_totp: bool, reset_password: bool) -> None:
    db = SessionLocal()
    try:
        admin = db.scalar(select(Admin).where(Admin.email == email))
        if admin:
            if reset_password:
                admin.password_hash = hash_password(password)
                admin.role = AdminRole.super_admin.value
                admin.is_active = True
                if enable_totp and not admin.totp_enabled:
                    admin.totp_secret = None
                    admin.totp_secret_encrypted = encrypt_secret(new_totp_secret())
                    admin.totp_enabled = True
                    admin.totp_required = True
                    admin.totp_confirmed_at = datetime.now(timezone.utc)
                seed_default_access_profiles(db)
                db.commit()
                print(f"Updated super admin: {email}")
            else:
                print(f"Admin already exists: {email}")
            return
        totp_secret = new_totp_secret() if enable_totp else None
        admin = Admin(
            email=email,
            password_hash=hash_password(password),
            role=AdminRole.super_admin.value,
            totp_secret=None,
            totp_secret_encrypted=encrypt_secret(totp_secret) if totp_secret else None,
            totp_enabled=enable_totp,
            totp_required=enable_totp,
            totp_confirmed_at=datetime.now(timezone.utc) if enable_totp else None,
        )
        db.add(admin)
        seed_default_access_profiles(db)
        db.commit()
        print(f"Created super admin: {email}")
        secret = decrypt_secret(admin.totp_secret_encrypted)
        if secret:
            print(f"TOTP secret: {secret}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser("AKFA management CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed-admin")
    seed.add_argument("--email", required=True)
    seed.add_argument("--password")
    seed.add_argument("--password-env")
    seed.add_argument("--reset-password", action="store_true")
    seed.add_argument("--enable-totp", action="store_true")
    args = parser.parse_args()
    if args.command == "seed-admin":
        password = args.password
        if args.password_env:
            import os

            password = os.environ.get(args.password_env)
        if not password:
            raise SystemExit("Password is required. Use --password or --password-env.")
        seed_admin(args.email, password, args.enable_totp, args.reset_password)


if __name__ == "__main__":
    main()
