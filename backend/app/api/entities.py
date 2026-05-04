import asyncio
import csv
import io
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import current_admin, require_write
from app.core.security import encrypt_secret
from app.db.session import get_db
from app.models import (
    AccessProfile,
    Admin,
    AuditLog,
    Department,
    NodeStatus,
    TrafficSnapshot,
    UserNodeTraffic,
    UserStatus,
    DeviceStatus,
    VpnUserDevice,
    VpnUserNode,
    VpnUser,
    VpsNode,
)
from app.schemas.common import AuditLogRead, DashboardStats, Message
from app.schemas.entities import (
    AccessProfileCreate,
    AccessProfileRead,
    BulkImportResult,
    DepartmentCreate,
    DepartmentRead,
    NodeCreate,
    NodeActionJobAccepted,
    NodeActionJobRead,
    NodeMetricsRead,
    NodeRead,
    NodeUpdate,
    RestoreSummary,
    SniCheckRequest,
    SniCheckResponse,
    SshCheckResponse,
    TrafficSnapshotRead,
    TrafficUserRead,
    PublicConnectRead,
    VpnUserDeviceRead,
    VpnUserDeviceUpdate,
    XrayImportRequest,
    XrayProbeRequest,
    XrayProbeResponse,
    VpnUserCreate,
    VpnUserRead,
)
from app.services.access_profiles import seed_default_access_profiles
from app.services.reality import check_sni_target, ensure_reality_credentials
from app.services.audit import audit
from app.services.backup import build_backup_archive, restore_backup_archive
from app.services.node_action_jobs import get_job, start_install_job
from app.services.config_apply import (
    APPLY_FAILED,
    ConfigApplyRequiredError,
    ConfigApplyService,
    ConfigApplySummary,
    NodeApplyResult,
    affected_node_ids_for_user,
    apply_config_for_user,
)
from app.services.server_metrics import collect_nodes_metrics
from app.services.ssh_installer import XrayInstaller
from app.services.hwid import apply_device_metadata, build_display_name, compute_hwid_context
from app.services.subscriptions import subscription_payload, subscription_response, validate_subscription_user
from app.services.traffic import (
    collect_traffic as collect_traffic_stats,
    enforce_expiration_and_limits,
    traffic_overview,
)
from app.services.xray_config import render_server_config
from app.services.xray_probe import import_probe_to_node, probe_xray

router = APIRouter(prefix="/admin", tags=["admin"])
public_router = APIRouter(tags=["subscriptions"])
ModelT = TypeVar("ModelT")
logger = logging.getLogger(__name__)
IDEMPOTENCY_TTL_SECONDS = 300
_create_user_idempotency_cache: dict[str, dict[str, Any]] = {}
_create_user_idempotency_locks: dict[str, asyncio.Lock] = {}


