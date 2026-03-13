import logging
import secrets
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from registry_pkgs import load_scopes_config
from registry_pkgs.core.config import (
    ChunkingConfig,
    MongoConfig,
    RedisConfig,
    ScopesConfig,
    TelemetryConfig,
    VectorConfig,
)
from registry_pkgs.vector.config import BackendConfig


class Settings(BaseSettings):
    """Registry application settings loaded via pydantic-settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # ==================== Auth ====================
    secret_key: str = Field(default="", validation_alias="SECRET_KEY")
    admin_user: str = Field(default="admin", validation_alias="ADMIN_USER")
    admin_password: str = Field(default="password", validation_alias="ADMIN_PASSWORD")

    # ==================== Session ====================
    session_cookie_name: str = Field(default="jarvis_registry_session", validation_alias="SESSION_COOKIE_NAME")
    refresh_cookie_name: str = Field(default="jarvis_registry_refresh", validation_alias="REFRESH_COOKIE_NAME")
    session_max_age_seconds: int = Field(default=60 * 60 * 8, validation_alias="SESSION_MAX_AGE_SECONDS")
    session_cookie_secure: bool = Field(default=True, validation_alias="SESSION_COOKIE_SECURE")
    session_cookie_domain: str | None = Field(default=None, validation_alias="SESSION_COOKIE_DOMAIN")

    # ==================== Service URLs ====================
    auth_server_url: str = Field(default="http://localhost:8888", validation_alias="AUTH_SERVER_URL")
    auth_server_external_url: str = Field(default="http://localhost:8888", validation_alias="AUTH_SERVER_EXTERNAL_URL")
    auth_server_api_prefix: str = Field(default="", validation_alias="AUTH_SERVER_API_PREFIX")
    registry_client_url: str = Field(default="http://localhost:5173", validation_alias="REGISTRY_CLIENT_URL")
    registry_url: str = Field(default="http://localhost:7860", validation_alias="REGISTRY_URL")
    registry_app_name: str = Field(default="jarvis-registry-client", validation_alias="REGISTRY_APP_NAME")

    # ==================== Headers ====================
    auth_egress_header: str = Field(default="Authorization", validation_alias="AUTH_EGRESS_HEADER")
    internal_auth_header: str = Field(default="X-Jarvis-Auth", validation_alias="INTERNAL_AUTH_HEADER")

    # ==================== API ====================
    api_version: str = Field(default="v1", validation_alias="API_VERSION")

    # ==================== Anthropic ====================
    anthropic_api_version: str = Field(default="v0.1", validation_alias="ANTHROPIC_API_VERSION")
    anthropic_server_namespace: str = Field(default="io.mcpgateway", validation_alias="ANTHROPIC_SERVER_NAMESPACE")
    anthropic_api_default_limit: int = Field(default=100, validation_alias="ANTHROPIC_API_DEFAULT_LIMIT")
    anthropic_api_max_limit: int = Field(default=1000, validation_alias="ANTHROPIC_API_MAX_LIMIT")

    # ==================== Embeddings ====================
    embeddings_model_name: str = Field(default="all-MiniLM-L6-v2", validation_alias="EMBEDDINGS_MODEL_NAME")
    embeddings_model_dimensions: int = Field(default=384, validation_alias="EMBEDDINGS_MODEL_DIMENSIONS")

    # ==================== Search Defaults ====================
    tool_discovery_mode: str = Field(default="external", validation_alias="TOOL_DISCOVERY_MODE")
    external_vector_search_url: str = Field(
        default="http://localhost:8000/mcp", validation_alias="EXTERNAL_VECTOR_SEARCH_URL"
    )

    # ==================== Health ====================
    health_check_interval_seconds: int = Field(default=300, validation_alias="HEALTH_CHECK_INTERVAL_SECONDS")
    health_check_timeout_seconds: int = Field(default=2, validation_alias="HEALTH_CHECK_TIMEOUT_SECONDS")

    # ==================== WebSocket ====================
    max_websocket_connections: int = Field(default=100, validation_alias="MAX_WEBSOCKET_CONNECTIONS")
    websocket_send_timeout_seconds: float = Field(default=2.0, validation_alias="WEBSOCKET_SEND_TIMEOUT_SECONDS")
    websocket_broadcast_interval_ms: int = Field(default=10, validation_alias="WEBSOCKET_BROADCAST_INTERVAL_MS")
    websocket_max_batch_size: int = Field(default=20, validation_alias="WEBSOCKET_MAX_BATCH_SIZE")
    websocket_cache_ttl_seconds: int = Field(default=1, validation_alias="WEBSOCKET_CACHE_TTL_SECONDS")

    # ==================== Well-Known ====================
    enable_wellknown_discovery: bool = Field(default=True, validation_alias="ENABLE_WELLKNOWN_DISCOVERY")
    wellknown_cache_ttl: int = Field(default=300, validation_alias="WELLKNOWN_CACHE_TTL")

    # ==================== Gateway Security ====================
    mcpgw_enable_dns_rebinding_protection: bool = Field(
        default=True, validation_alias="MCPGW_ENABLE_DNS_REBINDING_PROTECTION"
    )
    mcpgw_allowed_hosts: str = Field(
        default="jarvis-demo.ascendingdc.com,jarvis-demo.ascendingdc.com:*", validation_alias="MCPGW_ALLOWED_HOSTS"
    )
    mcpgw_allowed_origins: str = Field(
        default="https://jarvis-demo.ascendingdc.com,https://jarvis-demo.ascendingdc.com:*",
        validation_alias="MCPGW_ALLOWED_ORIGINS",
    )

    # ==================== Server Security Scanning ====================
    security_scan_enabled: bool = Field(default=True, validation_alias="SECURITY_SCAN_ENABLED")
    security_scan_on_registration: bool = Field(default=True, validation_alias="SECURITY_SCAN_ON_REGISTRATION")
    security_block_unsafe_servers: bool = Field(default=True, validation_alias="SECURITY_BLOCK_UNSAFE_SERVERS")
    security_analyzers: str = Field(default="yara", validation_alias="SECURITY_ANALYZERS")
    security_scan_timeout: int = Field(default=60, validation_alias="SECURITY_SCAN_TIMEOUT")
    security_add_pending_tag: bool = Field(default=True, validation_alias="SECURITY_ADD_PENDING_TAG")
    mcp_scanner_llm_api_key: str = Field(default="", validation_alias="MCP_SCANNER_LLM_API_KEY")

    # ==================== Agent Security Scanning ====================
    agent_security_scan_enabled: bool = Field(default=True, validation_alias="AGENT_SECURITY_SCAN_ENABLED")
    agent_security_scan_on_registration: bool = Field(
        default=True, validation_alias="AGENT_SECURITY_SCAN_ON_REGISTRATION"
    )
    agent_security_block_unsafe_agents: bool = Field(
        default=True, validation_alias="AGENT_SECURITY_BLOCK_UNSAFE_AGENTS"
    )
    agent_security_analyzers: str = Field(default="yara,spec", validation_alias="AGENT_SECURITY_ANALYZERS")
    agent_security_scan_timeout: int = Field(default=60, validation_alias="AGENT_SECURITY_SCAN_TIMEOUT")
    agent_security_add_pending_tag: bool = Field(default=True, validation_alias="AGENT_SECURITY_ADD_PENDING_TAG")
    a2a_scanner_llm_api_key: str = Field(default="", validation_alias="A2A_SCANNER_LLM_API_KEY")

    # ==================== Container Paths ====================
    container_app_dir: Path = Field(default=Path("/app"))
    container_registry_dir: Path = Field(default=Path("/app/registry"))
    container_log_dir: Path = Field(default=Path("/app/logs"))

    # ==================== Redis ====================
    redis_uri: str = Field(default="redis://registry-redis:6379/1", validation_alias="REDIS_URI")
    redis_key_prefix: str = Field(default="jarvis-registry", validation_alias="REDIS_KEY_PREFIX")

    # ==================== MongoDB ====================
    mongo_uri: str = Field(default="mongodb://127.0.0.1:27017/jarvis", validation_alias="MONGO_URI")
    mongodb_username: str = Field(default="", validation_alias="MONGODB_USERNAME")
    mongodb_password: str = Field(default="", validation_alias="MONGODB_PASSWORD")

    # ==================== Telemetry ====================
    otel_metrics_config_path: str = Field(default="", validation_alias="OTEL_METRICS_CONFIG_PATH")
    otel_exporter_otlp_endpoint: str = Field(
        default="http://otel-collector:4318", validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    otel_prometheus_enabled: bool = Field(default=False, validation_alias="OTEL_PROMETHEUS_ENABLED")
    otel_prometheus_port: int = Field(default=9464, validation_alias="OTEL_PROMETHEUS_PORT")

    # ==================== Scopes ====================
    scopes_config_path: str = Field(default="", validation_alias="SCOPES_CONFIG_PATH")

    # ==================== Chunking ====================
    max_chunk_size: int = Field(default=2048, validation_alias="MAX_CHUNK_SIZE")
    chunk_overlap: int = Field(default=200, validation_alias="CHUNK_OVERLAP")

    # ==================== Vector Store ====================
    vector_store_type: str = Field(default="weaviate", validation_alias="VECTOR_STORE_TYPE")
    embedding_provider: str = Field(default="aws_bedrock", validation_alias="EMBEDDING_PROVIDER")
    weaviate_host: str = Field(default="127.0.0.1", validation_alias="WEAVIATE_HOST")
    weaviate_port: int = Field(default=8080, validation_alias="WEAVIATE_PORT")
    weaviate_api_key: str = Field(default="", validation_alias="WEAVIATE_API_KEY")
    weaviate_collection_prefix: str = Field(default="", validation_alias="WEAVIATE_COLLECTION_PREFIX")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="text-embedding-3-small", validation_alias="OPENAI_MODEL")

    # ==================== AWS ====================
    aws_region: str = Field(default="us-east-1", validation_alias="AWS_REGION")
    bedrock_model: str = Field(default="amazon.titan-embed-text-v2:0", validation_alias="BEDROCK_MODEL")
    aws_access_key_id: str = Field(default="", validation_alias="AWS_ACCESS_KEY_ID")
    aws_secret_access_key: str = Field(default="", validation_alias="AWS_SECRET_ACCESS_KEY")
    aws_session_token: str = Field(default="", validation_alias="AWS_SESSION_TOKEN")
    agentcore_assume_role_arn: str | None = Field(default=None, validation_alias="AGENTCORE_ASSUME_ROLE_ARN")

    # ==================== JWT ====================
    jwt_issuer: str = Field(default="jarvis-auth-server", validation_alias="JWT_ISSUER")
    jwt_audience: str = Field(default="jarvis-services", validation_alias="JWT_AUDIENCE")
    jwt_self_signed_kid: str = Field(default="self-signed-key-v1", validation_alias="JWT_SELF_SIGNED_KID")

    # ==================== Logging ====================
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_format: str = Field(
        default="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
        validation_alias="LOG_FORMAT",
    )

    # ==================== Encryption ====================
    creds_key: str | None = Field(default=None, validation_alias="CREDS_KEY")

    # ==================== Keycloak Integration ====================
    keycloak_url: str = Field(default="http://keycloak:8080", validation_alias="KEYCLOAK_URL")
    keycloak_realm: str = Field(default="mcp-gateway", validation_alias="KEYCLOAK_REALM")
    keycloak_admin: str = Field(default="admin", validation_alias="KEYCLOAK_ADMIN")
    keycloak_admin_password: str | None = Field(default=None, validation_alias="KEYCLOAK_ADMIN_PASSWORD")
    keycloak_m2m_client_id: str = Field(default="mcp-gateway-m2m", validation_alias="KEYCLOAK_M2M_CLIENT_ID")
    keycloak_m2m_client_secret: str = Field(default="", validation_alias="KEYCLOAK_M2M_CLIENT_SECRET")

    # ==================== Federation ====================
    federation_config_path: str = Field(
        default="/app/config/federation.json",
        validation_alias="FEDERATION_CONFIG_PATH",
    )
    asor_access_token: str = Field(default="", validation_alias="ASOR_ACCESS_TOKEN")
    asor_client_credentials: str = Field(default="", validation_alias="ASOR_CLIENT_CREDENTIALS")

    # ==================== Build Metadata ====================
    build_version: str = Field(default="", validation_alias="BUILD_VERSION")

    def model_post_init(self, __context: Any) -> None:
        if not self.secret_key:
            self.secret_key = secrets.token_hex(32)

        if self.auth_server_api_prefix:
            prefix = self.auth_server_api_prefix.rstrip("/")
            if not self.auth_server_url.endswith(prefix):
                self.auth_server_url = f"{self.auth_server_url.rstrip('/')}{prefix}"
            if not self.auth_server_external_url.endswith(prefix):
                self.auth_server_external_url = f"{self.auth_server_external_url.rstrip('/')}{prefix}"

        if self.tool_discovery_mode not in {"embedded", "external"}:
            raise ValueError(
                f"Invalid tool_discovery_mode: {self.tool_discovery_mode}. Must be 'embedded' or 'external'"
            )

    @property
    def is_local_dev(self) -> bool:
        return not Path("/app").exists()

    @property
    def use_external_discovery(self) -> bool:
        return self.tool_discovery_mode == "external"

    @property
    def servers_dir(self) -> Path:
        if self.is_local_dev:
            return Path.cwd() / "registry" / "servers"
        return self.container_registry_dir / "servers"

    @property
    def static_dir(self) -> Path:
        if self.is_local_dev:
            return Path.cwd() / "registry" / "static"
        return self.container_registry_dir / "static"

    @property
    def templates_dir(self) -> Path:
        if self.is_local_dev:
            return Path.cwd() / "registry" / "templates"
        return self.container_registry_dir / "templates"

    @property
    def embeddings_model_dir(self) -> Path:
        if self.is_local_dev:
            return Path.cwd() / "registry" / "models" / self.embeddings_model_name
        return self.container_registry_dir / "models" / self.embeddings_model_name

    @property
    def log_dir(self) -> Path:
        if self.is_local_dev:
            return Path.cwd() / "logs"
        return self.container_log_dir

    @property
    def log_file_path(self) -> Path:
        return self.log_dir / "registry.log"

    @property
    def faiss_index_path(self) -> Path:
        return self.servers_dir / "service_index.faiss"

    @property
    def faiss_metadata_path(self) -> Path:
        return self.servers_dir / "service_index_metadata.json"

    @property
    def dotenv_path(self) -> Path:
        if self.is_local_dev:
            return Path.cwd() / ".env"
        return self.container_registry_dir / ".env"

    @property
    def agents_dir(self) -> Path:
        if self.is_local_dev:
            return Path.cwd() / "registry" / "agents"
        return self.container_registry_dir / "agents"

    @property
    def agent_state_file_path(self) -> Path:
        return self.agents_dir / "agent_state.json"

    @property
    def mongo_config(self) -> MongoConfig:
        return MongoConfig(
            mongo_uri=self.mongo_uri,
            mongodb_username=self.mongodb_username,
            mongodb_password=self.mongodb_password,
        )

    @property
    def redis_config(self) -> RedisConfig:
        return RedisConfig(redis_uri=self.redis_uri, redis_key_prefix=self.redis_key_prefix)

    @property
    def telemetry_config(self) -> TelemetryConfig:
        return TelemetryConfig(
            otel_metrics_config_path=self.otel_metrics_config_path,
            otel_exporter_otlp_endpoint=self.otel_exporter_otlp_endpoint,
            otel_prometheus_enabled=self.otel_prometheus_enabled,
            otel_prometheus_port=self.otel_prometheus_port,
        )

    @property
    def scopes_file_config(self) -> ScopesConfig:
        return ScopesConfig(scopes_config_path=self.scopes_config_path)

    @property
    def chunking_config(self) -> ChunkingConfig:
        return ChunkingConfig(max_chunk_size=self.max_chunk_size, chunk_overlap=self.chunk_overlap)

    @property
    def vector_config(self) -> VectorConfig:
        return VectorConfig(
            vector_store_type=self.vector_store_type,
            embedding_provider=self.embedding_provider,
            weaviate_host=self.weaviate_host,
            weaviate_port=self.weaviate_port,
            weaviate_api_key=self.weaviate_api_key,
            weaviate_collection_prefix=self.weaviate_collection_prefix,
            openai_api_key=self.openai_api_key,
            openai_model=self.openai_model,
            aws_region=self.aws_region,
            bedrock_model=self.bedrock_model,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            aws_session_token=self.aws_session_token,
        )

    @property
    def vector_backend_config(self) -> BackendConfig:
        return BackendConfig.from_vector_config(self.vector_config)

    def configure_logging(self) -> None:
        numeric_level = getattr(logging, self.log_level.upper(), logging.INFO)
        logging.basicConfig(level=numeric_level, format=self.log_format, force=True)

    @property
    def scopes_config(self) -> dict[str, Any]:
        return load_scopes_config(self.scopes_file_config)


settings = Settings()
