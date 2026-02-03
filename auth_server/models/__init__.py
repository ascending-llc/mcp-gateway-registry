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
    "DeviceApprovalRequest",
    "DeviceCodeRequest",
    "DeviceCodeResponse",
    "DeviceTokenRequest",
    "DeviceTokenResponse",
    "GenerateTokenRequest",
    "GenerateTokenResponse",
    "TokenValidationResponse",
]
