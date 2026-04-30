from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.session import SessionLocal
from app.services.traffic import enforce_expiration_and_limits

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    if scheduler.running:
        return

    def enforce() -> None:
        db = SessionLocal()
        try:
            enforce_expiration_and_limits(db)
        finally:
            db.close()

    scheduler.add_job(enforce, "interval", minutes=5, id="enforce-user-limits", replace_existing=True)
    scheduler.start()

