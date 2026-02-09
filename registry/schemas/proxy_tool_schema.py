from typing import Any

from pydantic import BaseModel


class ToolExecutionRequest(BaseModel):
    """Request to execute a discovered tool"""

    server_id: str
    server_path: str
    tool_name: str
    arguments: dict[str, Any]


class ToolExecutionResponse(BaseModel):
    """Response from tool execution"""

    success: bool
    server_path: str
    server_id: str
    tool_name: str
    result: dict | None = None
    error: str | None = None
    execution_time_ms: int | None = None


class ResourceReadRequest(BaseModel):
    """Request to read an MCP resource"""

    server_id: str
    resource_uri: str  # e.g., "tavily://search-results/AI"


class ResourceContent(BaseModel):
    """Resource content response"""

    uri: str
    mimeType: str
    text: str | None = None
    blob: str | None = None  # Base64 encoded binary data


class ResourceReadResponse(BaseModel):
    """Response from reading a resource"""

    success: bool
    server_id: str
    server_path: str
    resource_uri: str
    contents: list[ResourceContent]
    error: str | None = None


class PromptExecutionRequest(BaseModel):
    """Request to execute/get an MCP prompt"""

    server_id: str
    prompt_name: str
    arguments: dict[str, Any] | None = None


class PromptMessage(BaseModel):
    """Prompt message in MCP format"""

    role: str  # "system", "user", "assistant"
    content: dict[str, Any]  # {"type": "text", "text": "..."}


class PromptExecutionResponse(BaseModel):
    """Response from executing a prompt"""

    success: bool
    server_id: str
    server_path: str
    prompt_name: str
    description: str | None = None
    messages: list[PromptMessage]
    error: str | None = None
