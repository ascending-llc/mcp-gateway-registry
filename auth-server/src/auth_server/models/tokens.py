"""
Pydantic models for token validation and generation.
"""

from typing import Any

from pydantic import BaseModel


class TokenValidationResponse(BaseModel):
    """Response model for token validation"""

    valid: bool
    scopes: list[str] = []
    error: str | None = None
    method: str | None = None
    client_id: str | None = None
    username: str | None = None


class GenerateTokenRequest(BaseModel):
    """Request model for token generation"""

    user_context: dict[str, Any]
    requested_scopes: list[str] = []
    expires_in_hours: int = 8  # Will be updated from server DEFAULT_TOKEN_LIFETIME_HOURS
    description: str | None = None


class GenerateTokenResponse(BaseModel):
    """Response model for token generation"""

    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int
    refresh_expires_in: int | None = None
    scope: str
    issued_at: int
    description: str | None = None
