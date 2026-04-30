import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NodeStatus, VpnUser, VpsNode
from app.services.audit import audit
from app.services.reality import ensure_reality_credentials
from app.services.ssh_installer import XrayInstaller
from app.services.xray_config import render_server_config


APPLY_SUCCESS = "success"
APPLY_FAILED = "failed"
APPLY_SKIPPED = "skipped"
APPLY_PENDING = "pending"


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


def node_has_installed_xray(node: VpsNode) -> bool:
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
    ) -> ConfigApplySummary:
        nodes = self._target_nodes(set(node_ids) if node_ids is not None else None, include_uninstalled)
        users = list(self.db.scalars(select(VpnUser)))
        results: list[NodeApplyResult] = []
        for node in nodes:
            results.append(await self._apply_node(node, users, reason, allow_non_online))
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
        nodes = list(self.db.scalars(query))
        if include_uninstalled:
            return nodes
        return [
            node
            for node in nodes
            if node.status == NodeStatus.online.value and node_has_installed_xray(node)
        ]

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
