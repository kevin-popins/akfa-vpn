from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


JsonColumn = JSONB().with_variant(JSON(), "sqlite")


class AdminRole(StrEnum):
    super_admin = "super_admin"
    admin = "admin"
    read_only = "read_only"


class NodeStatus(StrEnum):
    draft = "draft"
    checking = "checking"
    online = "online"
    offline = "offline"
    installing = "installing"
    failed = "failed"


class AuthType(StrEnum):
    password = "password"
    private_key = "private_key"


class RoutingMode(StrEnum):
    full_tunnel = "full_tunnel"
    ru_direct = "ru_direct"
    custom_direct_domains = "custom_direct_domains"


class ClientTemplate(StrEnum):
    vless_uri = "vless_uri"
    sing_box = "sing_box"
    xray_json = "xray_json"


class UserStatus(StrEnum):
    active = "active"
    disabled = "disabled"
    expired = "expired"
    traffic_limited = "traffic_limited"
    deleted = "deleted"


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default=AdminRole.admin.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccessProfile(Base):
    __tablename__ = "access_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    routing_mode: Mapped[str] = mapped_column(String(64), default=RoutingMode.ru_direct.value)
    direct_domains: Mapped[list[str]] = mapped_column(JsonColumn, default=list)
    blocked_domains: Mapped[list[str]] = mapped_column(JsonColumn, default=list)
    traffic_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    expires_in_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allowed_nodes: Mapped[list[int]] = mapped_column(JsonColumn, default=list)
    client_template: Mapped[str] = mapped_column(String(32), default=ClientTemplate.vless_uri.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    departments: Mapped[list["Department"]] = relationship(back_populates="default_access_profile")
    users: Mapped[list["VpnUser"]] = relationship(back_populates="access_profile")


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_access_profile_id: Mapped[int | None] = mapped_column(ForeignKey("access_profiles.id"), nullable=True)

    default_access_profile: Mapped[AccessProfile | None] = relationship(back_populates="departments")
    users: Mapped[list["VpnUser"]] = relationship(back_populates="department")


class VpsNode(Base):
    __tablename__ = "vps_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    ip_address: Mapped[str] = mapped_column(String(64), index=True)
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    ssh_username: Mapped[str] = mapped_column(String(120))
    ssh_auth_type: Mapped[str] = mapped_column(String(32), default=AuthType.password.value)
    encrypted_ssh_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_private_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    public_host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vless_port: Mapped[int] = mapped_column(Integer, default=443)
    sni: Mapped[str] = mapped_column(String(255), default="www.googletagmanager.com")
    reality_private_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reality_public_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    short_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(32), default="chrome")
    xray_config_path: Mapped[str] = mapped_column(String(255), default="/usr/local/etc/xray/config.json")
    xray_service_name: Mapped[str] = mapped_column(String(80), default="xray")
    status: Mapped[str] = mapped_column(String(32), default=NodeStatus.draft.value)
    last_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    install_log: Mapped[list[dict[str, Any]]] = mapped_column(JsonColumn, default=list)
    last_raw_inbound_upload_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    last_raw_inbound_download_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    traffic_upload_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    traffic_download_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    traffic_total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    last_metrics_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_config_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_config_apply_status: Mapped[str] = mapped_column(String(32), default="pending")
    last_config_apply_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_config_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user_links: Mapped[list["VpnUserNode"]] = relationship(back_populates="node", cascade="all, delete-orphan")
    snapshots: Mapped[list["TrafficSnapshot"]] = relationship(back_populates="node")


class VpnUser(Base):
    __tablename__ = "vpn_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(120))
    last_name: Mapped[str] = mapped_column(String(120))
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    access_profile_id: Mapped[int | None] = mapped_column(ForeignKey("access_profiles.id"), nullable=True)
    primary_node_id: Mapped[int | None] = mapped_column(ForeignKey("vps_nodes.id"), nullable=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True)
    subscription_token: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    traffic_limit_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    used_upload_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    used_download_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    used_total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    last_raw_upload_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    last_raw_download_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    last_seen_delta_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    last_traffic_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_online_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=UserStatus.active.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    department: Mapped[Department | None] = relationship(back_populates="users")
    access_profile: Mapped[AccessProfile | None] = relationship(back_populates="users")
    node_links: Mapped[list["VpnUserNode"]] = relationship(back_populates="vpn_user", cascade="all, delete-orphan")
    allowed_nodes: Mapped[list[VpsNode]] = relationship(secondary="vpn_user_nodes", viewonly=True)
    primary_node: Mapped[VpsNode | None] = relationship(foreign_keys=[primary_node_id])
    node_traffic: Mapped[list["UserNodeTraffic"]] = relationship(back_populates="vpn_user", cascade="all, delete-orphan")
    snapshots: Mapped[list["TrafficSnapshot"]] = relationship(back_populates="vpn_user")

    @property
    def allowed_node_ids(self) -> list[int]:
        return [link.node_id for link in self.node_links]

    @property
    def access_status(self) -> str:
        return self.status

    @property
    def online_status(self) -> str:
        if not self.last_online_at:
            return "offline"
        now = datetime.now(self.last_online_at.tzinfo)
        seconds_since_online = (now - self.last_online_at).total_seconds()
        return "online" if seconds_since_online <= 180 else "offline"


class VpnUserNode(Base):
    __tablename__ = "vpn_user_nodes"
    __table_args__ = (UniqueConstraint("vpn_user_id", "node_id", name="uq_vpn_user_node"),)

    vpn_user_id: Mapped[int] = mapped_column(ForeignKey("vpn_users.id", ondelete="CASCADE"), primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("vps_nodes.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vpn_user: Mapped[VpnUser] = relationship(back_populates="node_links")
    node: Mapped[VpsNode] = relationship(back_populates="user_links")


class TrafficSnapshot(Base):
    __tablename__ = "traffic_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vpn_user_id: Mapped[int] = mapped_column(ForeignKey("vpn_users.id"))
    node_id: Mapped[int] = mapped_column(ForeignKey("vps_nodes.id"))
    upload_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    download_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vpn_user: Mapped[VpnUser] = relationship(back_populates="snapshots")
    node: Mapped[VpsNode] = relationship(back_populates="snapshots")


class UserNodeTraffic(Base):
    __tablename__ = "user_node_traffic"
    __table_args__ = (UniqueConstraint("vpn_user_id", "node_id", name="uq_user_node_traffic"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vpn_user_id: Mapped[int] = mapped_column(ForeignKey("vpn_users.id", ondelete="CASCADE"))
    node_id: Mapped[int] = mapped_column(ForeignKey("vps_nodes.id", ondelete="CASCADE"))
    upload_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    download_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    total_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    last_raw_upload_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    last_raw_download_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    last_online_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    vpn_user: Mapped[VpnUser] = relationship(back_populates="node_traffic")
    node: Mapped[VpsNode] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("admins.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(120))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JsonColumn, default=dict)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
