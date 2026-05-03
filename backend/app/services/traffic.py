import json
import re
from datetime import datetime, timezone
from typing import Any

import asyncssh
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.models import DeviceStatus, NodeStatus, TrafficSnapshot, UserNodeTraffic, UserStatus, VpsNode, VpnUser, VpnUserDevice

USER_TRAFFIC_RE = re.compile(r"user>>>([^>]+)>>>traffic>>>(uplink|downlink)")
DEVICE_EMAIL_RE = re.compile(r"^akfa_user_(\d+)_device_(\d+)$")
XRAY_STATS_COMMAND = "/usr/local/bin/xray api statsquery --server=127.0.0.1:10085"
ONLINE_WINDOW_SECONDS = 180


class StatsCollectionError(RuntimeError):
    def __init__(self, message: str, *, exit_code: int | None = None, stderr: str | None = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code
        self.stderr = stderr

    @property
    def diagnostics(self) -> str:
        parts = [f"exit_code={self.exit_code if self.exit_code is not None else 'unknown'}"]
        if self.stderr:
            parts.append(f"stderr={self.stderr.strip()}")
        else:
            parts.append(f"error={self}")
        return "\n".join(parts)


def select_traffic_nodes(nodes: list[VpsNode], selected_node_id: int | None = None) -> tuple[list[dict[str, Any]], list[VpsNode]]:
    considered: list[dict[str, Any]] = []
    selected: list[VpsNode] = []
    for node in nodes:
        skip_reason = None
        if selected_node_id is not None and node.id != selected_node_id:
            skip_reason = "Выбрана другая нода"
        elif node.status != NodeStatus.online.value:
            skip_reason = "Нода не online"

        is_selected = skip_reason is None
        considered.append(
            {
                "id": node.id,
                "name": node.name,
                "ip_address": node.ip_address,
                "status": node.status,
                "selected": is_selected,
                "skip_reason": skip_reason,
            }
        )
        if is_selected:
            selected.append(node)
    return considered, selected


async def run_xray_statsquery(node: VpsNode) -> dict[str, Any]:
    password = decrypt_secret(node.encrypted_ssh_password)
    private_key = decrypt_secret(node.encrypted_private_key)
    async with asyncssh.connect(
        node.ip_address,
        port=node.ssh_port,
        username=node.ssh_username,
        password=password,
        client_keys=[asyncssh.import_private_key(private_key)] if private_key else None,
        known_hosts=None,
    ) as conn:
        result = await conn.run(XRAY_STATS_COMMAND, check=False)
    return {
        "node_id": node.id,
        "command": XRAY_STATS_COMMAND,
        "exit_code": result.exit_status,
        "stdout": result.stdout or "",
        "stderr": result.stderr or "",
        "stdout_preview": (result.stdout or "")[:4000],
        "stderr_preview": (result.stderr or "")[:4000],
    }


async def collect_node_stats(db: Session, node: VpsNode) -> int:
    command_result = await run_xray_statsquery(node)
    if command_result["exit_code"] != 0:
        raise StatsCollectionError(
            "Не удалось получить статистику Xray",
            exit_code=command_result["exit_code"],
            stderr=command_result["stderr"],
        )
    raw_stats = parse_xray_raw_stats(command_result["stdout"])
    stats = parse_user_stats(raw_stats)
    result = apply_xray_stats(db, node, stats)
    return result["updated_users"]


async def collect_traffic(
    db: Session,
    nodes: list[VpsNode],
    selected_node_id: int | None = None,
    *,
    debug: bool = False,
) -> dict[str, Any]:
    nodes_considered, selected_nodes = select_traffic_nodes(nodes, selected_node_id)
    response: dict[str, Any] = {
        "nodes_considered": nodes_considered,
        "selected_nodes": [node.id for node in selected_nodes],
        "commands": [],
        "raw_xray_stats": [],
        "parsed_user_stats": {},
        "akfa_users": [],
        "unmatched_xray_emails": [],
        "akfa_users_without_xray_stats": [],
        "db_committed": False,
        "errors": [],
        "collected_users": 0,
        "updated_users": 0,
        "matched_users": [],
        "message": "",
    }
    if not selected_nodes:
        response["message"] = "Нет установленной активной ноды для сбора статистики"
        response["errors"].append(response["message"])
        return response

    for node in selected_nodes:
        try:
            command_result = await run_xray_statsquery(node)
        except Exception as exc:
            response["commands"].append(
                {
                    "node_id": node.id,
                    "command": XRAY_STATS_COMMAND,
                    "exit_code": None,
                    "stdout_preview": "",
                    "stderr_preview": str(exc),
                }
            )
            response["errors"].append(f"{node.name}: {exc}")
            continue

        response["commands"].append(
            {
                "node_id": node.id,
                "command": command_result["command"],
                "exit_code": command_result["exit_code"],
                "stdout_preview": command_result["stdout_preview"],
                "stderr_preview": command_result["stderr_preview"],
            }
        )
        if command_result["exit_code"] != 0:
            response["errors"].append(
                f"{node.name}: Не удалось получить статистику Xray, exit_code={command_result['exit_code']}"
            )
            continue

        raw_stats = parse_xray_raw_stats(command_result["stdout"])
        node_raw_stats = [{"node_id": node.id, **item} for item in raw_stats]
        response["raw_xray_stats"].extend(node_raw_stats)
        parsed = parse_user_stats(raw_stats)
        merge_user_stats(response["parsed_user_stats"], parsed)
        apply_result = apply_xray_stats(db, node, parsed, commit=False, include_debug=debug)
        response["akfa_users"].extend(apply_result["akfa_users"])
        response["collected_users"] += apply_result["collected_users"]
        response["updated_users"] += apply_result["updated_users"]
        response["matched_users"].extend(apply_result["matched_users"])
        response["unmatched_xray_emails"].extend(apply_result["unmatched_xray_emails"])
        response["akfa_users_without_xray_stats"].extend(apply_result["akfa_users_without_xray_stats"])

    response["matched_users"] = sorted(set(response["matched_users"]))
    response["unmatched_xray_emails"] = sorted(set(response["unmatched_xray_emails"]))
    response["akfa_users_without_xray_stats"] = sorted(set(response["akfa_users_without_xray_stats"]))
    for email in response["unmatched_xray_emails"]:
        response["errors"].append(f"Xray отдаёт статистику для {email}, но такого активного пользователя нет в AKFA")
    if response["updated_users"] == 0 and response["parsed_user_stats"]:
        response["message"] = "Xray вернул статистику, но пользователи AKFA не обновились"
    elif response["updated_users"] == 0 and response["errors"]:
        response["message"] = "Не удалось получить статистику Xray"
    else:
        response["message"] = f"Статистика собрана: обновлено пользователей {response['updated_users']}"
    db.commit()
    response["db_committed"] = True
    return response


def parse_xray_raw_stats(output: str) -> list[dict[str, int | str]]:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return parse_xray_text_stats(output)

    raw_stats: list[dict[str, int | str]] = []
    for item in data.get("stat", []):
        name = str(item.get("name") or "")
        if not USER_TRAFFIC_RE.search(name):
            continue
        try:
            value = int(item.get("value") or 0)
        except (TypeError, ValueError):
            value = 0
        raw_stats.append({"name": name, "value": value})
    return raw_stats


def parse_xray_text_stats(output: str) -> list[dict[str, int | str]]:
    raw_stats: list[dict[str, int | str]] = []
    for name, value in re.findall(r'name:\s*"([^"]+)"\s+value:\s*(\d+)', output):
        if USER_TRAFFIC_RE.search(name):
            raw_stats.append({"name": name, "value": int(value)})
    return raw_stats


def parse_user_stats(raw_stats_or_output: list[dict[str, int | str]] | str) -> dict[str, dict[str, int]]:
    raw_stats = parse_xray_raw_stats(raw_stats_or_output) if isinstance(raw_stats_or_output, str) else raw_stats_or_output
    stats: dict[str, dict[str, int]] = {}
    for item in raw_stats:
        match = USER_TRAFFIC_RE.search(str(item["name"]))
        if not match:
            continue
        username, direction = match.groups()
        key = "upload" if direction == "uplink" else "download"
        stats.setdefault(username, {"upload": 0, "download": 0})[key] = int(item["value"])
    return stats


def parse_xray_stats(output: str) -> dict[str, dict[str, int]]:
    return parse_user_stats(output)


def merge_user_stats(target: dict[str, dict[str, int]], source: dict[str, dict[str, int]]) -> None:
    for username, values in source.items():
        current = target.setdefault(username, {"upload": 0, "download": 0})
        current["upload"] += values.get("upload", 0)
        current["download"] += values.get("download", 0)


def apply_xray_stats(
    db: Session,
    node: VpsNode,
    stats: dict[str, dict[str, int]],
    collected_at: datetime | None = None,
    *,
    commit: bool = True,
    include_debug: bool = False,
) -> dict[str, Any]:
    users = {
        user.username: user
        for user in db.scalars(
            select(VpnUser).where(VpnUser.status.in_([UserStatus.active.value, UserStatus.traffic_limited.value]))
        ).all()
    }
    devices = {
        f"akfa_user_{device.vpn_user_id}_device_{device.id}": device
        for device in db.scalars(
            select(VpnUserDevice).where(VpnUserDevice.status.in_([DeviceStatus.active.value, DeviceStatus.revoked.value]))
        ).all()
    }
    collected_at = collected_at or datetime.now(timezone.utc)
    akfa_users: list[dict[str, Any]] = []
    matched_users: list[str] = []
    updated_users = 0

    handled_device_users: set[int] = set()
    for email, device in devices.items():
        values = stats.get(email)
        if not values:
            continue
        user = device.vpn_user
        before = traffic_user_state(user)
        raw_upload = values.get("upload", 0)
        raw_download = values.get("download", 0)
        update = apply_device_raw_counters(user, device, raw_upload, raw_download, collected_at)
        if update["updated"]:
            updated_users += 1
        matched_users.append(email)
        handled_device_users.add(user.id)
        db.add(
            TrafficSnapshot(
                vpn_user_id=user.id,
                node_id=node.id,
                upload_bytes=update["upload_delta"],
                download_bytes=update["download_delta"],
                total_bytes=update["delta_total"],
            )
        )
        if include_debug:
            akfa_users.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "device_id": device.id,
                    "status": user.status,
                    "matched": True,
                    "before": before,
                    "after": traffic_user_state(user),
                }
            )

    for username, user in users.items():
        if user.id in handled_device_users:
            continue
        before = traffic_user_state(user)
        values = stats.get(username)
        matched = values is not None
        if matched:
            raw_upload = values.get("upload", 0)
            raw_download = values.get("download", 0)
            traffic_row = get_user_node_traffic(db, user, node)
            update = apply_user_node_raw_counters(user, traffic_row, raw_upload, raw_download, collected_at)
            if update["updated"]:
                updated_users += 1
            matched_users.append(username)
            db.add(
                TrafficSnapshot(
                    vpn_user_id=user.id,
                    node_id=node.id,
                    upload_bytes=update["upload_delta"],
                    download_bytes=update["download_delta"],
                    total_bytes=update["delta_total"],
                )
            )
        after = traffic_user_state(user)
        if include_debug or matched:
            akfa_users.append(
                {
                    "id": user.id,
                    "username": user.username,
                    "status": user.status,
                    "deleted": user.status == UserStatus.deleted.value,
                    "matched": matched,
                    "before": before,
                    "after": after,
                }
            )

    unmatched_xray_emails = sorted(username for username in stats if username not in users and username not in devices)
    users_without_stats = sorted(username for username in users if username not in stats)
    if commit:
        db.commit()
    return {
        "collected_users": len(matched_users),
        "updated_users": updated_users,
        "matched_users": matched_users,
        "unmatched_xray_emails": unmatched_xray_emails,
        "akfa_users_without_xray_stats": users_without_stats,
        "akfa_users": akfa_users,
    }


