import json
import re
from datetime import datetime, timezone
from typing import Any

import asyncssh
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decrypt_secret
from app.models import NodeStatus, UserStatus, VpsNode, VpnUser
from app.services.traffic import XRAY_STATS_COMMAND

INBOUND_TRAFFIC_RE = re.compile(r"inbound>>>([^>]+)>>>traffic>>>(uplink|downlink)")
CPU_SAMPLE_COMMAND = "cat /proc/stat; echo AKFA_CPU_SAMPLE; sleep 0.2; cat /proc/stat"
RAM_COMMAND = "free -b"
DISK_COMMAND = "df -B1 /"
IGNORED_INBOUND_TAGS = {"api-in", "api"}


async def collect_nodes_metrics(db: Session, nodes: list[VpsNode]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in nodes:
        rows.append(await collect_node_metrics(db, node))
    db.commit()
    return rows


async def collect_node_metrics(db: Session, node: VpsNode) -> dict[str, Any]:
    row = base_metric_row(node)
    if node.status != NodeStatus.online.value:
        row["errors"].append("Нода не online")
        return row
    try:
        command_outputs = await run_node_metric_commands(node)
        cpu_percent = parse_cpu_percent(command_outputs.get("cpu", ""))
        ram = parse_free_output(command_outputs.get("ram", ""))
        disk = parse_df_output(command_outputs.get("disk", ""))
        inbound_raw = parse_inbound_stats(command_outputs.get("xray", ""))
        collected_at = datetime.now(timezone.utc)
        if inbound_raw["upload"] > 0 or inbound_raw["download"] > 0:
            apply_node_raw_counters(node, inbound_raw["upload"], inbound_raw["download"], collected_at)
            traffic_source = "xray_inbound"
        else:
            apply_user_sum_fallback(db, node, collected_at)
            traffic_source = "users_sum_fallback"
        row.update(
            {
                "cpu_percent": cpu_percent,
                **ram,
                **disk,
                "traffic_upload_bytes": node.traffic_upload_bytes or 0,
                "traffic_download_bytes": node.traffic_download_bytes or 0,
                "traffic_total_bytes": node.traffic_total_bytes or 0,
                "traffic_source": traffic_source,
                "last_checked_at": node.last_metrics_collected_at,
            }
        )
    except Exception as exc:
        row["errors"].append(str(exc))
    return row


async def run_node_metric_commands(node: VpsNode) -> dict[str, str]:
    password = decrypt_secret(node.encrypted_ssh_password)
    private_key = decrypt_secret(node.encrypted_private_key)
    outputs: dict[str, str] = {}
    async with asyncssh.connect(
        node.ip_address,
        port=node.ssh_port,
        username=node.ssh_username,
        password=password,
        client_keys=[asyncssh.import_private_key(private_key)] if private_key else None,
        known_hosts=None,
    ) as conn:
        for key, command in {
            "cpu": CPU_SAMPLE_COMMAND,
            "ram": RAM_COMMAND,
            "disk": DISK_COMMAND,
            "xray": XRAY_STATS_COMMAND,
        }.items():
            result = await conn.run(command, check=False)
            if result.exit_status != 0:
                outputs[key] = ""
                outputs[f"{key}_error"] = result.stderr or f"exit_code={result.exit_status}"
            else:
                outputs[key] = result.stdout or ""
    return outputs


def base_metric_row(node: VpsNode) -> dict[str, Any]:
    return {
        "node_id": node.id,
        "name": node.name,
        "ip_address": node.ip_address,
        "status": node.status,
        "cpu_percent": None,
        "ram_used_bytes": None,
        "ram_total_bytes": None,
        "ram_percent": None,
        "disk_used_bytes": None,
        "disk_total_bytes": None,
        "disk_percent": None,
        "traffic_upload_bytes": node.traffic_upload_bytes or 0,
        "traffic_download_bytes": node.traffic_download_bytes or 0,
        "traffic_total_bytes": node.traffic_total_bytes or 0,
        "traffic_source": "xray_inbound" if (node.last_raw_inbound_upload_bytes or node.last_raw_inbound_download_bytes) else "users_sum_fallback",
        "last_checked_at": node.last_metrics_collected_at,
        "errors": [],
    }


def parse_cpu_percent(output: str) -> float | None:
    parts = output.split("AKFA_CPU_SAMPLE")
    if len(parts) != 2:
        return None
    first = parse_cpu_line(parts[0])
    second = parse_cpu_line(parts[1])
    if not first or not second:
        return None
    total_delta = second["total"] - first["total"]
    idle_delta = second["idle"] - first["idle"]
    if total_delta <= 0:
        return None
    return round(max(0.0, min(100.0, (1 - idle_delta / total_delta) * 100)), 1)


def parse_cpu_line(output: str) -> dict[str, int] | None:
    for line in output.splitlines():
        if line.startswith("cpu "):
            values = [int(value) for value in line.split()[1:]]
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            return {"total": sum(values), "idle": idle}
    return None


def parse_free_output(output: str) -> dict[str, int | float | None]:
    for line in output.splitlines():
        if line.startswith("Mem:"):
            parts = line.split()
            total = int(parts[1])
            used = int(parts[2])
            percent = round((used / total) * 100, 1) if total else 0.0
            return {"ram_total_bytes": total, "ram_used_bytes": used, "ram_percent": percent}
    return {"ram_total_bytes": None, "ram_used_bytes": None, "ram_percent": None}


def parse_df_output(output: str) -> dict[str, int | float | None]:
    lines = [line for line in output.splitlines() if line.strip()]
    if len(lines) < 2:
        return {"disk_total_bytes": None, "disk_used_bytes": None, "disk_percent": None}
    parts = lines[1].split()
    total = int(parts[1])
    used = int(parts[2])
    percent = round((used / total) * 100, 1) if total else 0.0
    return {"disk_total_bytes": total, "disk_used_bytes": used, "disk_percent": percent}


def parse_inbound_stats(output: str) -> dict[str, int]:
    raw_stats = parse_inbound_raw_stats(output)
    totals = {"upload": 0, "download": 0}
    for item in raw_stats:
        match = INBOUND_TRAFFIC_RE.search(str(item["name"]))
        if not match:
            continue
        tag, direction = match.groups()
        if tag in IGNORED_INBOUND_TAGS:
            continue
        key = "upload" if direction == "uplink" else "download"
        totals[key] += int(item["value"])
    return totals


def parse_inbound_raw_stats(output: str) -> list[dict[str, int | str]]:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return [
            {"name": name, "value": int(value)}
            for name, value in re.findall(r'name:\s*"([^"]+)"\s+value:\s*(\d+)', output)
            if INBOUND_TRAFFIC_RE.search(name)
        ]
    raw_stats: list[dict[str, int | str]] = []
    for item in data.get("stat", []):
        name = str(item.get("name") or "")
        if not INBOUND_TRAFFIC_RE.search(name):
            continue
        raw_stats.append({"name": name, "value": int(item.get("value") or 0)})
    return raw_stats


def apply_node_raw_counters(node: VpsNode, raw_upload: int, raw_download: int, collected_at: datetime) -> dict[str, int]:
    previous_upload = node.last_raw_inbound_upload_bytes or 0
    previous_download = node.last_raw_inbound_download_bytes or 0
    first_collection = previous_upload == 0 and previous_download == 0
    if first_collection:
        upload_delta = raw_upload
        download_delta = raw_download
    else:
        upload_delta = max(raw_upload - previous_upload, 0)
        download_delta = max(raw_download - previous_download, 0)
    if not first_collection and (raw_upload < previous_upload or raw_download < previous_download):
        upload_delta = 0
        download_delta = 0
    node.last_raw_inbound_upload_bytes = raw_upload
    node.last_raw_inbound_download_bytes = raw_download
    node.traffic_upload_bytes = (node.traffic_upload_bytes or 0) + upload_delta
    node.traffic_download_bytes = (node.traffic_download_bytes or 0) + download_delta
    node.traffic_total_bytes = (node.traffic_total_bytes or 0) + upload_delta + download_delta
    node.last_metrics_collected_at = collected_at
    return {"upload_delta": upload_delta, "download_delta": download_delta, "delta_total": upload_delta + download_delta}


def apply_user_sum_fallback(db: Session, node: VpsNode, collected_at: datetime) -> None:
    upload = db.scalar(
        select(VpnUser.used_upload_bytes).where(VpnUser.status == UserStatus.active.value).limit(1)
    )
    if upload is None:
        node.last_metrics_collected_at = collected_at
        return
    users = db.scalars(select(VpnUser).where(VpnUser.status == UserStatus.active.value)).all()
    node.traffic_upload_bytes = sum(user.used_upload_bytes or 0 for user in users)
    node.traffic_download_bytes = sum(user.used_download_bytes or 0 for user in users)
    node.traffic_total_bytes = sum(user.used_total_bytes or 0 for user in users)
    node.last_metrics_collected_at = collected_at
