import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import asyncssh

from app.core.security import decrypt_secret, mask_secret
from app.models import NodeManagedMode, NodeStatus, VpsNode
from app.schemas.entities import XrayProbeResponse
from app.services.ssh_installer import SSH_COMMAND_TIMEOUT_SECONDS, SSH_CONNECT_TIMEOUT_SECONDS


READ_ONLY_PROBE_COMMANDS = [
    "command -v xray",
    "xray version",
    "systemctl is-active xray",
    "systemctl is-enabled xray",
    "test -f /usr/local/etc/xray/config.json",
    "cat /usr/local/etc/xray/config.json",
]


async def probe_xray(node: VpsNode) -> XrayProbeResponse:
    logs: list[dict[str, Any]] = []

    async def run(conn: asyncssh.SSHClientConnection, command: str, allow_failure: bool = True):
        logs.append({"command": command, "mutating": False, "message": "read-only probe"})
        result = await asyncio.wait_for(
            conn.run(command, check=False),
            timeout=SSH_COMMAND_TIMEOUT_SECONDS,
        )
        logs.append(
            {
                "command": command,
                "mutating": False,
                "exit_code": result.exit_status,
                "stdout": mask_secret((result.stdout or "")[:4000]),
                "stderr": mask_secret((result.stderr or "")[:4000]),
            }
        )
        if result.exit_status != 0 and not allow_failure:
            raise RuntimeError(command)
        return result

    try:
        async with await _connect(node) as conn:
            command_path = await run(conn, "command -v xray")
            version = await run(conn, "xray version")
            active = await run(conn, f"systemctl is-active {node.xray_service_name}")
            enabled = await run(conn, f"systemctl is-enabled {node.xray_service_name}")
            exists = await run(conn, f"test -f {node.xray_config_path}")
            config_result = await run(conn, f"cat {node.xray_config_path}")
            response = XrayProbeResponse(
                ssh_ok=True,
                xray_installed=command_path.exit_status == 0,
                xray_version=(version.stdout or "").splitlines()[0] if version.stdout else None,
                service_active=(active.stdout or "").strip() == "active",
                service_enabled=(enabled.stdout or "").strip() == "enabled",
                config_found=exists.exit_status == 0,
                logs=logs,
            )
            if config_result.exit_status == 0 and config_result.stdout:
                _parse_config(response, config_result.stdout)
            if response.private_key and not response.public_key:
                pub = await run(conn, f"xray x25519 -i {response.private_key}")
                response.public_key = _extract_public_key(pub.stdout or "")
            response.public_key_missing = bool(response.reality_inbound_found and not response.public_key)
            response.manual_public_key_required = response.public_key_missing
            response.partial_import_required = response.public_key_missing
            return response
    except Exception as exc:
        return XrayProbeResponse(ssh_ok=False, error=mask_secret(str(exc)), logs=logs)


def _parse_config(response: XrayProbeResponse, raw: str) -> None:
    try:
        config = json.loads(raw)
    except json.JSONDecodeError as exc:
        response.config_found = True
        response.config_valid = False
        response.error = f"config invalid: {exc}"
        return
    response.config_valid = True
    response.raw_config = config
    inbound = find_reality_inbound(config)
    if not inbound:
        return
    settings = inbound.get("settings") or {}
    stream = inbound.get("streamSettings") or {}
    reality = stream.get("realitySettings") or {}
    response.reality_inbound_found = True
    response.inbound = inbound
    response.inbound_tag = inbound.get("tag")
    response.listen = inbound.get("listen")
    response.port = inbound.get("port")
    response.clients_count = len(settings.get("clients") or [])
    response.server_names = reality.get("serverNames") or []
    response.dest = reality.get("dest")
    response.private_key = reality.get("privateKey")
    response.public_key = reality.get("publicKey")
    response.short_ids = reality.get("shortIds") or []
    response.network = stream.get("network")
    response.security = stream.get("security")


def find_reality_inbound(config: dict[str, Any]) -> dict[str, Any] | None:
    for inbound in config.get("inbounds") or []:
        stream = inbound.get("streamSettings") or {}
        if inbound.get("protocol") == "vless" and stream.get("realitySettings"):
            return inbound
    return None


def _extract_public_key(output: str) -> str | None:
    for line in output.splitlines():
        if "Public key:" in line:
            return line.split("Public key:", 1)[1].strip()
    stripped = output.strip()
    return stripped if stripped and "\n" not in stripped else None


def import_probe_to_node(node: VpsNode, probe: XrayProbeResponse, public_key: str | None = None) -> None:
    if not probe.reality_inbound_found or not probe.inbound:
        raise ValueError("Reality inbound не найден")
    resolved_public_key = public_key or probe.public_key
    if not resolved_public_key:
        raise ValueError("Reality publicKey обязателен для импорта")
    node.xray_installed = bool(probe.xray_installed)
    node.managed_mode = NodeManagedMode.imported_safe.value
    node.import_status = "imported"
    node.inbound_tag = probe.inbound_tag or "vless-reality"
    node.vless_port = int(probe.port or node.vless_port)
    node.sni = (probe.server_names[0] if probe.server_names else node.sni)
    node.reality_private_key = probe.private_key or node.reality_private_key
    node.reality_public_key = resolved_public_key
    node.short_id = (probe.short_ids[0] if probe.short_ids else node.short_id)
    node.imported_config = probe.raw_config
    node.imported_inbound = probe.inbound
    node.status = NodeStatus.online.value if probe.service_active else node.status
    node.last_check_at = datetime.now(timezone.utc)


async def _connect(node: VpsNode) -> asyncssh.SSHClientConnection:
    password = decrypt_secret(node.encrypted_ssh_password)
    private_key = decrypt_secret(node.encrypted_private_key)
    return await asyncio.wait_for(
        asyncssh.connect(
            node.ip_address,
            port=node.ssh_port,
            username=node.ssh_username,
            password=password,
            client_keys=[asyncssh.import_private_key(private_key)] if private_key else None,
            known_hosts=None,
        ),
        timeout=SSH_CONNECT_TIMEOUT_SECONDS,
    )
