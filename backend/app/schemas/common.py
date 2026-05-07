from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    message: str
    diagnostics: str | None = None
    apply_status: "ConfigApplySummaryRead | None" = None


class NodeApplyResultRead(BaseModel):
    node_id: int
    node_name: str
    ok: bool
    status: str
    error: str | None = None
    applied_at: str | None = None
    config_version: str | None = None


class ConfigApplySummaryRead(BaseModel):
    ok: bool
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[NodeApplyResultRead] = Field(default_factory=list)


class InstallLogEntry(BaseModel):
    at: datetime
    level: str = "info"
    command: str | None = None
    message: str
    output: str | None = None


class DashboardStats(BaseModel):
    nodes_total: int
    nodes_online: int
    users_total: int
    users_active: int
    traffic_total_bytes: int


class AuditLogRead(OrmModel):
    id: int
    admin_id: int | None
    action: str
    entity_type: str
    entity_id: str | None
    metadata: dict[str, Any] = Field(default_factory=dict, validation_alias="metadata_")
    ip_address: str | None
    created_at: datetime
