import argparse
import logging
import os

from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from models.enums import ToolDiscoveryMode

logging.basicConfig(
    level=os.environ.get("LOGLEVEL", "INFO"),
    format='%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s'
)
logger = logging.getLogger(__name__)


class Constants:
    """Application constants that don't change."""

    DESCRIPTION: str = "MCP Gateway Registry Interaction Server (mcpgw)"
    DEFAULT_MCP_TRANSPORT: str = "streamable-http"
    DEFAULT_MCP_SERVER_LISTEN_PORT: str = "8003"
    REQUEST_TIMEOUT: float = 15.0


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings can be overridden via environment variables with the same name.
    For nested configs, use double underscore (e.g., REGISTRY__BASE_URL).
    """
    # Registry configuration
    registry_base_url: str = Field(
        default="http://localhost:7860",
        description="Base URL of the MCP Gateway Registry"
    )
    registry_username: str = Field(
        default="",
        description="Username for registry authentication"
    )
    registry_password: str = Field(
        default="",
        description="Password for registry authentication"
    )

    # Server configuration
    mcp_transport: str = Field(
        default=Constants.DEFAULT_MCP_TRANSPORT,
        description="Transport type for the MCP server"
    )
    mcp_server_listen_port: str = Field(
        default=Constants.DEFAULT_MCP_SERVER_LISTEN_PORT,
        description="Port for the MCP server to listen on"
    )

    # Auth server configuration
    auth_server_url: str = Field(
        default="http://localhost:8888",
        description="URL of the authentication server"
    )

    # JWT authentication configuration
    jwt_secret_key: Optional[str] = Field(
        default=None,
        description="Secret key for JWT token validation (HS256)"
    )
    jwt_issuer: str = Field(
        default="mcp-auth-server",
        description="Expected JWT token issuer"
    )
    jwt_audience: str = Field(
        default="mcp-registry",
        description="Expected JWT token audience"
    )
    jwt_self_signed_kid: str = Field(
        default="self-signed-key-v1",
        description="Key ID for self-signed JWT tokens"
    )

    # Vector search configuration
    tool_discovery_mode: ToolDiscoveryMode = Field(
        default=ToolDiscoveryMode.EMBEDDED,
        description="Vector search mode: 'embedded' or 'external'"
    )
    embeddings_model_name: str = Field(
        default="all-MiniLM-L6-v2",
        description="Name of the sentence-transformers model"
    )
    embeddings_model_dimension: int = Field(
        default=384,
        description="Dimension of embeddings"
    )
    faiss_check_interval: float = Field(
        default=5.0,
        description="Interval in seconds to check for FAISS index updates"
    )

    # Weaviate Configuration
    weaviate_host: str = Field(default="weaviate")
    weaviate_port: int = Field(default=8080)
    weaviate_api_key: Optional[str] = Field(
        default="test-secret-key",
        description="API key for WEAVIATE server"
    )

    weaviate_session_pool_connections: int = Field(
        default=20,
        description=" Maximum connections"
    )
    weaviate_session_pool_maxsize: int = Field(
        default=100,
        description="Connection pool size"
    )
    weaviate_init_time: int = Field(
        default=20,
        description="Initialization time"
    )
    weaviate_query_time: int = Field(
        default=120,
        description="Query time in seconds"
    )
    weaviate_insert_time: int = Field(
        default=300,
        description="Insert time in seconds"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Enable environment variable validation
        validate_default=True,
    )

    @field_validator("registry_base_url")
    @classmethod
    def validate_registry_url(cls, v: str) -> str:
        """Validate and normalize registry base URL."""
        if not v:
            raise ValueError("REGISTRY_BASE_URL must be set")
        return v.rstrip("/")

    @property
    def scopes_config_path(self) -> Path:
        """
        Determine the path to scopes.yml configuration file.
        
        Returns:
            Path: Path to scopes.yml file
        """
        # Try Docker container path first
        docker_path = Path("/app/auth_server/scopes.yml")
        if docker_path.exists():
            return docker_path

        # Try local development path
        local_path = Path(__file__).parent.parent.parent / "auth_server" / "scopes.yml"
        if local_path.exists():
            return local_path

        logger.warning("Scopes configuration file not found at expected locations")
        return Path("scopes.yml")

    def log_config(self):
        """Log current configuration (hiding sensitive values)."""
        logger.info("Configuration loaded:")
        logger.info(f"  Registry URL: {self.registry_base_url}")
        logger.info(f"  Registry Username: {'***' if self.registry_username else 'not set'}")
        logger.info(f"  Registry Password: {'***' if self.registry_password else 'not set'}")
        logger.info(f"  MCP Transport: {self.mcp_transport}")
        logger.info(f"  Listen Port: {self.mcp_server_listen_port}")
        logger.info(f"  Auth Server URL: {self.auth_server_url}")
        logger.info(f"  Tool Discovery Mode: {self.tool_discovery_mode}")


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.
    
    Command line arguments override environment variables.
    
    Returns:
        argparse.Namespace: Parsed command line arguments
    """
    parser = argparse.ArgumentParser(description=Constants.DESCRIPTION)

    parser.add_argument(
        "--port",
        type=str,
        help=f"Port for the MCP server to listen on (default: from env or {Constants.DEFAULT_MCP_SERVER_LISTEN_PORT})",
    )

    parser.add_argument(
        "--transport",
        type=str,
        choices=["streamable-http"],
        help=f"Transport type for the MCP server (default: from env or {Constants.DEFAULT_MCP_TRANSPORT})",
    )

    return parser.parse_args()


# Create global settings instance
settings = Settings()

settings.log_config()
