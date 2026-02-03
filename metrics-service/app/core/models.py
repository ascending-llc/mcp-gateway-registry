from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MetricType(str, Enum):
    AUTH_REQUEST = "auth_request"
    TOOL_DISCOVERY = "tool_discovery"
    TOOL_EXECUTION = "tool_execution"
    REGISTRY_OPERATION = "registry_operation"
    HEALTH_CHECK = "health_check"
    PROTOCOL_LATENCY = "protocol_latency"
    CUSTOM = "custom"


class Metric(BaseModel):
    type: MetricType
    timestamp: datetime | None = Field(default_factory=datetime.utcnow)
    value: float
    duration_ms: float | None = None
    dimensions: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MetricRequest(BaseModel):
    service: str = Field(..., max_length=50)
    version: str | None = Field(None, max_length=20)
    instance_id: str | None = Field(None, max_length=50)
    metrics: list[Metric]


class MetricResponse(BaseModel):
    status: str
    accepted: int
    rejected: int
    errors: list[str] = []
    request_id: str


class ErrorResponse(BaseModel):
    status: str
    error: str
    message: str
    request_id: str