def get_user_node_traffic(db: Session, user: VpnUser, node: VpsNode) -> UserNodeTraffic:
    row = db.scalar(
        select(UserNodeTraffic).where(
            UserNodeTraffic.vpn_user_id == user.id,
            UserNodeTraffic.node_id == node.id,
        )
    )
    if row:
        return row
    use_legacy_baseline = not user.node_traffic
    row = UserNodeTraffic(
        vpn_user=user,
        node_id=node.id,
        last_raw_upload_bytes=(user.last_raw_upload_bytes or 0) if use_legacy_baseline else 0,
        last_raw_download_bytes=(user.last_raw_download_bytes or 0) if use_legacy_baseline else 0,
    )
    db.add(row)
    db.flush()
    return row


def apply_user_node_raw_counters(
    user: VpnUser,
    traffic_row: UserNodeTraffic,
    raw_upload: int,
    raw_download: int,
    collected_at: datetime,
) -> dict[str, int | bool]:
    previous_upload = traffic_row.last_raw_upload_bytes or 0
    previous_download = traffic_row.last_raw_download_bytes or 0
    first_collection = previous_upload == 0 and previous_download == 0

    if first_collection:
        upload_delta = raw_upload
        download_delta = raw_download
    else:
        upload_delta = max(raw_upload - previous_upload, 0)
        download_delta = max(raw_download - previous_download, 0)

    counter_decreased = raw_upload < previous_upload or raw_download < previous_download
    if counter_decreased and not first_collection:
        upload_delta = 0
        download_delta = 0

    delta_total = upload_delta + download_delta
    traffic_row.last_raw_upload_bytes = raw_upload
    traffic_row.last_raw_download_bytes = raw_download
    traffic_row.last_collected_at = collected_at
    user.last_seen_delta_bytes = delta_total
    user.last_traffic_collected_at = collected_at
    if delta_total > 0:
        traffic_row.upload_bytes = (traffic_row.upload_bytes or 0) + upload_delta
        traffic_row.download_bytes = (traffic_row.download_bytes or 0) + download_delta
        traffic_row.total_bytes = (traffic_row.total_bytes or 0) + delta_total
        traffic_row.last_online_at = collected_at
        user.used_upload_bytes = (user.used_upload_bytes or 0) + upload_delta
        user.used_download_bytes = (user.used_download_bytes or 0) + download_delta
        user.used_total_bytes = (user.used_total_bytes or 0) + delta_total
        user.last_online_at = collected_at
    user.last_raw_upload_bytes = sum((row.last_raw_upload_bytes or 0) for row in user.node_traffic)
    user.last_raw_download_bytes = sum((row.last_raw_download_bytes or 0) for row in user.node_traffic)
    if user.traffic_limit_bytes and user.used_total_bytes >= user.traffic_limit_bytes:
        user.status = UserStatus.traffic_limited.value
    return {
        "upload_delta": upload_delta,
        "download_delta": download_delta,
        "delta_total": delta_total,
        "updated": delta_total > 0,
    }


