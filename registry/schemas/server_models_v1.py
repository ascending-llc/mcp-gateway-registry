"""
V1版本的Server Management API的Pydantic模型
基于MongoDB Schema定义，仅包含Schema中定义的字段
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


# ================= Transport相关模型 =================
class TransportConfig(BaseModel):
    """传输配置"""
    type: str = Field(..., description="传输类型，如stdio, streamable-http等")
    command: Optional[str] = Field(None, description="命令，用于stdio类型")
    args: Optional[List[str]] = Field(None, description="命令参数")
    env: Optional[Dict[str, str]] = Field(None, description="环境变量")


# ================= OAuth相关模型 =================
class OAuthConfig(BaseModel):
    """OAuth配置"""
    authorization_url: str = Field(..., description="授权URL")
    token_url: str = Field(..., description="Token URL")
    client_id: str = Field(..., description="客户端ID")
    scope: Optional[str] = Field(None, description="OAuth范围")


# ================= Tool相关模型 =================
class ToolSchema(BaseModel):
    """工具Schema定义"""
    name: str = Field(..., description="工具名称")
    description: Optional[str] = Field(None, description="工具描述")
    inputSchema: Optional[Dict[str, Any]] = Field(None, description="输入Schema")


# ================= Server相关模型 =================
class ServerRegisterRequest(BaseModel):
    """注册服务请求"""
    server_name: str = Field(..., description="服务名称")
    path: str = Field(..., description="服务路径")
    description: Optional[str] = Field(None, description="服务描述")
    proxy_pass_url: Optional[str] = Field(None, description="代理URL")
    supported_transports: Optional[List[str]] = Field(default=None, description="支持的传输方式")
    auth_type: Optional[str] = Field(None, description="认证类型")
    auth_provider: Optional[str] = Field(None, description="认证提供者")
    tags: Optional[List[str]] = Field(default_factory=list, description="标签列表")
    num_tools: Optional[int] = Field(0, description="工具数量")
    num_stars: Optional[int] = Field(0, description="星标数量")
    is_python: Optional[bool] = Field(False, description="是否为Python服务")
    license: Optional[str] = Field(None, description="许可证")
    tool_list: Optional[List[ToolSchema]] = Field(default_factory=list, description="工具列表")
    scope: Optional[str] = Field("shared_app", description="访问范围：shared_app, shared_user, private_user")
    user_id: Optional[str] = Field(None, description="用户ID（私有服务）")
    organization_id: Optional[str] = Field(None, description="组织ID")
    startup: Optional[bool] = Field(False, description="是否启动时自动运行")
    icon_path: Optional[str] = Field(None, description="图标路径")
    timeout: Optional[int] = Field(30000, description="超时时间（毫秒）")
    init_timeout: Optional[int] = Field(60000, description="初始化超时时间（毫秒）")
    chat_menu: Optional[bool] = Field(True, description="是否在聊天菜单显示")
    server_instructions: Optional[str] = Field(None, description="服务说明")
    transport: Optional[TransportConfig] = Field(None, description="传输配置")
    requires_oauth: Optional[bool] = Field(False, description="是否需要OAuth")
    oauth: Optional[OAuthConfig] = Field(None, description="OAuth配置")
    custom_user_vars: Optional[Dict[str, Any]] = Field(None, description="自定义用户变量")
    
    @field_validator('tags')
    @classmethod
    def validate_tags_case_insensitive(cls, v: Optional[List[str]]) -> List[str]:
        """验证tags大小写不敏感，将所有tag转为小写，并检查重复"""
        if not v:
            return []
        
        # 转为小写
        lowercase_tags = [tag.lower() for tag in v]
        
        # 检查是否有重复（忽略大小写）
        if len(lowercase_tags) != len(set(lowercase_tags)):
            raise ValueError("tags中存在重复的标签（忽略大小写）")
        
        return lowercase_tags


class ServerUpdateRequest(BaseModel):
    """更新服务请求"""
    description: Optional[str] = Field(None, description="服务描述")
    proxy_pass_url: Optional[str] = Field(None, description="代理URL")
    supported_transports: Optional[List[str]] = Field(None, description="支持的传输方式")
    auth_type: Optional[str] = Field(None, description="认证类型")
    auth_provider: Optional[str] = Field(None, description="认证提供者")
    tags: Optional[List[str]] = Field(None, description="标签列表")
    num_tools: Optional[int] = Field(None, description="工具数量")
    num_stars: Optional[int] = Field(None, description="星标数量")
    is_python: Optional[bool] = Field(None, description="是否为Python服务")
    license: Optional[str] = Field(None, description="许可证")
    tool_list: Optional[List[ToolSchema]] = Field(None, description="工具列表")
    status: Optional[str] = Field(None, description="状态：active, inactive, error")
    startup: Optional[bool] = Field(None, description="是否启动时自动运行")
    icon_path: Optional[str] = Field(None, description="图标路径")
    timeout: Optional[int] = Field(None, description="超时时间（毫秒）")
    init_timeout: Optional[int] = Field(None, description="初始化超时时间（毫秒）")
    chat_menu: Optional[bool] = Field(None, description="是否在聊天菜单显示")
    server_instructions: Optional[str] = Field(None, description="服务说明")
    transport: Optional[TransportConfig] = Field(None, description="传输配置")
    requires_oauth: Optional[bool] = Field(None, description="是否需要OAuth")
    oauth: Optional[OAuthConfig] = Field(None, description="OAuth配置")
    custom_user_vars: Optional[Dict[str, Any]] = Field(None, description="自定义用户变量")
    version: int = Field(..., description="版本号（用于乐观锁）")
    
    @field_validator('tags')
    @classmethod
    def validate_tags_case_insensitive(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """验证tags大小写不敏感"""
        if v is None:
            return None
        
        # 转为小写
        lowercase_tags = [tag.lower() for tag in v]
        
        # 检查是否有重复（忽略大小写）
        if len(lowercase_tags) != len(set(lowercase_tags)):
            raise ValueError("tags中存在重复的标签（忽略大小写）")
        
        return lowercase_tags


class ServerToggleRequest(BaseModel):
    """切换服务状态请求"""
    enabled: bool = Field(..., description="是否启用")


class ServerResponse(BaseModel):
    """服务响应"""
    id: str = Field(..., description="服务ID")
    server_name: str = Field(..., description="服务名称")
    path: str = Field(..., description="服务路径")
    description: Optional[str] = Field(None, description="服务描述")
    proxy_pass_url: Optional[str] = Field(None, description="代理URL")
    supported_transports: Optional[List[str]] = Field(None, description="支持的传输方式")
    auth_type: Optional[str] = Field(None, description="认证类型")
    auth_provider: Optional[str] = Field(None, description="认证提供者")
    tags: Optional[List[str]] = Field(default_factory=list, description="标签列表")
    num_tools: Optional[int] = Field(0, description="工具数量")
    num_stars: Optional[int] = Field(0, description="星标数量")
    is_python: Optional[bool] = Field(False, description="是否为Python服务")
    license: Optional[str] = Field(None, description="许可证")
    tool_list: Optional[List[ToolSchema]] = Field(default_factory=list, description="工具列表")
    scope: Optional[str] = Field("shared_app", description="访问范围")
    user_id: Optional[str] = Field(None, description="用户ID")
    organization_id: Optional[str] = Field(None, description="组织ID")
    startup: Optional[bool] = Field(False, description="是否启动时自动运行")
    icon_path: Optional[str] = Field(None, description="图标路径")
    timeout: Optional[int] = Field(None, description="超时时间（毫秒）")
    init_timeout: Optional[int] = Field(None, description="初始化超时时间（毫秒）")
    chat_menu: Optional[bool] = Field(None, description="是否在聊天菜单显示")
    server_instructions: Optional[str] = Field(None, description="服务说明")
    transport: Optional[TransportConfig] = Field(None, description="传输配置")
    requires_oauth: Optional[bool] = Field(False, description="是否需要OAuth")
    oauth: Optional[OAuthConfig] = Field(None, description="OAuth配置")
    custom_user_vars: Optional[Dict[str, Any]] = Field(None, description="自定义用户变量")
    status: Optional[str] = Field("active", description="状态")
    last_connected: Optional[datetime] = Field(None, description="最后连接时间")
    last_error: Optional[str] = Field(None, description="最后错误")
    error_message: Optional[str] = Field(None, description="错误消息")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    version: int = Field(..., description="版本号")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ServerListResponse(BaseModel):
    """服务列表响应"""
    servers: List[ServerResponse] = Field(..., description="服务列表")
    pagination: Dict[str, int] = Field(..., description="分页信息")


class ServerToggleResponse(BaseModel):
    """切换服务状态响应"""
    id: str = Field(..., description="服务ID")
    server_name: str = Field(..., description="服务名称")
    path: str = Field(..., description="服务路径")
    enabled: bool = Field(..., description="是否启用")
    status: str = Field(..., description="状态")
    updated_at: datetime = Field(..., description="更新时间")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ServerToolsResponse(BaseModel):
    """服务工具列表响应"""
    id: str = Field(..., description="服务ID")
    server_name: str = Field(..., description="服务名称")
    path: str = Field(..., description="服务路径")
    tools: List[ToolSchema] = Field(..., description="工具列表")
    num_tools: int = Field(..., description="工具数量")
    cached: bool = Field(False, description="是否来自缓存")


class ServerHealthResponse(BaseModel):
    """服务健康状态响应"""
    id: str = Field(..., description="服务ID")
    server_name: str = Field(..., description="服务名称")
    path: str = Field(..., description="服务路径")
    status: str = Field(..., description="健康状态")
    last_checked: datetime = Field(..., description="最后检查时间")
    response_time_ms: Optional[int] = Field(None, description="响应时间（毫秒）")
    num_tools: int = Field(..., description="工具数量")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str = Field(..., description="错误类型")
    message: str = Field(..., description="错误消息")
    current_version: Optional[int] = Field(None, description="当前版本号（冲突时）")
    provided_version: Optional[int] = Field(None, description="提供的版本号（冲突时）")

