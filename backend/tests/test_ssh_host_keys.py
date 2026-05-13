import asyncssh

from app.models import VpsNode
from app.services.ssh_host_keys import NodeHostKeyVerifier


def make_node(fingerprint: str | None = None) -> VpsNode:
    return VpsNode(
        name="node",
        ip_address="203.0.113.10",
        ssh_username="root",
        ssh_host_key_fingerprint=fingerprint,
    )


def test_ssh_host_key_verifier_saves_first_seen_fingerprint():
    node = make_node()
    key = asyncssh.generate_private_key("ssh-ed25519")
    fingerprint = key.get_fingerprint("sha256")

    verifier = NodeHostKeyVerifier(node)
    assert verifier.validate_host_public_key("203.0.113.10", "203.0.113.10", 22, key) is True

    assert node.ssh_host_key_fingerprint == fingerprint
    assert verifier.accepted_new is True


def test_ssh_host_key_verifier_accepts_matching_fingerprint():
    key = asyncssh.generate_private_key("ssh-ed25519")
    node = make_node(key.get_fingerprint("sha256"))

    verifier = NodeHostKeyVerifier(node)
    assert verifier.validate_host_public_key("203.0.113.10", "203.0.113.10", 22, key) is True
    assert verifier.matched_existing is True


def test_ssh_host_key_verifier_rejects_changed_fingerprint():
    trusted_key = asyncssh.generate_private_key("ssh-ed25519")
    changed_key = asyncssh.generate_private_key("ssh-ed25519")
    node = make_node(trusted_key.get_fingerprint("sha256"))

    verifier = NodeHostKeyVerifier(node)
    assert verifier.validate_host_public_key("203.0.113.10", "203.0.113.10", 22, changed_key) is False
    assert node.ssh_host_key_fingerprint == trusted_key.get_fingerprint("sha256")
