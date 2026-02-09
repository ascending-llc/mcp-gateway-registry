"""
Pydantic models for auth server.
"""

from .device_flow import (
    DeviceApprovalRequest,
    DeviceCodeRequest,
    DeviceCodeResponse,
    DeviceTokenRequest,
    DeviceTokenResponse,
)
from .tokens import GenerateTokenRequest, GenerateTokenResponse, TokenValidationResponse

__all__ = [
    "DeviceCodeRequest",
    "DeviceCodeResponse",
    "DeviceApprovalRequest",
    "DeviceTokenRequest",
    "DeviceTokenResponse",
    "TokenValidationResponse",
    "GenerateTokenRequest",
    "GenerateTokenResponse",
]
