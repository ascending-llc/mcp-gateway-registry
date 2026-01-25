from pydantic import BaseModel
from typing import Optional
class ToolExecutionRequest(BaseModel):
    """Request to execute a discovered tool"""
    server_id: str
    server_path: str
    tool_name: str
    arguments: dict


class ToolExecutionResponse(BaseModel):
    """Response from tool execution"""
    success: bool
    server_path: str
    server_id: str
    tool_name: str
    result: Optional[dict] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None
