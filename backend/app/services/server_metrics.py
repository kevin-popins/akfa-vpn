import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncssh
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import NodeStatus, TrafficSnapshot, VpsNode
from app.services.ssh_host_keys import ssh_connection_options
from app.services.traffic import XRAY_STATS_COMMAND

INBOUND_TRAFFIC_RE = re.compile(r"inbound>>>([^>]+)>>>traffic>>>(uplink|downlink)")
CPU_SAMPLE_COMMAND = "cat /proc/stat; echo AKFA_CPU_SAMPLE; sleep 0.2; cat /proc/stat"
RAM_COMMAND = "free -b"
DISK_COMMAND = "df -B1 /"
NETWORK_COMMAND = "ip route show default 2>/dev/null | awk 'NR==1 {for (i=1;i<=NF;i++) if ($i==\"dev\") {print $(i+1); exit}}'; echo AKFA_NET_DEV; cat /proc/net/dev"
IGNORED_INBOUND_TAGS = {"api-in", "api"}
IGNORED_NETWORK_INTERFACES = ("lo", "docker", "br-", "veth", "virbr", "zt", "tailscale")


async def collect_nodes_metrics(db: Session, nodes: list[VpsNode], period: str = "all") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in nodes:
        rows.append(await collect_node_metrics(db, node, period))
    db.commit()
    return rows


async def collect_node_metrics(db: Session, node: VpsNode, period: str = "all") -> dict[str, Any]:
    row = base_metric_row(db, node, period)
    if node.status != NodeStatus.online.value:
        row["errors"].append("Нода не online")
        return row
    try:
        command_outputs = await run_node_metric_commands(node)
        cpu_percent = parse_cpu_percent(command_outputs.get("cpu", ""))
        ram = parse_free_output(command_outputs.get("ram", ""))
        disk = parse_df_output(command_outputs.get("disk", ""))
        network = parse_system_network_stats(command_outputs.get("network", ""))
        if command_outputs.get("network_error"):
            network = unavailable_system_network_stats(command_outputs["network_error"])
        inbound_raw = parse_inbound_stats(command_outputs.get("xray", ""))
        collected_at = datetime.now(timezone.utc)
        if inbound_raw["upload"] > 0 or inbound_raw["download"] > 0:
            apply_node_raw_counters(db, node, inbound_raw["upload"], inbound_raw["download"], collected_at)
            traffic_source = "xray_inbound"
        else:
            node.last_metrics_collected_at = collected_at
            traffic_source = "node_traffic"
        traffic = aggregate_node_traffic(db, node.id, period)
        row.update(
            {
                "cpu_percent": cpu_percent,
                **ram,
                **disk,
                "vpn_traffic_upload_bytes": traffic["upload"],
                "vpn_traffic_download_bytes": traffic["download"],
                "vpn_traffic_total_bytes": traffic["total"],
                "vpn_traffic_source": "xray_stats",
                "traffic_upload_bytes": traffic["upload"],
                "traffic_download_bytes": traffic["download"],
                "traffic_total_bytes": traffic["total"],
                "traffic_type": "vpn_xray",
                "traffic_source": traffic_source,
                **network,
                "last_checked_at": node.last_metrics_collected_at,
            }
        )
    except Exception as exc:
        row["errors"].append(str(exc))
    return row


async def run_node_metric_commands(node: VpsNode) -> dict[str, str]:
    _, options = ssh_connection_options(node)
    outputs: dict[str, str] = {}
    async with asyncssh.connect(
        node.ip_address,
        **options,
    ) as conn:
        for key, command in {
            "cpu": CPU_SAMPLE_COMMAND,
            "ram": RAM_COMMAND,
            "disk": DISK_COMMAND,
            "network": NETWORK_COMMAND,
            "xray": XRAY_STATS_COMMAND,
        }.items():
            result = await conn.run(command, check=False)
            if result.exit_status != 0:
                outputs[key] = ""
                outputs[f"{key}_error"] = result.stderr or f"exit_code={result.exit_status}"
            else:
                outputs[key] = result.stdout or ""
    return outputs


def base_metric_row(db: Session, node: VpsNode, period: str = "all") -> dict[str, Any]:
    traffic = aggregate_node_traffic(db, node.id, period)
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
        "vpn_traffic_upload_bytes": traffic["upload"],
        "vpn_traffic_download_bytes": traffic["download"],
        "vpn_traffic_total_bytes": traffic["total"],
        "vpn_traffic_source": "xray_stats",
        "traffic_upload_bytes": traffic["upload"],
        "traffic_download_bytes": traffic["download"],
        "traffic_total_bytes": traffic["total"],
        "traffic_type": "vpn_xray",
        "traffic_source": "node_traffic",
        "system_traffic_upload_bytes": None,
        "system_traffic_download_bytes": None,
        "system_traffic_total_bytes": None,
        "system_traffic_source": "unavailable",
        "system_traffic_interface": None,
        "system_traffic_available": False,
        "system_traffic_error": "Нода не online" if node.status != NodeStatus.online.value else None,
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


