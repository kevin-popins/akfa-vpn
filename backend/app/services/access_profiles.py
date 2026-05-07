from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import DEFAULT_ACCESS_PROFILE_DEFINITIONS, LEGACY_RU_DIRECT_PROFILE_NAMES
from app.models import AccessProfile


def seed_default_access_profiles(db: Session) -> list[AccessProfile]:
    profiles: list[AccessProfile] = []
    for source_definition in DEFAULT_ACCESS_PROFILE_DEFINITIONS:
        definition = {
            key: value.copy() if isinstance(value, list) else value
            for key, value in source_definition.items()
        }
        profile = db.scalar(select(AccessProfile).where(AccessProfile.name == definition["name"]))
        if not profile and definition["name"] == "Российские сервисы напрямую":
            profile = db.scalar(
                select(AccessProfile).where(AccessProfile.name.in_(LEGACY_RU_DIRECT_PROFILE_NAMES))
            )
            if profile:
                profile.name = definition["name"]
        if not profile:
            profile = AccessProfile(**definition)
            db.add(profile)
        else:
            for key, value in definition.items():
                setattr(profile, key, value)
        profiles.append(profile)
    db.flush()
    return profiles