def apply_device_raw_counters(
    user: VpnUser,
    device: VpnUserDevice,
    raw_upload: int,
    raw_download: int,
    collected_at: datetime,
) -> dict[str, int | bool]:
    previous_upload = device.last_raw_upload_bytes or 0
    previous_download = device.last_raw_download_bytes or 0
    first_collection = previous_upload == 0 and previous_download == 0
    upload_delta = raw_upload if first_collection else max(raw_upload - previous_upload, 0)
    download_delta = raw_download if first_collection else max(raw_download - previous_download, 0)
    if (raw_upload < previous_upload or raw_download < previous_download) and not first_collection:
        upload_delta = 0
        download_delta = 0
    delta_total = upload_delta + download_delta
    device.last_raw_upload_bytes = raw_upload
    device.last_raw_download_bytes = raw_download
    device.last_seen_delta_bytes = delta_total
    device.last_seen_at = collected_at if delta_total > 0 else device.last_seen_at
    if delta_total > 0:
        device.upload_bytes = (device.upload_bytes or 0) + upload_delta
        device.download_bytes = (device.download_bytes or 0) + download_delta
        device.total_bytes = (device.total_bytes or 0) + delta_total
        user.used_upload_bytes = (user.used_upload_bytes or 0) + upload_delta
        user.used_download_bytes = (user.used_download_bytes or 0) + download_delta
        user.used_total_bytes = (user.used_total_bytes or 0) + delta_total
        user.last_seen_delta_bytes = delta_total
        user.last_online_at = collected_at
        user.last_traffic_collected_at = collected_at
    user.last_raw_upload_bytes = sum(device.last_raw_upload_bytes or 0 for device in user.devices)
    user.last_raw_download_bytes = sum(device.last_raw_download_bytes or 0 for device in user.devices)
    if user.traffic_limit_bytes and user.used_total_bytes >= user.traffic_limit_bytes:
        user.status = UserStatus.traffic_limited.value
    return {
        "upload_delta": upload_delta,
        "download_delta": download_delta,
        "delta_total": delta_total,
        "updated": delta_total > 0,
    }


