import asyncio
import hashlib
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import NodeStatus, VpnUser, VpsNode
from app.services.audit import audit
from app.services.reality import ensure_reality_credentials
from app.services.ssh_installer import XrayInstaller
from app.services.xray_config import render_server_config
from app.services.xray_config import effective_node_ids


APPLY_SUCCESS = "success"
APPLY_FAILED = "failed"
APPLY_SKIPPED = "skipped"
APPLY_PENDING = "pending"
APPLY_FLOW_TIMEOUT_SECONDS = 25
logger = logging.getLogger(__name__)


@dataclass
class NodeApplyResult:
    node_id: int
    node_name: str
    ok: bool
    status: str
    error: str | None = None
    applied_at: str | None = None
    config_version: str | None = None


@dataclass
class ConfigApplySummary:
    ok: bool
    attempted: int
    succeeded: int
    failed: int
    skipped: int
    results: list[NodeApplyResult]

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "attempted": self.attempted,
            "succeeded": self.succeeded,
            "failed": self.failed,
            "skipped": self.skipped,
            "results": [asdict(result) for result in self.results],
        }


class ConfigApplyRequiredError(RuntimeError):
    def __init__(self, message: str, summary: ConfigApplySummary | None = None) -> None:
        super().__init__(message)
        self.summary = summary


def node_has_installed_xray(node: VpsNode) -> bool:
    if getattr(node, "xray_installed", False):
        return True
    log_text = str(node.install_log or [])
    return (
        "Начата реальная установка Xray" in log_text
        or "Применение конфига Xray" in log_text
        or "systemctl restart" in log_text
        or "systemctl status" in log_text
        or "jq empty" in log_text
        or "ss -tulpn" in log_text
        or "xray version" in log_text
        or node.last_config_apply_status == APPLY_SUCCESS
    )


