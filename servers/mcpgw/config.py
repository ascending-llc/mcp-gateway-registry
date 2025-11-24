import argparse
import logging
import os

from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from models.enums import ToolDiscoveryMode

logging.basicConfig(
    level=logging.INFO,
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
    WEAVIATE_HOST: str = "weaviate"
    WEAVIATE_PORT: int = 8080
    WEAVIATE_API_KEY: Optional[str] = "test-secret-key"

    WEAVIATE_SESSION_POOL_CONNECTIONS: int = 20  # Maximum connections
    WEAVIATE_SESSION_POOL_MAXSIZE: int = 100  # Connection pool size
    WEAVIATE_INIT_TIME: int = 30  # 初始化超时时间
    WEAVIATE_QUERY_TIME: int = 120  # 查询超时时间
    WEAVIATE_INSERT_TIME: int = 300  # 插入超时时间

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

        # Debug: check if .env file exists and show env var
        env_file = Path(".env")
        if env_file.exists():
            logger.debug(f"  .env file found at: {env_file.absolute()}")
        else:
            logger.warning(f"  .env file NOT found at: {env_file.absolute()}")

        # Debug: show environment variable value
        env_value = os.getenv("TOOL_DISCOVERY_MODE")
        if env_value:
            logger.debug(f"  TOOL_DISCOVERY_MODE env var: {env_value}")
        else:
            logger.debug(f"  TOOL_DISCOVERY_MODE env var: not set")
        logger.info(f"  Scopes Config Path: {self.scopes_config_path}")


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

# Log configuration on module import
settings.log_config()
