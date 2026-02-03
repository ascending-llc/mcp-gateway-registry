from pydantic import BaseModel
from typing import Optional, List, Dict, Any


class ToolExecutionRequest(BaseModel):
    """Request to execute a discovered tool"""
    server_id: str
    server_path: str
    tool_name: str
    arguments: Dict[str, Any]


class ToolExecutionResponse(BaseModel):
    """Response from tool execution"""
    success: bool
    server_path: str
    server_id: str
    tool_name: str
    result: Optional[dict] = None
    error: Optional[str] = None
    execution_time_ms: Optional[int] = None


class ResourceReadRequest(BaseModel):
    """Request to read an MCP resource"""
    server_id: str
    resource_uri: str  # e.g., "tavily://search-results/AI"


class ResourceContent(BaseModel):
    """Resource content response"""
    uri: str
    mimeType: str
    text: Optional[str] = None
    blob: Optional[str] = None  # Base64 encoded binary data


class ResourceReadResponse(BaseModel):
    """Response from reading a resource"""
    success: bool
    server_id: str
    server_path: str
    resource_uri: str
    contents: List[ResourceContent]
    error: Optional[str] = None


class PromptExecutionRequest(BaseModel):
    """Request to execute/get an MCP prompt"""
    server_id: str
    prompt_name: str
    arguments: Optional[Dict[str, Any]] = None


class PromptMessage(BaseModel):
    """Prompt message in MCP format"""
    role: str  # "system", "user", "assistant"
    content: Dict[str, Any]  # {"type": "text", "text": "..."}


class PromptExecutionResponse(BaseModel):
    """Response from executing a prompt"""
    success: bool
    server_id: str
    server_path: str
    prompt_name: str
    description: Optional[str] = None
    messages: List[PromptMessage]
    error: Optional[str] = None
