import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any

from sqlalchemy import DateTime, inspect, select, text
from sqlalchemy.orm import Session

from app.models import (
    AccessProfile,
    Admin,
    AppSetting,
    AuditLog,
    Department,
    TrafficSnapshot,
    UserNodeTraffic,
    VpnUser,
    VpnUserDevice,
    VpnUserNode,
    VpsNode,
)
from app.services.xray_config import render_server_config

BACKUP_VERSION = 1
APP_NAME = "AKFA"

EXPORT_MODELS = [
    Admin,
    AppSetting,
    AccessProfile,
    Department,
    VpsNode,
    VpnUser,
    VpnUserDevice,
    VpnUserNode,
    UserNodeTraffic,
    TrafficSnapshot,
    AuditLog,
]

EXPORT_FILES = {
    "admins": Admin,
    "app_settings": AppSetting,
    "profiles": AccessProfile,
    "departments": Department,
    "nodes": VpsNode,
    "users": VpnUser,
    "devices": VpnUserDevice,
    "user_nodes": VpnUserNode,
    "user_node_traffic": UserNodeTraffic,
    "traffic_snapshots": TrafficSnapshot,
    "audit_logs": AuditLog,
}


def build_backup_archive(db: Session) -> tuple[bytes, str]:
    created_at = datetime.now(timezone.utc)
    data = {
        name: [_serialize_row(item) for item in db.scalars(select(model)).all()]
        for name, model in EXPORT_FILES.items()
    }
    counts = {
        "users": len(data["users"]),
        "nodes": len(data["nodes"]),
        "profiles": len(data["profiles"]),
        "departments": len(data["departments"]),
    }
    manifest = {
        "app": APP_NAME,
        "backup_version": BACKUP_VERSION,
        "created_at": created_at.isoformat(),
        "app_version": "0.1.0",
        "schema_version": _alembic_revision(db),
        "counts": counts,
        "warning": "Архив содержит чувствительные данные: подписки, ключи Reality и параметры серверов.",
    }

    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        _add_json(archive, "manifest.json", manifest)
        _add_json(archive, "database.json", data)
        _add_json(archive, "settings.json", {"exported_env": False})
        _add_text(
            archive,
            "README.txt",
            "AKFA backup archive. Store it securely: it contains subscription tokens, node keys and server parameters.\n",
        )
        users = db.scalars(select(VpnUser)).all()
        for node in db.scalars(select(VpsNode)).all():
            try:
                config = render_server_config(node, users)
            except Exception as exc:
                config = json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2)
            _add_text(archive, f"xray-configs/node-{node.id}.json", config)

    filename = f"akfa-backup-{created_at.strftime('%Y%m%d-%H%M%S')}.tar.gz"
    return buffer.getvalue(), filename


def restore_backup_archive(db: Session, raw: bytes) -> dict[str, int]:
    members = _read_archive(raw)
    manifest = _read_json_member(members, "manifest.json")
    if manifest.get("app") != APP_NAME:
        raise ValueError("Архив не является backup AKFA")
    if manifest.get("backup_version") != BACKUP_VERSION:
        raise ValueError("Версия backup не поддерживается")
    database = _read_json_member(members, "database.json")
    if not isinstance(database, dict):
        raise ValueError("database.json должен быть объектом")

    restored: dict[str, int] = {}
    with db.begin_nested():
        for model in reversed(EXPORT_MODELS):
            db.execute(model.__table__.delete())
        for name, model in EXPORT_FILES.items():
            rows = database.get(name, [])
            if not isinstance(rows, list):
                raise ValueError(f"{name}: ожидается список")
            values = [_deserialize_row(model, row) for row in rows]
            if values:
                db.execute(model.__table__.insert(), values)
            restored[name] = len(values)
    db.flush()
    _reset_postgres_sequences(db)
    return restored


def _serialize_row(item: object) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for column in item.__table__.columns:
        attr_name = "metadata_" if column.name == "metadata" and hasattr(item, "metadata_") else column.key
        value = getattr(item, attr_name)
        if isinstance(value, datetime):
            value = value.isoformat()
        row[column.name] = value
    return row


def _deserialize_row(model: type, row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError(f"{model.__tablename__}: строка должна быть объектом")
    columns = {column.name: column for column in model.__table__.columns}
    result: dict[str, Any] = {}
    for key, value in row.items():
        column = columns.get(key)
        if column is None:
            continue
        if value is not None and isinstance(column.type, DateTime) and isinstance(value, str):
            value = datetime.fromisoformat(value)
        result["metadata_" if column.name == "metadata" else column.key] = value
    return result


def _read_archive(raw: bytes) -> dict[str, bytes]:
    members: dict[str, bytes] = {}
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            for member in archive.getmembers():
                path = PurePosixPath(member.name)
                if member.isdir():
                    continue
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("Архив содержит небезопасный путь")
                file_obj = archive.extractfile(member)
                if file_obj:
                    members[member.name] = file_obj.read()
    except tarfile.TarError as exc:
        raise ValueError("Архив должен быть .tar.gz") from exc
    return members


def _read_json_member(members: dict[str, bytes], name: str) -> Any:
    raw = members.get(name)
    if raw is None:
        raise ValueError(f"В архиве отсутствует {name}")
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{name} содержит невалидный JSON") from exc


def _add_json(archive: tarfile.TarFile, name: str, payload: Any) -> None:
    _add_text(archive, name, json.dumps(payload, ensure_ascii=False, indent=2))


def _add_text(archive: tarfile.TarFile, name: str, value: str) -> None:
    raw = value.encode("utf-8")
    info = tarfile.TarInfo(name)
    info.size = len(raw)
    archive.addfile(info, io.BytesIO(raw))


def _alembic_revision(db: Session) -> str | None:
    try:
        return db.execute(text("select version_num from alembic_version")).scalar_one_or_none()
    except Exception:
        return None


def _reset_postgres_sequences(db: Session) -> None:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    inspector = inspect(db.bind)
    for model in EXPORT_MODELS:
        table = model.__tablename__
        pk_columns = [column.name for column in model.__table__.primary_key.columns]
        if pk_columns != ["id"]:
            continue
        sequence = db.execute(text("select pg_get_serial_sequence(:table_name, 'id')"), {"table_name": table}).scalar()
        if not sequence:
            continue
        max_id = db.execute(text(f"select coalesce(max(id), 1) from {table}")).scalar() or 1
        if table in inspector.get_table_names():
            db.execute(text("select setval(:sequence, :value, true)"), {"sequence": sequence, "value": max_id})
