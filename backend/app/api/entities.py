import csv
import io
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, TypeVar

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
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
    NodeMetricsRead,
    NodeRead,
    NodeUpdate,
    RestoreSummary,
    SniCheckRequest,
    SniCheckResponse,
    SshCheckResponse,
    TrafficSnapshotRead,
    TrafficUserRead,
    VpnUserCreate,
    VpnUserRead,
)
from app.services.access_profiles import seed_default_access_profiles
from app.services.reality import check_sni_target, ensure_reality_credentials
from app.services.audit import audit
from app.services.backup import build_backup_archive, restore_backup_archive
from app.services.config_apply import ConfigApplyService, ConfigApplySummary
from app.services.server_metrics import collect_nodes_metrics
from app.services.ssh_installer import XrayInstaller
from app.services.subscriptions import get_subscription, subscription_payload
from app.services.traffic import (
    collect_traffic as collect_traffic_stats,
    enforce_expiration_and_limits,
    traffic_overview,
)
from app.services.xray_config import render_server_config

router = APIRouter(prefix="/admin", tags=["admin"])
public_router = APIRouter(tags=["subscriptions"])
ModelT = TypeVar("ModelT")


def _get_or_404(db: Session, model: type[ModelT], item_id: int) -> ModelT:
    item = db.get(model, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Запись не найдена")
    return item


def attach_apply_status(item: object, summary: ConfigApplySummary | None) -> object:
    if summary is not None:
        setattr(item, "apply_status", summary.as_dict())
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
    node.last_check_at = datetime.now(timezone.utc)
    audit(db, "verify_xray", "vps_node", node.id, admin.id)
    db.commit()
    return node


@router.post("/nodes/{node_id}/install", response_model=NodeRead)
async def install_node(node_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> VpsNode:
    node = _get_or_404(db, VpsNode, node_id)
    ensure_reality_credentials(node)
    node.status = NodeStatus.installing.value
    db.commit()
    users = list(db.scalars(select(VpnUser)))
    result = await XrayInstaller(node, users).install()
    node.install_log = result.logs
    node.status = NodeStatus.online.value if result.ok else NodeStatus.failed.value
    node.reality_private_key = result.reality_private_key or node.reality_private_key
    node.reality_public_key = result.reality_public_key or node.reality_public_key
    node.short_id = result.short_id or node.short_id
    node.last_check_at = datetime.now(timezone.utc)
    audit(db, "install_xray", "vps_node", node.id, admin.id)
    db.commit()
    return node


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
async def create_user(payload: VpnUserCreate, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> VpnUser:
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
    db.flush()
    _, new_ids = set_user_node_access(db, user, allowed_node_ids, payload.primary_node_id)
    audit(db, "create", "vpn_user", user.id, admin.id)
    summary = await auto_apply_after_change(db, admin, new_ids, "auto_apply_after_user_create")
    db.commit()
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
    allowed_node_ids = normalize_allowed_node_ids(db, payload.allowed_node_ids, payload.status)
    if payload.status == UserStatus.active.value and not allowed_node_ids and has_online_nodes(db):
        raise HTTPException(status_code=422, detail="Активному пользователю нужен хотя бы один доступный сервер")
    if payload.primary_node_id and payload.primary_node_id not in allowed_node_ids:
        raise HTTPException(status_code=422, detail="Основной сервер должен входить в доступные серверы")
    for key, value in payload.model_dump(exclude={"allowed_node_ids", "primary_node_id"}).items():
        setattr(user, key, value)
    old_ids, new_ids = set_user_node_access(db, user, allowed_node_ids, payload.primary_node_id)
    audit(db, "update", "vpn_user", user.id, admin.id)
    summary = await auto_apply_after_change(db, admin, old_ids | new_ids, "auto_apply_after_user_update")
    db.commit()
    return attach_apply_status(user, summary)


@router.delete("/users/{user_id}", response_model=Message)
async def delete_user(user_id: int, admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> Message:
    user = _get_or_404(db, VpnUser, user_id)
    affected_ids = set(user.allowed_node_ids or [])
    user.status = UserStatus.deleted.value
    audit(db, "delete", "vpn_user", user.id, admin.id)
    summary = await auto_apply_after_change(db, admin, affected_ids, "auto_apply_after_user_delete")
    db.commit()
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


@public_router.get("/sub/{token}")
def subscription(token: str, db: Session = Depends(get_db)) -> Response:
    payload = get_subscription(db, token)
    return Response(str(payload["vless_uri"]), media_type="text/plain; charset=utf-8")


@router.post("/seed/default-profile", response_model=list[AccessProfileRead])
def seed_default_profile(admin: Admin = Depends(require_write), db: Session = Depends(get_db)) -> list[AccessProfile]:
    profiles = seed_default_access_profiles(db)
    audit(db, "seed", "access_profile", admin_id=admin.id)
    db.commit()
    return profiles