class ConfigApplyService:
    def __init__(self, db: Session, admin_id: int | None = None) -> None:
        self.db = db
        self.admin_id = admin_id

    async def apply_to_nodes(
        self,
        node_ids: set[int] | list[int] | None = None,
        *,
        reason: str = "auto_apply_xray_config",
        include_uninstalled: bool = False,
        allow_non_online: bool = False,
        timeout_seconds: int = APPLY_FLOW_TIMEOUT_SECONDS,
    ) -> ConfigApplySummary:
        self.db.flush()
        nodes = self._target_nodes(set(node_ids) if node_ids is not None else None, include_uninstalled)
        users = self._fresh_users()
        results: list[NodeApplyResult] = []
        deadline = time.monotonic() + timeout_seconds
        for node in nodes:
            remaining = max(0.1, deadline - time.monotonic())
            if remaining <= 0.1:
                results.append(self._mark_failed(node, "Таймаут применения конфигурации Xray", datetime.now(timezone.utc), None))
                logger.error("apply-config timeout before node node_id=%s reason=%s", node.id, reason)
                continue
            logger.info("apply-config start node_id=%s reason=%s timeout_left=%.1f", node.id, reason, remaining)
            try:
                result = await asyncio.wait_for(
                    self._apply_node(node, users, reason, allow_non_online),
                    timeout=remaining,
                )
            except TimeoutError:
                result = self._mark_failed(node, "Таймаут применения конфигурации Xray", datetime.now(timezone.utc), None)
                logger.exception("apply-config timeout node_id=%s reason=%s", node.id, reason)
            if result.status == APPLY_SUCCESS:
                logger.info("apply-config success node_id=%s reason=%s config_version=%s", node.id, reason, result.config_version)
            elif result.status == APPLY_FAILED:
                logger.error("apply-config failed node_id=%s reason=%s error=%s", node.id, reason, result.error)
            else:
                logger.info("apply-config skipped node_id=%s reason=%s error=%s", node.id, reason, result.error)
            results.append(result)
        attempted = sum(1 for result in results if result.status != APPLY_SKIPPED)
        succeeded = sum(1 for result in results if result.status == APPLY_SUCCESS)
        failed = sum(1 for result in results if result.status == APPLY_FAILED)
        skipped = sum(1 for result in results if result.status == APPLY_SKIPPED)
        return ConfigApplySummary(
            ok=failed == 0,
            attempted=attempted,
            succeeded=succeeded,
            failed=failed,
            skipped=skipped,
            results=results,
        )

    def _target_nodes(self, node_ids: set[int] | None, include_uninstalled: bool) -> list[VpsNode]:
        query = select(VpsNode).order_by(VpsNode.name, VpsNode.id)
        if node_ids is not None:
            if not node_ids:
                return []
            query = query.where(VpsNode.id.in_(node_ids))
        else:
            query = query.where(VpsNode.status != NodeStatus.deleted.value)
        return list(self.db.scalars(query))

    def _fresh_users(self) -> list[VpnUser]:
        self.db.expire_all()
        return list(
            self.db.scalars(
                select(VpnUser).options(
                    selectinload(VpnUser.devices),
                    selectinload(VpnUser.node_links),
                    selectinload(VpnUser.access_profile),
                )
            )
        )

    async def _apply_node(self, node: VpsNode, users: list[VpnUser], reason: str, allow_non_online: bool) -> NodeApplyResult:
        if node.status != NodeStatus.online.value and not allow_non_online:
            return NodeApplyResult(
                node_id=node.id,
                node_name=node.name,
                ok=True,
                status=APPLY_SKIPPED,
                error="Нода не online",
            )
        if not node_has_installed_xray(node):
            return NodeApplyResult(
                node_id=node.id,
                node_name=node.name,
                ok=True,
                status=APPLY_SKIPPED,
                error="Xray еще не установлен через AKFA",
            )

        ensure_reality_credentials(node)
        applied_at = datetime.now(timezone.utc)
        try:
            rendered = render_server_config(node, users)
            config_version = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
        except Exception as exc:
            return self._mark_failed(node, str(exc), applied_at, None)

        result = await XrayInstaller(node, users).apply_config()
        node.install_log = result.logs
        node.last_check_at = applied_at
        node.last_config_version = config_version
        if result.ok:
            if node.status not in {NodeStatus.disabled.value, NodeStatus.maintenance.value, NodeStatus.deleted.value}:
                node.status = NodeStatus.online.value
            node.last_config_applied_at = applied_at
            node.last_config_apply_status = APPLY_SUCCESS
            node.last_config_apply_error = None
            audit(
                self.db,
                reason,
                "vps_node",
                node.id,
                self.admin_id,
                metadata={"config_version": config_version},
            )
            return NodeApplyResult(
                node_id=node.id,
                node_name=node.name,
                ok=True,
                status=APPLY_SUCCESS,
                applied_at=applied_at.isoformat(),
                config_version=config_version,
            )

        error = last_error_from_logs(result.logs) or "Конфиг Xray не удалось применить"
        return self._mark_failed(node, error, applied_at, config_version)

    def _mark_failed(
        self,
        node: VpsNode,
        error: str,
        applied_at: datetime,
        config_version: str | None,
    ) -> NodeApplyResult:
        node.last_check_at = applied_at
        node.last_config_apply_status = APPLY_FAILED
        node.last_config_apply_error = error[-2000:]
        node.last_config_version = config_version
        audit(
            self.db,
            "auto_apply_xray_config_failed",
            "vps_node",
            node.id,
            self.admin_id,
            metadata={"error": node.last_config_apply_error, "config_version": config_version},
        )
        return NodeApplyResult(
            node_id=node.id,
            node_name=node.name,
            ok=False,
            status=APPLY_FAILED,
            error=node.last_config_apply_error,
            applied_at=applied_at.isoformat(),
            config_version=config_version,
        )


def last_error_from_logs(logs: list[dict]) -> str | None:
    for entry in reversed(logs or []):
        if entry.get("level") == "error":
            parts = [str(entry.get("message") or "")]
            if entry.get("stderr"):
                parts.append(str(entry["stderr"]))
            return ": ".join(part for part in parts if part)
    return None


def affected_node_ids_for_user(user: VpnUser) -> set[int]:
    return effective_node_ids(user)


async def apply_config_for_user(
    db: Session,
    user: VpnUser,
    *,
    reason: str,
    admin_id: int | None = None,
    require_success: bool = False,
) -> ConfigApplySummary:
    db.flush()
    try:
        db.expire(user, ["devices", "node_links", "access_profile"])
    except Exception:
        pass
    node_ids = affected_node_ids_for_user(user)
    if not node_ids:
        raise ConfigApplyRequiredError("Пользователю не назначен сервер")
    summary = await ConfigApplyService(db, admin_id).apply_to_nodes(node_ids, reason=reason)
    if require_success:
        missing = len(node_ids) - summary.succeeded
        if missing > 0 or summary.failed or summary.skipped:
            raise ConfigApplyRequiredError("Не удалось применить конфигурацию на сервер", summary)
    return summary
