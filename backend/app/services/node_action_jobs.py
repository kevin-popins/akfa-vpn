from __future__ import annotations

import asyncio
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import NodeManagedMode, NodeStatus, VpnUser, VpsNode
from app.schemas.entities import NodeRead
from app.services.audit import audit
from app.services.reality import ensure_reality_credentials
from app.services.ssh_installer import XrayInstaller


def install_failure_reason(logs: list[dict]) -> str:
    for entry in reversed(logs or []):
        if entry.get("level") != "error":
            continue
        parts = [
            str(entry.get("message") or "").strip(),
            str(entry.get("command") or "").strip(),
            str(entry.get("stderr") or "").strip(),
        ]
        reason = " · ".join(part for part in parts if part)
        if reason:
            return reason
    return "Не удалось завершить установку Xray"


JobStatus = str


@dataclass
class NodeActionJob:
    job_id: str
    node_id: int
    action: str
    admin_id: int | None
    status: JobStatus = "pending"
    current_step: str = "Ожидает запуска"
    logs: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    result: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "node_id": self.node_id,
            "action": self.action,
            "status": self.status,
            "current_step": self.current_step,
            "logs": self.logs,
            "error": self.error,
            "result": self.result,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


_jobs: dict[str, NodeActionJob] = {}
_running_install_by_node: dict[int, str] = {}
_lock = threading.Lock()


def start_install_job(node_id: int, admin_id: int | None) -> NodeActionJob:
    with _lock:
        existing_id = _running_install_by_node.get(node_id)
        if existing_id:
            existing = _jobs.get(existing_id)
            if existing and existing.status in {"pending", "running"}:
                return existing
        job = NodeActionJob(
            job_id=uuid.uuid4().hex,
            node_id=node_id,
            action="install",
            admin_id=admin_id,
            current_step="Подключаемся к VPS...",
        )
        _jobs[job.job_id] = job
        _running_install_by_node[node_id] = job.job_id

    thread = threading.Thread(target=lambda: asyncio.run(_run_install_job(job.job_id)), daemon=True)
    thread.start()
    return job


def get_job(job_id: str) -> NodeActionJob | None:
    with _lock:
        return _jobs.get(job_id)


async def _run_install_job(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        return
    _update_job(job_id, status="running", current_step="Подключаемся к VPS...")
    db = SessionLocal()
    try:
        node = db.get(VpsNode, job.node_id)
        if not node:
            _update_job(job_id, status="failed", error="Нода не найдена", current_step="Установка Xray не завершена")
            return
        ensure_reality_credentials(node)
        node.status = NodeStatus.installing.value
        db.commit()

        users = list(db.scalars(select(VpnUser)))
        installer = XrayInstaller(node, users, progress_callback=lambda entry: _append_log(job_id, entry))
        result = await installer.install()

        node = db.get(VpsNode, job.node_id)
        if not node:
            _update_job(job_id, status="failed", error="Нода не найдена после установки", current_step="Установка Xray не завершена")
            return
        node.install_log = result.logs
        node.status = NodeStatus.online.value if result.ok else NodeStatus.failed.value
        node.xray_installed = bool(result.ok)
        if result.ok:
            node.managed_mode = NodeManagedMode.akfa_owned.value
        node.reality_private_key = result.reality_private_key or node.reality_private_key
        node.reality_public_key = result.reality_public_key or node.reality_public_key
        node.short_id = result.short_id or node.short_id
        node.last_check_at = datetime.now(timezone.utc)
        audit(db, "install_xray", "vps_node", node.id, job.admin_id)
        db.commit()
        db.refresh(node)

        if result.ok:
            _update_job(
                job_id,
                status="success",
                current_step="Установка Xray завершена",
                result=NodeRead.model_validate(node).model_dump(mode="json"),
            )
        else:
            reason = install_failure_reason(result.logs)
            _update_job(
                job_id,
                status="failed",
                current_step="Установка Xray не завершена",
                error=f"Установка Xray не завершена: {reason}",
                result=NodeRead.model_validate(node).model_dump(mode="json"),
            )
    except Exception as exc:
        db.rollback()
        node = db.get(VpsNode, job.node_id)
        if node:
            node.status = NodeStatus.failed.value
            node.xray_installed = False
            node.install_log = job.logs + [
                {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "level": "error",
                    "command": None,
                    "message": "Ошибка фоновой установки",
                    "stderr": str(exc),
                    "exit_code": None,
                    "mutating": False,
                }
            ]
            db.commit()
        _update_job(job_id, status="failed", current_step="Установка Xray не завершена", error=f"Установка Xray не завершена: {exc}")
    finally:
        db.close()
        with _lock:
            current = _running_install_by_node.get(job.node_id)
            if current == job_id:
                _running_install_by_node.pop(job.node_id, None)


def _append_log(job_id: str, entry: dict[str, Any]) -> None:
    message = str(entry.get("message") or "")
    command = str(entry.get("command") or "")
    current_step = _step_from_log(message, command)
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.logs.append(entry)
        if current_step:
            job.current_step = current_step
        job.updated_at = datetime.now(timezone.utc)


def _update_job(
    job_id: str,
    *,
    status: JobStatus | None = None,
    current_step: str | None = None,
    error: str | None = None,
    result: dict[str, Any] | None = None,
) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        if status is not None:
            job.status = status
        if current_step is not None:
            job.current_step = current_step
        if error is not None:
            job.error = error
        if result is not None:
            job.result = result
        job.updated_at = datetime.now(timezone.utc)


def _step_from_log(message: str, command: str) -> str | None:
    if "apt/dpkg" in command or "AKFA_APT_DPKG_OK" in message:
        return "Проверяем apt/dpkg..."
    if "apt-get update" in command:
        return "Обновляем пакеты..."
    if "apt-get install" in command:
        return "Устанавливаем зависимости..."
    if "install-release.sh" in command:
        return "Скачиваем и устанавливаем Xray..."
    if "cat >" in command or "cp " in command or "chmod" in command:
        return "Пишем Reality config..."
    if "xray run -test" in command or "jq empty" in command:
        return "Проверяем конфигурацию Xray..."
    if "systemctl restart" in command or "systemctl enable" in command:
        return "Запускаем Xray service..."
    if "systemctl is-active" in command or "systemctl status" in command:
        return "Проверяем статус ноды..."
    if "Начата реальная установка" in message:
        return "Подключаемся к VPS..."
    return None
