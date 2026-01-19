"""
Pydantic models for auth server.
"""

from .device_flow import (
    DeviceCodeRequest,
    DeviceCodeResponse,
    DeviceApprovalRequest,
    DeviceTokenRequest,
    DeviceTokenResponse
)

from .tokens import (
    TokenValidationResponse,
    GenerateTokenRequest,
    GenerateTokenResponse
)

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
