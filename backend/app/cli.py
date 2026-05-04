import argparse
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.security import hash_password, new_totp_secret
from app.db.session import SessionLocal, engine
from app.models import Admin, AdminRole, Base
from app.services.access_profiles import seed_default_access_profiles


def seed_admin(email: str, password: str, enable_totp: bool) -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        admin = db.scalar(select(Admin).where(Admin.email == email))
        if admin:
            print(f"Admin already exists: {email}")
            return
        admin = Admin(
            email=email,
            password_hash=hash_password(password),
            role=AdminRole.super_admin.value,
            totp_secret=new_totp_secret() if enable_totp else None,
            totp_enabled=enable_totp,
            totp_required=enable_totp,
            totp_confirmed_at=datetime.now(timezone.utc) if enable_totp else None,
        )
        db.add(admin)
        seed_default_access_profiles(db)
        db.commit()
        print(f"Created super admin: {email}")
        if admin.totp_secret:
            print(f"TOTP secret: {admin.totp_secret}")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser("AKFA management CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed-admin")
    seed.add_argument("--email", required=True)
    seed.add_argument("--password", required=True)
    seed.add_argument("--enable-totp", action="store_true")
    args = parser.parse_args()
    if args.command == "seed-admin":
        seed_admin(args.email, args.password, args.enable_totp)


if __name__ == "__main__":
    main()
