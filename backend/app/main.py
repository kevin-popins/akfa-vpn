from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.entities import public_router, router as admin_router
from app.core.config import settings
from app.services.scheduler import start_scheduler

app = FastAPI(title="AKFA API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(public_router)


@app.on_event("startup")
async def startup() -> None:
    if settings.environment != "test":
        start_scheduler()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "akfa"}

