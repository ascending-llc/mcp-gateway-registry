"""
Pydantic models for token validation and generation.
"""

from typing import Dict, List, Any, Optional
from pydantic import BaseModel


class TokenValidationResponse(BaseModel):
    """Response model for token validation"""
    valid: bool
    scopes: List[str] = []
    error: Optional[str] = None
    method: Optional[str] = None
    client_id: Optional[str] = None
    username: Optional[str] = None


class GenerateTokenRequest(BaseModel):
    """Request model for token generation"""
    user_context: Dict[str, Any]
    requested_scopes: List[str] = []
    expires_in_hours: int = 8  # Will be updated from server DEFAULT_TOKEN_LIFETIME_HOURS
    description: Optional[str] = None


class GenerateTokenResponse(BaseModel):
    """Response model for token generation"""
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "Bearer"
    expires_in: int
    refresh_expires_in: Optional[int] = None
    scope: str
    issued_at: int
    description: Optional[str] = None
