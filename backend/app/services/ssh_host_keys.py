from __future__ import annotations

from typing import Any

import asyncssh

from app.core.security import decrypt_secret
from app.models import VpsNode


class NodeHostKeyVerifier(asyncssh.SSHClient):
    def __init__(self, node: VpsNode) -> None:
        self.node = node
        self.fingerprint: str | None = None
        self.accepted_new = False
        self.matched_existing = False

    def validate_host_public_key(self, host: str, addr: str, port: int, key: asyncssh.SSHKey) -> bool:
        fingerprint = key.get_fingerprint("sha256")
        self.fingerprint = fingerprint
        expected = (self.node.ssh_host_key_fingerprint or "").strip()
        if expected:
            self.matched_existing = fingerprint == expected
            return self.matched_existing
        self.node.ssh_host_key_fingerprint = fingerprint
        self.accepted_new = True
        return True


def ssh_connection_options(node: VpsNode) -> tuple[NodeHostKeyVerifier, dict[str, Any]]:
    password = decrypt_secret(node.encrypted_ssh_password)
    private_key = decrypt_secret(node.encrypted_private_key)
    verifier = NodeHostKeyVerifier(node)
    return verifier, {
        "port": node.ssh_port,
        "username": node.ssh_username,
        "password": password,
        "client_keys": [asyncssh.import_private_key(private_key)] if private_key else None,
        "known_hosts": b"",
        "client_factory": lambda: verifier,
    }
