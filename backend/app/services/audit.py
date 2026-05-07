from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def audit(
    db: Session,
    action: str,
    entity_type: str,
    entity_id: str | int | None = None,
    admin_id: int | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    db.add(
        AuditLog(
            admin_id=admin_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            metadata_=metadata or {},
            ip_address=ip_address,
        )
    )