def parse_system_network_stats(output: str) -> dict[str, int | str | bool | None]:
    default_iface = None
    proc_output = output
    if "AKFA_NET_DEV" in output:
        before, proc_output = output.split("AKFA_NET_DEV", 1)
        default_iface = before.strip().splitlines()[-1].strip() if before.strip() else None
    interfaces: dict[str, dict[str, int]] = {}
    for line in proc_output.splitlines():
        if ":" not in line:
            continue
        name, values = line.split(":", 1)
        iface = name.strip()
        parts = values.split()
        if len(parts) < 16:
            continue
        interfaces[iface] = {"download": int(parts[0]), "upload": int(parts[8])}
    selected = default_iface if default_iface in interfaces else None
    if selected is None:
        candidates = [
            iface
            for iface in interfaces
            if not any(iface == ignored or iface.startswith(ignored) for ignored in IGNORED_NETWORK_INTERFACES)
        ]
        if len(candidates) == 1:
            selected = candidates[0]
    if selected is None:
        return unavailable_system_network_stats("Не удалось определить сетевой интерфейс VPS")
    download = interfaces[selected]["download"]
    upload = interfaces[selected]["upload"]
    return {
        "system_traffic_upload_bytes": upload,
        "system_traffic_download_bytes": download,
        "system_traffic_total_bytes": upload + download,
        "system_traffic_source": "host_proc_net_dev",
        "system_traffic_interface": selected,
        "system_traffic_available": True,
        "system_traffic_error": None,
    }


def unavailable_system_network_stats(error: str | None = None) -> dict[str, int | str | bool | None]:
    return {
        "system_traffic_upload_bytes": None,
        "system_traffic_download_bytes": None,
        "system_traffic_total_bytes": None,
        "system_traffic_source": "unavailable",
        "system_traffic_interface": None,
        "system_traffic_available": False,
        "system_traffic_error": error or "Не удалось получить общий трафик VPS",
    }


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


def apply_node_raw_counters(db_or_node: Session | VpsNode, node_or_upload: VpsNode | int, raw_upload_or_download: int, raw_download_or_collected_at: int | datetime, collected_at: datetime | None = None) -> dict[str, int]:
    if isinstance(db_or_node, Session):
        db: Session | None = db_or_node
        node = node_or_upload
        raw_upload = int(raw_upload_or_download)
        raw_download = int(raw_download_or_collected_at)
        collected = collected_at or datetime.now(timezone.utc)
    else:
        db = None
        node = db_or_node
        raw_upload = int(node_or_upload)
        raw_download = int(raw_upload_or_download)
        collected = raw_download_or_collected_at if isinstance(raw_download_or_collected_at, datetime) else datetime.now(timezone.utc)
    assert isinstance(node, VpsNode)
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
    node.last_metrics_collected_at = collected
    if db is not None and upload_delta + download_delta > 0:
        db.add(
            TrafficSnapshot(
                vpn_user_id=None,
                node_id=node.id,
                upload_bytes=upload_delta,
                download_bytes=download_delta,
                total_bytes=upload_delta + download_delta,
                collected_at=collected,
            )
        )
    return {"upload_delta": upload_delta, "download_delta": download_delta, "delta_total": upload_delta + download_delta}


def period_start(period: str, now: datetime | None = None) -> datetime | None:
    now = now or datetime.now(timezone.utc)
    if period == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period in {"7d", "week"}:
        return now - timedelta(days=7)
    if period in {"month", "this_month"}:
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return None


def aggregate_node_traffic(db: Session, node_id: int, period: str = "all") -> dict[str, int]:
    query = select(
        func.coalesce(func.sum(TrafficSnapshot.upload_bytes), 0),
        func.coalesce(func.sum(TrafficSnapshot.download_bytes), 0),
        func.coalesce(func.sum(TrafficSnapshot.total_bytes), 0),
    ).where(TrafficSnapshot.node_id == node_id)
    start = period_start(period)
    if start is not None:
        query = query.where(TrafficSnapshot.collected_at >= start)
    upload, download, total = db.execute(query).one()
    return {"upload": int(upload or 0), "download": int(download or 0), "total": int(total or 0)}
