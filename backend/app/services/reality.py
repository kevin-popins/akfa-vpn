import base64
import secrets
import socket
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime

from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from app.models import VpsNode

DEFAULT_REALITY_SNI = "www.googletagmanager.com"
DEFAULT_REALITY_FINGERPRINT = "chrome"
REALITY_FLOW = "xtls-rprx-vision"
REALITY_SECURITY = "reality"
REALITY_NETWORK = "tcp"


def _xray_key(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def generate_reality_key_pair() -> tuple[str, str]:
    private_key = x25519.X25519PrivateKey.generate()
    private_bytes = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    public_bytes = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return _xray_key(private_bytes), _xray_key(public_bytes)


def generate_short_id() -> str:
    return secrets.token_hex(8)


def ensure_reality_credentials(node: VpsNode) -> None:
    if not node.reality_private_key or not node.reality_public_key:
        private_key, public_key = generate_reality_key_pair()
        node.reality_private_key = private_key
        node.reality_public_key = public_key
    if not node.short_id:
        node.short_id = generate_short_id()


@dataclass
class SniCheckResult:
    sni: str
    dns_ok: bool = False
    tcp_443_ok: bool = False
    tls_ok: bool = False
    latency_ms: int | None = None
    certificate_summary: str | None = None
    errors: list[str] = field(default_factory=list)


def check_sni_target(sni: str, timeout: float = 5.0) -> SniCheckResult:
    result = SniCheckResult(sni=sni)
    start = time.perf_counter()
    try:
        addresses = socket.getaddrinfo(sni, 443, type=socket.SOCK_STREAM)
        result.dns_ok = bool(addresses)
    except OSError as exc:
        result.errors.append(f"DNS не разрешился: {exc}")
        return result

    try:
        raw_socket = socket.create_connection((sni, 443), timeout=timeout)
        result.tcp_443_ok = True
    except OSError as exc:
        result.errors.append(f"TCP 443 недоступен: {exc}")
        return result

    try:
        context = ssl.create_default_context()
        with raw_socket:
            with context.wrap_socket(raw_socket, server_hostname=sni) as tls_socket:
                result.tls_ok = True
                result.latency_ms = int((time.perf_counter() - start) * 1000)
                result.certificate_summary = _certificate_summary(tls_socket.getpeercert())
    except (OSError, ssl.SSLError) as exc:
        result.latency_ms = int((time.perf_counter() - start) * 1000)
        result.errors.append(f"TLS handshake не выполнен: {exc}")
    return result


def _certificate_summary(certificate: dict) -> str | None:
    if not certificate:
        return None
    subject = _certificate_name(certificate.get("subject", []))
    issuer = _certificate_name(certificate.get("issuer", []))
    expires = certificate.get("notAfter")
    parts = []
    if subject:
        parts.append(f"CN: {subject}")
    if issuer:
        parts.append(f"Issuer: {issuer}")
    if expires:
        try:
            parsed = datetime.strptime(expires, "%b %d %H:%M:%S %Y %Z")
            parts.append(f"до {parsed.date().isoformat()}")
        except ValueError:
            parts.append(f"до {expires}")
    return "; ".join(parts) if parts else None


def _certificate_name(items: list) -> str | None:
    for group in items:
        for key, value in group:
            if key == "commonName":
                return str(value)
    return None