def _get_or_404(db: Session, model: type[ModelT], item_id: int) -> ModelT:
    item = db.get(model, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return item


def attach_apply_status(item: object, summary: ConfigApplySummary | None) -> object:
    if summary is not None:
        setattr(item, "apply_status", summary.as_dict())
        errors = [result.error for result in summary.results if result.error and (not result.ok or result.status == "skipped")]
        if errors:
            setattr(item, "apply_error", "; ".join(errors))
    return item


def apply_warning(prefix: str, summary: ConfigApplySummary | None) -> str | None:
    if not summary or summary.failed == 0:
        return None
    failed_nodes = ", ".join(result.node_name for result in summary.results if not result.ok)
    return f"{prefix}, но конфиг не применился на нодах: {failed_nodes}"


def default_allowed_node_ids(db: Session) -> list[int]:
    return list(db.scalars(select(VpsNode.id).where(VpsNode.status == NodeStatus.online.value).order_by(VpsNode.name, VpsNode.id)))


def normalize_allowed_node_ids(db: Session, allowed_node_ids: list[int], status: str) -> list[int]:
    ids = sorted(set(allowed_node_ids or []))
    if not ids and status == UserStatus.active.value:
        ids = default_allowed_node_ids(db)
    existing_ids = set(db.scalars(select(VpsNode.id).where(VpsNode.id.in_(ids))).all()) if ids else set()
    return [node_id for node_id in ids if node_id in existing_ids]


def has_online_nodes(db: Session) -> bool:
    return bool(db.scalar(select(func.count(VpsNode.id)).where(VpsNode.status == NodeStatus.online.value)))


def set_user_node_access(db: Session, user: VpnUser, allowed_node_ids: list[int], primary_node_id: int | None) -> tuple[set[int], set[int]]:
    old_ids = set(user.allowed_node_ids or [])
    new_ids = set(allowed_node_ids)
    user.node_links.clear()
    for node_id in sorted(new_ids):
        user.node_links.append(VpnUserNode(node_id=node_id))
    user.primary_node_id = primary_node_id if primary_node_id in new_ids else (min(new_ids) if new_ids else None)
    db.flush()
    return old_ids, new_ids


async def auto_apply_after_change(
    db: Session,
    admin: Admin,
    node_ids: set[int] | None,
    reason: str,
) -> ConfigApplySummary:
    return await ConfigApplyService(db, admin.id).apply_to_nodes(node_ids, reason=reason)


def failed_apply_summary_from_exception(db: Session, node_ids: set[int] | None, error: Exception) -> ConfigApplySummary:
    ids = set(node_ids or [])
    nodes = list(db.scalars(select(VpsNode).where(VpsNode.id.in_(ids)).order_by(VpsNode.name, VpsNode.id))) if ids else []
    message = str(error) or "Не удалось применить конфигурацию на сервер"
    applied_at = datetime.now(timezone.utc).isoformat()
    results = [
        NodeApplyResult(
            node_id=node.id,
            node_name=node.name,
            ok=False,
            status=APPLY_FAILED,
            error=message,
            applied_at=applied_at,
        )
        for node in nodes
    ]
    if not results:
        results.append(
            NodeApplyResult(
                node_id=0,
                node_name="Xray config",
                ok=False,
                status=APPLY_FAILED,
                error=message,
                applied_at=applied_at,
            )
        )
    return ConfigApplySummary(
        ok=False,
        attempted=len(results),
        succeeded=0,
        failed=len(results),
        skipped=0,
        results=results,
    )


async def safe_auto_apply_after_change(
    db: Session,
    admin: Admin,
    node_ids: set[int] | None,
    reason: str,
) -> ConfigApplySummary:
    try:
        return await auto_apply_after_change(db, admin, node_ids, reason)
    except Exception as exc:
        logger.exception(
            "auto apply failed with unhandled exception admin_id=%s reason=%s nodes=%s",
            admin.id,
            reason,
            sorted(node_ids or []),
        )
        return failed_apply_summary_from_exception(db, node_ids, exc)


def request_idempotency_key(request: Request) -> str | None:
    value = (request.headers.get("X-Idempotency-Key") or request.headers.get("X-Request-ID") or "").strip()
    if not value:
        return None
    return value[:120]


def cached_created_user(db: Session, key: str) -> VpnUser | None:
    entry = _create_user_idempotency_cache.get(key)
    if not entry:
        return None
    if time.monotonic() - float(entry.get("stored_at", 0)) > IDEMPOTENCY_TTL_SECONDS:
        _create_user_idempotency_cache.pop(key, None)
        _create_user_idempotency_locks.pop(key, None)
        return None
    user = db.get(VpnUser, int(entry["user_id"]))
    if not user:
        return None
    if entry.get("apply_status"):
        setattr(user, "apply_status", entry["apply_status"])
    if entry.get("apply_error"):
        setattr(user, "apply_error", entry["apply_error"])
    return user


def cache_created_user(key: str | None, user: VpnUser, summary: ConfigApplySummary | None) -> None:
    if not key:
        return
    apply_status = summary.as_dict() if summary else None
    errors = []
    if summary:
        errors = [result.error for result in summary.results if result.error and (not result.ok or result.status == "skipped")]
    _create_user_idempotency_cache[key] = {
        "user_id": user.id,
        "username": user.username,
        "apply_status": apply_status,
        "apply_error": "; ".join(errors) if errors else None,
        "stored_at": time.monotonic(),
    }


@router.get("/dashboard", response_model=DashboardStats)
def dashboard(_: Admin = Depends(current_admin), db: Session = Depends(get_db)) -> DashboardStats:
    visible_users = VpnUser.status != UserStatus.deleted.value
    return DashboardStats(
        nodes_total=db.scalar(select(func.count(VpsNode.id))) or 0,
        nodes_online=db.scalar(select(func.count(VpsNode.id)).where(VpsNode.status == NodeStatus.online.value)) or 0,
        users_total=db.scalar(select(func.count(VpnUser.id)).where(visible_users)) or 0,
        users_active=db.scalar(select(func.count(VpnUser.id)).where(VpnUser.status == UserStatus.active.value)) or 0,
        traffic_total_bytes=db.scalar(select(func.coalesce(func.sum(VpnUser.used_total_bytes), 0)).where(visible_users)) or 0,
    )


@router.get("/access-profiles", response_model=list[AccessProfileRead])
def list_profiles(_: Admin = Depends(current_admin), db: Session = Depends(get_db)) -> list[AccessProfile]:
    return list(db.scalars(select(AccessProfile).order_by(AccessProfile.name)))


@router.post("/access-profiles", response_model=AccessProfileRead)
def create_profile(payload: AccessProfileCreate, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> AccessProfile:
    profile = AccessProfile(**payload.model_dump())
    db.add(profile)
    db.flush()
    audit(db, "create", "access_profile", profile.id, admin.id)
    db.commit()
    return profile


@router.put("/access-profiles/{profile_id}", response_model=AccessProfileRead)
async def update_profile(profile_id: int, payload: AccessProfileCreate, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> AccessProfile:
    profile = _get_or_404(db, AccessProfile, profile_id)
    affected_ids = set(
        db.scalars(
            select(VpnUserNode.node_id)
            .join(VpnUser, VpnUser.id == VpnUserNode.vpn_user_id)
            .where(
                VpnUser.access_profile_id == profile.id,
                VpnUser.status != UserStatus.deleted.value,
            )
        )
    )
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    audit(db, "update", "access_profile", profile.id, admin.id)
    db.flush()
    summary = await auto_apply_after_change(db, admin, affected_ids or None, "auto_apply_after_profile_update")
    db.commit()
    return attach_apply_status(profile, summary)


@router.delete("/access-profiles/{profile_id}", response_model=Message)
def delete_profile(profile_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> Message:
    profile = _get_or_404(db, AccessProfile, profile_id)
    used_by_users = db.scalar(
        select(func.count(VpnUser.id)).where(
            VpnUser.access_profile_id == profile.id,
            VpnUser.status != UserStatus.deleted.value,
        )
    ) or 0
    used_by_departments = db.scalar(select(func.count(Department.id)).where(Department.default_access_profile_id == profile.id)) or 0
    if used_by_users or used_by_departments:
        raise HTTPException(status_code=409, detail="Нельзя удалить профиль: он используется")
    db.delete(profile)
    audit(db, "delete", "access_profile", profile_id, admin.id)
    db.commit()
    return Message(message="Профиль удален")


@router.get("/departments", response_model=list[DepartmentRead])
def list_departments(_: Admin = Depends(current_admin), db: Session = Depends(get_db)) -> list[Department]:
    return list(db.scalars(select(Department).order_by(Department.name)))


@router.post("/departments", response_model=DepartmentRead)
def create_department(payload: DepartmentCreate, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> Department:
    department = Department(**payload.model_dump())
    db.add(department)
    db.flush()
    audit(db, "create", "department", department.id, admin.id)
    db.commit()
    return department


@router.get("/departments/{department_id}", response_model=DepartmentRead)
def get_department(department_id: int, _: Admin = Depends(current_admin), db: Session = Depends(get_db)) -> Department:
    return _get_or_404(db, Department, department_id)


@router.put("/departments/{department_id}", response_model=DepartmentRead)
def update_department(department_id: int, payload: DepartmentCreate, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> Department:
    department = _get_or_404(db, Department, department_id)
    for key, value in payload.model_dump().items():
        setattr(department, key, value)
    audit(db, "update", "department", department.id, admin.id)
    db.commit()
    return department


@router.get("/nodes", response_model=list[NodeRead])
def list_nodes(_: Admin = Depends(current_admin), db: Session = Depends(get_db)) -> list[VpsNode]:
    return list(db.scalars(select(VpsNode).order_by(VpsNode.created_at.desc())))


@router.get("/nodes/metrics", response_model=list[NodeMetricsRead])
async def node_metrics(_: Admin = Depends(current_admin), db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    nodes = list(db.scalars(select(VpsNode).order_by(VpsNode.created_at.desc())))
    return await collect_nodes_metrics(db, nodes)


@router.post("/nodes", response_model=NodeRead)
def create_node(payload: NodeCreate, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> VpsNode:
    data = payload.model_dump(exclude={"ssh_password", "private_key"})
    data["public_host"] = payload.public_host or payload.ip_address
    node = VpsNode(
        **data,
        encrypted_ssh_password=encrypt_secret(payload.ssh_password),
        encrypted_private_key=encrypt_secret(payload.private_key),
    )
    ensure_reality_credentials(node)
    db.add(node)
    db.flush()
    audit(db, "create", "vps_node", node.id, admin.id)
    db.commit()
    return node


@router.get("/nodes/{node_id}", response_model=NodeRead)
def get_node(node_id: int, _: Admin = Depends(current_admin), db: Session = Depends(get_db)) -> VpsNode:
    return _get_or_404(db, VpsNode, node_id)


@router.post("/nodes/{node_id}/check", response_model=NodeRead)
async def check_node(node_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> VpsNode:
    node = _get_or_404(db, VpsNode, node_id)
    result = await XrayInstaller(node).check_connection()
    node.install_log = result.logs
    node.status = NodeStatus.draft.value if result.ok else NodeStatus.failed.value
    node.last_check_at = datetime.now(timezone.utc)
    audit(db, "check_connection", "vps_node", node.id, admin.id)
    db.commit()
    return node


@router.post("/tools/check-ssh", response_model=SshCheckResponse)
async def check_ssh(payload: NodeCreate, _: Admin = Depends(require_write)) -> SshCheckResponse:
    data = payload.model_dump(exclude={"ssh_password", "private_key"})
    data["public_host"] = payload.public_host or payload.ip_address
    node = VpsNode(
        **data,
        encrypted_ssh_password=encrypt_secret(payload.ssh_password),
        encrypted_private_key=encrypt_secret(payload.private_key),
    )
    result = await XrayInstaller(node).check_connection()
    return SshCheckResponse(ok=result.ok, logs=result.logs)


@router.post("/nodes/{node_id}/dry-run", response_model=NodeRead)
async def dry_run_node(node_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> VpsNode:
    node = _get_or_404(db, VpsNode, node_id)
    ensure_reality_credentials(node)
    users = list(db.scalars(select(VpnUser)))
    result = await XrayInstaller(node, users).dry_run()
    node.install_log = result.logs
    node.short_id = result.short_id or node.short_id
    node.reality_private_key = result.reality_private_key or node.reality_private_key
    node.reality_public_key = result.reality_public_key or node.reality_public_key
    audit(db, "dry_run_install", "vps_node", node.id, admin.id)
    db.commit()
    return node


@router.post("/nodes/{node_id}/verify", response_model=NodeRead)
async def verify_node(node_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> VpsNode:
    node = _get_or_404(db, VpsNode, node_id)
    result = await XrayInstaller(node).verify()
    node.install_log = result.logs
    node.status = NodeStatus.online.value if result.ok else NodeStatus.failed.value
    node.xray_installed = bool(result.ok)
    node.last_check_at = datetime.now(timezone.utc)
    audit(db, "verify_xray", "vps_node", node.id, admin.id)
    db.commit()
    return node


@router.post("/nodes/{node_id}/install", response_model=NodeActionJobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def install_node(node_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> dict[str, str]:
    node = _get_or_404(db, VpsNode, node_id)
    ensure_reality_credentials(node)
    node.status = NodeStatus.installing.value
    db.commit()
    job = start_install_job(node.id, admin.id)
    return {"job_id": job.job_id, "status": job.status, "current_step": job.current_step}


@router.get("/node-actions/{job_id}", response_model=NodeActionJobRead)
def get_node_action_job(job_id: str, _: Admin = Depends(current_admin)) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return job.as_dict()


@router.post("/nodes/probe", response_model=XrayProbeResponse)
async def probe_new_node(payload: XrayProbeRequest, _: Admin = Depends(require_write)) -> XrayProbeResponse:
    data = payload.model_dump(exclude={"ssh_password", "private_key"})
    data["public_host"] = payload.public_host or payload.ip_address
    node = VpsNode(
        **data,
        encrypted_ssh_password=encrypt_secret(payload.ssh_password),
        encrypted_private_key=encrypt_secret(payload.private_key),
    )
    return await probe_xray(node)


@router.post("/nodes/{node_id}/probe", response_model=XrayProbeResponse)
async def probe_existing_node(node_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> XrayProbeResponse:
    node = _get_or_404(db, VpsNode, node_id)
    result = await probe_xray(node)
    node.install_log = result.logs
    node.last_check_at = datetime.now(timezone.utc)
    audit(db, "probe_xray", "vps_node", node.id, admin.id)
    db.commit()
    return result


@router.post("/nodes/{node_id}/import-xray", response_model=NodeRead)
async def import_existing_xray(
    node_id: int,
    payload: XrayImportRequest,
    admin: Admin = Depends(require_write),
    db: Session = Depends(get_db),
) -> VpsNode:
    node = _get_or_404(db, VpsNode, node_id)
    probe = payload.probe or await probe_xray(node)
    try:
        import_probe_to_node(node, probe, payload.public_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit(db, "import_xray", "vps_node", node.id, admin.id)
    db.flush()
    summary = await auto_apply_after_change(db, admin, {node.id}, "auto_apply_after_xray_import")
    db.commit()
    return attach_apply_status(node, summary)


@router.post("/nodes/{node_id}/apply-config", response_model=NodeRead)
async def apply_node_config(node_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> VpsNode:
    node = _get_or_404(db, VpsNode, node_id)
    ensure_reality_credentials(node)
    summary = await ConfigApplyService(db, admin.id).apply_to_nodes(
        {node.id},
        reason="apply_xray_config",
        include_uninstalled=True,
        allow_non_online=True,
    )
    audit(db, "apply_xray_config", "vps_node", node.id, admin.id)
    db.commit()
    if not summary.ok:
        raise HTTPException(status_code=502, detail="Конфиг Xray не удалось применить")
    return attach_apply_status(node, summary)


@router.put("/nodes/{node_id}", response_model=NodeRead)
async def update_node(node_id: int, payload: NodeUpdate, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> VpsNode:
    node = _get_or_404(db, VpsNode, node_id)
    for key, value in payload.model_dump().items():
        setattr(node, key, value)
    node.public_host = node.public_host or node.ip_address
    ensure_reality_credentials(node)
    audit(db, "update", "vps_node", node.id, admin.id)
    db.flush()
    summary = await auto_apply_after_change(db, admin, {node.id}, "auto_apply_after_node_update")
    db.commit()
    return attach_apply_status(node, summary)


@router.get("/nodes/{node_id}/config-preview")
def node_config_preview(node_id: int, _: Admin = Depends(current_admin), db: Session = Depends(get_db)) -> Response:
    node = _get_or_404(db, VpsNode, node_id)
    ensure_reality_credentials(node)
    users = list(db.scalars(select(VpnUser)))
    for user in users:
        db.expire(user, ["devices", "node_links"])
    return Response(render_server_config(node, users), media_type="application/json")


@router.post("/tools/check-sni", response_model=SniCheckResponse)
def check_sni(payload: SniCheckRequest, _: Admin = Depends(require_write)) -> SniCheckResponse:
    return SniCheckResponse(**check_sni_target(payload.sni).__dict__)


@router.delete("/nodes/{node_id}", response_model=Message)
def delete_node(node_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> Message:
    node = _get_or_404(db, VpsNode, node_id)
    db.delete(node)
    audit(db, "delete", "vps_node", node_id, admin.id)
    db.commit()
    return Message(message="Сервер удален из AKFA. Удаление не трогает Xray на VPS.")


@router.get("/users", response_model=list[VpnUserRead])
def list_users(_: Admin = Depends(current_admin), db: Session = Depends(get_db)) -> list[VpnUser]:
    enforce_expiration_and_limits(db)
    return list(
        db.scalars(
            select(VpnUser)
            .where(VpnUser.status != UserStatus.deleted.value)
            .order_by(VpnUser.created_at.desc())
        )
    )


@router.post("/users", response_model=VpnUserRead)
async def create_user(
    payload: VpnUserCreate,
    request: Request,
    admin: Admin = Depends(require_write),
    db: Session = Depends(get_db),
) -> VpnUser:
    idempotency_key = request_idempotency_key(request)
    if idempotency_key:
        cached = cached_created_user(db, idempotency_key)
        if cached:
            logger.info(
                "create user idempotent cache hit before lock admin_id=%s username=%s request_id=%s user_id=%s",
                admin.id,
                payload.username,
                idempotency_key,
                cached.id,
            )
            return cached
        lock = _create_user_idempotency_locks.setdefault(idempotency_key, asyncio.Lock())
        async with lock:
            cached = cached_created_user(db, idempotency_key)
            if cached:
                logger.info(
                    "create user idempotent cache hit after lock admin_id=%s username=%s request_id=%s user_id=%s",
                    admin.id,
                    payload.username,
                    idempotency_key,
                    cached.id,
                )
                return cached
            return await create_user_unlocked(payload, admin, db, idempotency_key)
    return await create_user_unlocked(payload, admin, db, None)


async def create_user_unlocked(
    payload: VpnUserCreate,
    admin: Admin,
    db: Session,
    idempotency_key: str | None,
) -> VpnUser:
    logger.info(
        "create user start admin_id=%s username=%s request_id=%s status=%s department_id=%s profile_id=%s nodes=%s primary_node_id=%s",
        admin.id,
        payload.username,
        idempotency_key,
        payload.status,
        payload.department_id,
        payload.access_profile_id,
        payload.allowed_node_ids,
        payload.primary_node_id,
    )
    if db.scalar(select(VpnUser.id).where(VpnUser.username == payload.username)):
        logger.info("create user validation failed duplicate_username admin_id=%s username=%s request_id=%s", admin.id, payload.username, idempotency_key)
        raise HTTPException(status_code=409, detail="Пользователь с таким логином уже существует")
    expires_at = payload.expires_at
    profile = db.get(AccessProfile, payload.access_profile_id) if payload.access_profile_id else None
    if not expires_at and profile and profile.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=profile.expires_in_days)
    allowed_node_ids = normalize_allowed_node_ids(db, payload.allowed_node_ids, payload.status)
    if payload.status == UserStatus.active.value and not allowed_node_ids and has_online_nodes(db):
        raise HTTPException(status_code=422, detail="Активному пользователю нужен хотя бы один доступный сервер")
    if payload.primary_node_id and payload.primary_node_id not in allowed_node_ids:
        raise HTTPException(status_code=422, detail="Основной сервер должен входить в доступные серверы")
    data = payload.model_dump(exclude={"expires_at", "traffic_limit_bytes", "allowed_node_ids", "primary_node_id"})
    user = VpnUser(
        **data,
        expires_at=expires_at,
        uuid=str(uuid.uuid4()),
        subscription_token=secrets.token_urlsafe(32),
        traffic_limit_bytes=payload.traffic_limit_bytes or (profile.traffic_limit_bytes if profile else None),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        logger.exception("create user flush failed admin_id=%s username=%s request_id=%s", admin.id, payload.username, idempotency_key)
        raise HTTPException(status_code=409, detail="Пользователь с таким логином уже существует") from exc
    logger.info("create user db flushed admin_id=%s user_id=%s username=%s request_id=%s", admin.id, user.id, user.username, idempotency_key)
    _, new_ids = set_user_node_access(db, user, allowed_node_ids, payload.primary_node_id)
    audit(db, "create", "vpn_user", user.id, admin.id)
    summary = await safe_auto_apply_after_change(db, admin, new_ids, "auto_apply_after_user_create")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.exception("create user commit failed admin_id=%s user_id=%s username=%s request_id=%s", admin.id, user.id, payload.username, idempotency_key)
        raise HTTPException(status_code=409, detail="Пользователь с таким логином уже существует") from exc
    cache_created_user(idempotency_key, user, summary)
    if summary.ok:
        logger.info(
            "create user response success admin_id=%s user_id=%s username=%s request_id=%s apply_attempted=%s apply_skipped=%s",
            admin.id,
            user.id,
            user.username,
            idempotency_key,
            summary.attempted,
            summary.skipped,
        )
    else:
        logger.warning(
            "create user response partial_success admin_id=%s user_id=%s username=%s request_id=%s apply_failed=%s apply_skipped=%s",
            admin.id,
            user.id,
            user.username,
            idempotency_key,
            summary.failed,
            summary.skipped,
        )
    return attach_apply_status(user, summary)


@router.get("/users/{user_id}", response_model=VpnUserRead)
def get_user(user_id: int, _: Admin = Depends(current_admin), db: Session = Depends(get_db)) -> VpnUser:
    user = _get_or_404(db, VpnUser, user_id)
    if user.status == UserStatus.deleted.value:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


@router.put("/users/{user_id}", response_model=VpnUserRead)
async def update_user(user_id: int, payload: VpnUserCreate, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> VpnUser:
    user = _get_or_404(db, VpnUser, user_id)
    duplicate_id = db.scalar(select(VpnUser.id).where(VpnUser.username == payload.username, VpnUser.id != user.id))
    if duplicate_id:
        raise HTTPException(status_code=409, detail="Пользователь с таким логином уже существует")
    active_devices = user.active_devices_count
    if payload.device_limit < active_devices:
        raise HTTPException(status_code=400, detail="Нельзя установить лимит меньше текущего количества активных устройств.")
    allowed_node_ids = normalize_allowed_node_ids(db, payload.allowed_node_ids, payload.status)
    if payload.status == UserStatus.active.value and not allowed_node_ids and has_online_nodes(db):
        raise HTTPException(status_code=422, detail="Активному пользователю нужен хотя бы один доступный сервер")
    if payload.primary_node_id and payload.primary_node_id not in allowed_node_ids:
        raise HTTPException(status_code=422, detail="Основной сервер должен входить в доступные серверы")
    for key, value in payload.model_dump(exclude={"allowed_node_ids", "primary_node_id"}).items():
        setattr(user, key, value)
    old_ids, new_ids = set_user_node_access(db, user, allowed_node_ids, payload.primary_node_id)
    audit(db, "update", "vpn_user", user.id, admin.id)
    summary = await safe_auto_apply_after_change(db, admin, old_ids | new_ids, "auto_apply_after_user_update")
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.exception("update user commit failed admin_id=%s user_id=%s username=%s", admin.id, user_id, payload.username)
        raise HTTPException(status_code=409, detail="Пользователь с таким логином уже существует") from exc
    return attach_apply_status(user, summary)


@router.delete("/users/{user_id}", response_model=Message)
async def delete_user(user_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> Message:
    user = _get_or_404(db, VpnUser, user_id)
    affected_ids = set(user.allowed_node_ids or [])
    logger.info("delete user start admin_id=%s user_id=%s status=%s nodes=%s", admin.id, user.id, user.status, sorted(affected_ids))
    if user.status == UserStatus.deleted.value:
        logger.info("delete user already_deleted admin_id=%s user_id=%s", admin.id, user.id)
        return Message(message="Пользователь уже удален")
    user.status = UserStatus.deleted.value
    audit(db, "delete", "vpn_user", user.id, admin.id)
    summary = await safe_auto_apply_after_change(db, admin, affected_ids, "auto_apply_after_user_delete")
    db.commit()
    logger.info(
        "delete user response success admin_id=%s user_id=%s apply_failed=%s apply_skipped=%s",
        admin.id,
        user.id,
        summary.failed,
        summary.skipped,
    )
    return Message(
        message="Пользователь помечен как удаленный",
        diagnostics=apply_warning("Пользователь удален", summary),
        apply_status=summary.as_dict(),
    )


@router.post("/users/{user_id}/enable", response_model=VpnUserRead)
async def enable_user(user_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> VpnUser:
    user = _get_or_404(db, VpnUser, user_id)
    user.status = UserStatus.active.value
    affected_ids = set(user.allowed_node_ids or [])
    audit(db, "enable", "vpn_user", user.id, admin.id)
    summary = await auto_apply_after_change(db, admin, affected_ids, "auto_apply_after_user_enable")
    db.commit()
    return attach_apply_status(user, summary)


@router.post("/users/{user_id}/disable", response_model=VpnUserRead)
async def disable_user(user_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> VpnUser:
    user = _get_or_404(db, VpnUser, user_id)
    affected_ids = set(user.allowed_node_ids or [])
    user.status = UserStatus.disabled.value
    audit(db, "disable", "vpn_user", user.id, admin.id)
    summary = await auto_apply_after_change(db, admin, affected_ids, "auto_apply_after_user_disable")
    db.commit()
    return attach_apply_status(user, summary)


@router.post("/users/{user_id}/regenerate-uuid", response_model=VpnUserRead)
async def regenerate_user_uuid(user_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> VpnUser:
    user = _get_or_404(db, VpnUser, user_id)
    affected_ids = set(user.allowed_node_ids or [])
    user.uuid = str(uuid.uuid4())
    audit(db, "regenerate_uuid", "vpn_user", user.id, admin.id)
    summary = await auto_apply_after_change(db, admin, affected_ids, "auto_apply_after_uuid_regenerate")
    db.commit()
    return attach_apply_status(user, summary)


@router.post("/users/{user_id}/regenerate-subscription", response_model=VpnUserRead)
async def regenerate_subscription(user_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> VpnUser:
    user = _get_or_404(db, VpnUser, user_id)
    affected_ids = set(user.allowed_node_ids or [])
    user.subscription_token = secrets.token_urlsafe(32)
    audit(db, "regenerate_subscription", "vpn_user", user.id, admin.id)
    summary = await auto_apply_after_change(db, admin, affected_ids, "auto_apply_after_subscription_regenerate")
    db.commit()
    return attach_apply_status(user, summary)


@router.post("/users/{user_id}/reset-traffic", response_model=VpnUserRead)
async def reset_user_traffic(user_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> VpnUser:
    user = _get_or_404(db, VpnUser, user_id)
    user.used_upload_bytes = 0
    user.used_download_bytes = 0
    user.used_total_bytes = 0
    user.last_raw_upload_bytes = 0
    user.last_raw_download_bytes = 0
    user.last_seen_delta_bytes = 0
    for row in db.scalars(select(UserNodeTraffic).where(UserNodeTraffic.vpn_user_id == user.id)):
        row.upload_bytes = 0
        row.download_bytes = 0
        row.total_bytes = 0
        row.last_raw_upload_bytes = 0
        row.last_raw_download_bytes = 0
        row.last_collected_at = None
        row.last_online_at = None
    if user.status == UserStatus.traffic_limited.value:
        user.status = UserStatus.active.value
    audit(db, "reset_traffic", "vpn_user", user.id, admin.id)
    summary = await auto_apply_after_change(db, admin, set(user.allowed_node_ids or []), "auto_apply_after_traffic_reset")
    db.commit()
    return attach_apply_status(user, summary)


@router.get("/users/{user_id}/devices", response_model=list[VpnUserDeviceRead])
def list_user_devices(user_id: int, _: Admin = Depends(current_admin), db: Session = Depends(get_db)) -> list[VpnUserDevice]:
    user = _get_or_404(db, VpnUser, user_id)
    return list(db.scalars(select(VpnUserDevice).where(VpnUserDevice.vpn_user_id == user.id).order_by(VpnUserDevice.created_at.desc())))


@router.patch("/users/{user_id}/devices/{device_id}", response_model=VpnUserDeviceRead)
async def update_user_device(
    user_id: int,
    device_id: int,
    payload: VpnUserDeviceUpdate,
    admin: Admin = Depends(require_write),
    db: Session = Depends(get_db),
) -> VpnUserDevice:
    user = _get_or_404(db, VpnUser, user_id)
    device = _get_or_404(db, VpnUserDevice, device_id)
    if device.vpn_user_id != user.id:
        raise HTTPException(status_code=404, detail="Устройство не найдено")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(device, key, value)
    audit(db, "update_device", "vpn_user_device", device.id, admin.id)
    summary = await auto_apply_after_change(db, admin, set(user.allowed_node_ids or []), "auto_apply_after_device_update")
    db.commit()
    setattr(device, "apply_status", summary.as_dict())
    return device


@router.post("/users/{user_id}/devices/{device_id}/revoke", response_model=Message)
async def revoke_user_device(user_id: int, device_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> Message:
    user = _get_or_404(db, VpnUser, user_id)
    device = db.get(VpnUserDevice, device_id)
    if not device or device.vpn_user_id != user.id:
        logger.info("remove device already_removed admin_id=%s user_id=%s device_id=%s", admin.id, user.id, device_id)
        return Message(message="Устройство уже удалено")
    device_id_for_audit = device.id
    logger.info("remove device start admin_id=%s user_id=%s device_id=%s", admin.id, user.id, device.id)
    try:
        summary = await _remove_device_and_apply(db, user, device, reason="auto_apply_after_device_remove", admin_id=admin.id)
    except ConfigApplyRequiredError as exc:
        db.rollback()
        logger.exception("remove device failed admin_id=%s user_id=%s device_id=%s", admin.id, user.id, device_id_for_audit)
        raise HTTPException(status_code=503, detail=str(exc) or "Конфиг Xray не удалось применить") from exc
    audit(db, "remove_device", "vpn_user_device", device_id_for_audit, admin.id)
    db.commit()
    logger.info("remove device success admin_id=%s user_id=%s device_id=%s", admin.id, user.id, device_id_for_audit)
    return Message(message="Устройство удалено", apply_status=summary.as_dict() if summary else None)


@router.post("/users/{user_id}/devices/reset", response_model=list[VpnUserDeviceRead])
async def reset_user_devices(user_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> list[VpnUserDevice]:
    user = _get_or_404(db, VpnUser, user_id)
    logger.info("reset devices start admin_id=%s user_id=%s", admin.id, user.id)
    devices_to_delete = list(user.devices)
    if not devices_to_delete:
        logger.info("reset devices already_empty admin_id=%s user_id=%s", admin.id, user.id)
        return []
    for device in devices_to_delete:
        db.delete(device)
    db.flush()
    audit(db, "reset_devices", "vpn_user", user.id, admin.id)
    if affected_node_ids_for_user(user):
        try:
            await apply_config_for_user(
                db,
                user,
                reason="auto_apply_after_devices_reset",
                admin_id=admin.id,
                require_success=True,
            )
        except ConfigApplyRequiredError as exc:
            db.rollback()
            logger.exception("reset devices failed admin_id=%s user_id=%s", admin.id, user.id)
            raise HTTPException(status_code=503, detail=str(exc) or "Конфиг Xray не удалось применить") from exc
    db.commit()
    logger.info("reset devices success admin_id=%s user_id=%s", admin.id, user.id)
    return []


@router.post("/users/import", response_model=BulkImportResult)
async def import_users(file: UploadFile, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> BulkImportResult:
    text = (await file.read()).decode("utf-8-sig")
    rows = csv.DictReader(io.StringIO(text))
    created: list[VpnUser] = []
    errors: list[str] = []
    affected_ids: set[int] = set()
    for row in rows:
        username = (row.get("username") or row.get("Логин") or "").strip()
        if not username:
            errors.append("Строка пропущена: не указан username/Логин")
            continue
        existing = db.scalar(select(VpnUser).where(VpnUser.username == username))
        if existing and existing.status != UserStatus.deleted.value:
            errors.append(f"{username}: пользователь уже существует")
            continue
        payload = VpnUserCreate(
            first_name=(row.get("first_name") or row.get("Имя") or "").strip(),
            last_name=(row.get("last_name") or row.get("Фамилия") or "").strip(),
            username=username,
            status="active",
        )
        allowed_node_ids = normalize_allowed_node_ids(db, payload.allowed_node_ids, payload.status)
        user = VpnUser(
            **payload.model_dump(exclude={"allowed_node_ids", "primary_node_id"}),
            uuid=str(uuid.uuid4()),
            subscription_token=secrets.token_urlsafe(32),
        )
        db.add(user)
        db.flush()
        _, new_ids = set_user_node_access(db, user, allowed_node_ids, payload.primary_node_id)
        affected_ids.update(new_ids)
        created.append(user)
    audit(db, "bulk_import", "vpn_user", metadata={"count": len(created)}, admin_id=admin.id)
    summary = await auto_apply_after_change(db, admin, affected_ids, "auto_apply_after_users_import")
    db.commit()
    return BulkImportResult(
        created=len(created),
        updated=0,
        skipped=len(errors),
        errors=errors,
        users=[attach_apply_status(user, summary) for user in created],
        apply_status=summary.as_dict(),
    )


@router.get("/users/{user_id}/subscription-preview")
def subscription_preview(user_id: int, _: Admin = Depends(current_admin), db: Session = Depends(get_db)) -> dict[str, Any]:
    user = _get_or_404(db, VpnUser, user_id)
    if user.status == UserStatus.deleted.value:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    payload = subscription_payload(db, user)
    return {
        "subscription_url": f"/sub/{user.subscription_token}",
        **payload,
    }


@router.post("/traffic/collect/{node_id}")
async def collect_traffic(node_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> dict[str, Any]:
    node = _get_or_404(db, VpsNode, node_id)
    result = await collect_traffic_stats(db, [node], selected_node_id=node.id)
    audit(
        db,
        "collect_stats",
        "vps_node",
        node.id,
        admin.id,
        metadata={"updated_users": result["updated_users"], "errors": result["errors"]},
    )
    db.commit()
    return result


@router.post("/traffic/collect-now")
async def collect_traffic_now(admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> dict[str, Any]:
    nodes = list(db.scalars(select(VpsNode).order_by(VpsNode.created_at.desc())))
    result = await collect_traffic_stats(db, nodes)
    audit(
        db,
        "collect_stats",
        "traffic",
        admin_id=admin.id,
        metadata={"updated_users": result["updated_users"], "selected_nodes": result["selected_nodes"], "errors": result["errors"]},
    )
    db.commit()
    return result


@router.post("/traffic/collect-background")
async def collect_traffic_background(_: Admin = Depends(require_write), db: Session = Depends(get_db)) -> dict[str, Any]:
    nodes = list(db.scalars(select(VpsNode).order_by(VpsNode.created_at.desc())))
    return await collect_traffic_stats(db, nodes)


@router.post("/traffic/debug-collect")
async def debug_collect_traffic(admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> dict[str, Any]:
    nodes = list(db.scalars(select(VpsNode).order_by(VpsNode.created_at.desc())))
    result = await collect_traffic_stats(db, nodes, debug=True)
    audit(
        db,
        "debug_collect_stats",
        "traffic",
        admin_id=admin.id,
        metadata={"updated_users": result["updated_users"], "selected_nodes": result["selected_nodes"], "errors": result["errors"]},
    )
    db.commit()
    return result


@router.get("/traffic/overview", response_model=list[TrafficUserRead])
def traffic_users(_: Admin = Depends(current_admin), db: Session = Depends(get_db)) -> list[dict]:
    return traffic_overview(db)


@router.get("/traffic/snapshots", response_model=list[TrafficSnapshotRead])
def traffic_snapshots(_: Admin = Depends(current_admin), db: Session = Depends(get_db)) -> list[TrafficSnapshot]:
    return list(
        db.scalars(
            select(TrafficSnapshot)
            .join(VpnUser)
            .where(VpnUser.status != UserStatus.deleted.value)
            .order_by(TrafficSnapshot.collected_at.desc())
            .limit(500)
        )
    )


@router.get("/audit-log", response_model=list[AuditLogRead])
def audit_log(_: Admin = Depends(current_admin), db: Session = Depends(get_db)) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(500)))


@router.get("/backup/export")
def export_backup(_: Admin = Depends(current_admin), db: Session = Depends(get_db)) -> StreamingResponse:
    raw, filename = build_backup_archive(db)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(io.BytesIO(raw), media_type="application/gzip", headers=headers)


@router.post("/backup/import", response_model=RestoreSummary)
async def import_backup(file: UploadFile, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> RestoreSummary:
    filename = file.filename or ""
    if not filename.endswith(".tar.gz"):
        raise HTTPException(status_code=422, detail="Загрузите архив .tar.gz")
    raw = await file.read()
    try:
        restored = restore_backup_archive(db, raw)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    audit(db, "restore_backup", "system", admin_id=admin.id, metadata={"restored": restored})
    summary = await ConfigApplyService(db, admin.id).apply_to_nodes(
        None,
        reason="auto_apply_after_backup_restore",
    )
    db.commit()
    return RestoreSummary(restored=restored, apply_status=summary.as_dict())


def _hwid_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"x-hwid-limit": "true"}
    if extra:
        headers.update(extra)
    return headers


def _plain_forbidden(message: str, extra_headers: dict[str, str] | None = None) -> Response:
    return Response(message, status_code=403, media_type="text/plain; charset=utf-8", headers=_hwid_headers(extra_headers))


def _plain_error(message: str, status_code: int, extra_headers: dict[str, str] | None = None) -> Response:
    return Response(message, status_code=status_code, media_type="text/plain; charset=utf-8", headers=_hwid_headers(extra_headers))


def _touch_device_from_context(device: VpnUserDevice, context, db: Session) -> None:
    apply_device_metadata(device, context, created=False)
    db.flush()


async def _remove_device_and_apply(
    db: Session,
    user: VpnUser,
    device: VpnUserDevice,
    *,
    reason: str,
    admin_id: int | None = None,
) -> ConfigApplySummary | None:
    logger.info("device remove apply start user_id=%s device_id=%s reason=%s", user.id, device.id, reason)
    db.delete(device)
    db.flush()
    if not affected_node_ids_for_user(user):
        logger.info("device remove apply skipped no_nodes user_id=%s reason=%s", user.id, reason)
        return None
    summary = await apply_config_for_user(
        db,
        user,
        reason=reason,
        admin_id=admin_id,
        require_success=True,
    )
    logger.info("device remove apply success user_id=%s reason=%s summary=%s", user.id, reason, summary.as_dict())
    return summary


async def _apply_for_subscription(db: Session, user: VpnUser) -> ConfigApplySummary:
    return await apply_config_for_user(
        db,
        user,
        reason="auto_apply_after_hwid_device_change",
        require_success=True,
    )


@public_router.get("/public/connect/{user_token}", response_model=PublicConnectRead)
def public_connect(user_token: str, db: Session = Depends(get_db)) -> PublicConnectRead:
    user = validate_subscription_user(db.scalar(select(VpnUser).where(VpnUser.subscription_token == user_token)))
    devices = [device for device in user.devices if device.status == DeviceStatus.active.value]
    return PublicConnectRead(
        display_name=f"{user.first_name} {user.last_name}".strip() or user.username,
        status=user.status,
        expires_at=user.expires_at,
        traffic_limit=user.traffic_limit_bytes,
        used_traffic=user.used_total_bytes or 0,
        device_limit=user.device_limit,
        active_devices_count=user.active_devices_count,
        devices_label=user.devices_label,
        devices=devices,
    )


@public_router.post("/public/connect/{user_token}/install-link")
def deprecated_install_link(user_token: str) -> Response:
    return Response(
        "Install-link flow deprecated. Используйте /sub/{user_token} с x-hwid.",
        status_code=status.HTTP_410_GONE,
        media_type="text/plain; charset=utf-8",
    )


@public_router.delete("/public/connect/{user_token}/devices/{device_id}", response_model=Message)
async def public_disconnect_device(user_token: str, device_id: int, db: Session = Depends(get_db)) -> Message:
    user = validate_subscription_user(db.scalar(select(VpnUser).where(VpnUser.subscription_token == user_token)))
    device = db.get(VpnUserDevice, device_id)
    if not device or device.vpn_user_id != user.id:
        logger.info("public remove device already_removed user_id=%s device_id=%s", user.id, device_id)
        return Message(message="Устройство уже удалено")
    logger.info("public remove device start user_id=%s device_id=%s", user.id, device.id)
    try:
        summary = await _remove_device_and_apply(db, user, device, reason="auto_apply_after_public_device_remove")
    except ConfigApplyRequiredError as exc:
        db.rollback()
        logger.exception("public remove device failed user_id=%s device_id=%s", user.id, device_id)
        raise HTTPException(status_code=503, detail="Не удалось применить конфигурацию на сервер") from exc
    db.commit()
    logger.info("public remove device success user_id=%s device_id=%s", user.id, device_id)
    return Message(message="Устройство удалено", apply_status=summary.as_dict() if summary else None)


@public_router.get("/sub/device/{device_token}")
def device_subscription(
    device_token: str,
    request: Request,
    format: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    device = db.scalar(select(VpnUserDevice).where(VpnUserDevice.subscription_token == device_token))
    if not device:
        raise HTTPException(status_code=404, detail="Подписка недоступна")
    user = validate_subscription_user(device.vpn_user)
    context = compute_hwid_context(request, device.platform, device.client_name)
    if not context:
        return _plain_forbidden("Ваш клиент не поддерживает ограничение устройств", {"x-hwid-not-supported": "true"})
    if device.status != DeviceStatus.active.value:
        return _plain_forbidden("Устройство отключено")
    if not device.hwid_hash or context.hwid_hash != device.hwid_hash:
        return _plain_forbidden("Ссылка подписки привязана к другому устройству")
    _touch_device_from_context(device, context, db)
    db.commit()
    response = subscription_response(db, user, device, format)
    response.headers["x-hwid-limit"] = "true"
    response.headers["x-hwid-active"] = "true"
    return response


@public_router.get("/sub/{token}")
async def subscription(
    token: str,
    request: Request,
    platform: str | None = None,
    client: str | None = None,
    format: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    user = validate_subscription_user(db.scalar(select(VpnUser).where(VpnUser.subscription_token == token)))
    context = compute_hwid_context(request, platform, client)
    if not context:
        return _plain_forbidden("Ваш клиент не поддерживает ограничение устройств", {"x-hwid-not-supported": "true"})

    device = db.scalar(
        select(VpnUserDevice).where(
            VpnUserDevice.vpn_user_id == user.id,
            VpnUserDevice.hwid_hash == context.hwid_hash,
        )
    )
    if device:
        if device.status == DeviceStatus.active.value:
            _touch_device_from_context(device, context, db)
            db.commit()
            response = subscription_response(db, user, device, format)
            response.headers["x-hwid-limit"] = "true"
            response.headers["x-hwid-active"] = "true"
            return response
        db.delete(device)
        db.flush()

    db.expire(user, ["devices", "node_links", "access_profile"])
    if user.active_devices_count >= user.device_limit:
        return _plain_forbidden("Превышен лимит устройств", {"x-hwid-max-devices-reached": "true"})
    affected_node_ids = affected_node_ids_for_user(user)
    if not affected_node_ids:
        return _plain_forbidden("Пользователю не назначен сервер")

    user_id_for_log = user.id
    device = VpnUserDevice(
        vpn_user_id=user.id,
        uuid=str(uuid.uuid4()),
        subscription_token=secrets.token_urlsafe(32),
        status=DeviceStatus.active.value,
    )
    db.add(device)
    apply_device_metadata(device, context, created=True)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        logger.info("subscription new hwid race detected user_id=%s", user_id_for_log)
        user = validate_subscription_user(db.scalar(select(VpnUser).where(VpnUser.subscription_token == token)))
        existing = db.scalar(
            select(VpnUserDevice).where(
                VpnUserDevice.vpn_user_id == user.id,
                VpnUserDevice.hwid_hash == context.hwid_hash,
                VpnUserDevice.status == DeviceStatus.active.value,
            )
        )
        if not existing:
            return _plain_error("Не удалось зарегистрировать устройство", status.HTTP_503_SERVICE_UNAVAILABLE)
        response = subscription_response(db, user, existing, format)
        response.headers["x-hwid-limit"] = "true"
        response.headers["x-hwid-active"] = "true"
        return response
    logger.info("subscription new hwid device created pending_apply user_id=%s device_id=%s", user.id, device.id)
    if not device.display_name or device.display_name == "Новое устройство":
        device.display_name = build_display_name(
            device_model=device.device_model,
            platform=device.platform,
            os_version=device.os_version,
            client_name=device.client_name,
            device_id=device.id,
        )
    try:
        await _apply_for_subscription(db, user)
    except ConfigApplyRequiredError as exc:
        summary = exc.summary.as_dict() if exc.summary else None
        user_id = user.id
        device_id = device.id
        db.rollback()
        logger.error(
            "subscription new hwid apply failed user_id=%s device_id=%s nodes=%s summary=%s",
            user_id,
            device_id,
            sorted(affected_node_ids),
            summary,
        )
        if str(exc) == "Пользователю не назначен сервер":
            return _plain_forbidden("Пользователю не назначен сервер")
        return _plain_error("Не удалось применить конфигурацию на сервер", status.HTTP_503_SERVICE_UNAVAILABLE)
    db.commit()
    logger.info("subscription new hwid apply success user_id=%s device_id=%s", user.id, device.id)
    response = subscription_response(db, user, device, format)
    response.headers["x-hwid-limit"] = "true"
    response.headers["x-hwid-active"] = "true"
    return response


@router.post("/seed/default-profile", response_model=list[AccessProfileRead])
def seed_default_profile(admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> list[AccessProfile]:
    profiles = seed_default_access_profiles(db)
    audit(db, "seed", "access_profile", admin_id=admin.id)
    db.commit()
    return profiles