def traffic_user_state(user: VpnUser) -> dict[str, Any]:
    return {
        "used_upload_bytes": user.used_upload_bytes or 0,
        "used_download_bytes": user.used_download_bytes or 0,
        "used_total_bytes": user.used_total_bytes or 0,
        "last_raw_upload_bytes": user.last_raw_upload_bytes or 0,
        "last_raw_download_bytes": user.last_raw_download_bytes or 0,
    }


def traffic_overview(db: Session) -> list[dict]:
    snapshots = {
        snapshot.vpn_user_id: snapshot
        for snapshot in db.scalars(select(TrafficSnapshot).order_by(TrafficSnapshot.collected_at)).all()
    }
    rows = []
    for user in db.scalars(
        select(VpnUser)
        .where(VpnUser.status == UserStatus.active.value)
        .order_by(VpnUser.created_at.desc())
    ):
        snapshot = snapshots.get(user.id)
        rows.append(
            {
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "status": user.status,
                "access_status": user.access_status,
                "online_status": user.online_status,
                "upload_bytes": user.used_upload_bytes or 0,
                "download_bytes": user.used_download_bytes or 0,
                "total_bytes": user.used_total_bytes or 0,
                "last_seen_delta_bytes": user.last_seen_delta_bytes or 0,
                "last_online_at": user.last_online_at,
                "last_traffic_collected_at": user.last_traffic_collected_at,
                "traffic_limit_bytes": user.traffic_limit_bytes,
                "devices_label": user.devices_label,
                "active_devices_count": user.active_devices_count,
                "device_limit": user.device_limit,
                "collected": snapshot is not None,
            }
        )
    return rows


def enforce_expiration_and_limits(db: Session) -> int:
    now = datetime.now(timezone.utc)
    changed = 0
    for user in db.scalars(select(VpnUser).where(VpnUser.status == UserStatus.active.value)):
        if user.expires_at and user.expires_at <= now:
            user.status = UserStatus.expired.value
            changed += 1
        elif user.traffic_limit_bytes and user.used_total_bytes >= user.traffic_limit_bytes:
            user.status = UserStatus.traffic_limited.value
            changed += 1
    db.commit()
    return changed
