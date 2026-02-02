import argparse
import logging
import os

from pathlib import Path
from typing import Optional
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    For nested configs, use double underscore (e.g., REGISTRY__URL).
    """
    # Registry configuration
    REGISTRY_URL: str = Field(
        default="http://localhost:7860",
        description="Base URL of the MCP Gateway Registry"
    )

    @property
    def REGISTRY_BASE_URL(self) -> str:
        """
        Backward-compatible alias for REGISTRY_URL.

        Existing code that references settings.REGISTRY_BASE_URL will continue
        to work, while new code should use settings.REGISTRY_URL.
        """
        return self.REGISTRY_URL

    @REGISTRY_BASE_URL.setter
    def REGISTRY_BASE_URL(self, value: str) -> None:
        self.REGISTRY_URL = value

    # Server configuration
    MCP_TRANSPORT: str = Field(
        default=Constants.DEFAULT_MCP_TRANSPORT,
        description="Transport type for the MCP server"
    )
    MCP_SERVER_LISTEN_PORT: str = Field(
        default=Constants.DEFAULT_MCP_SERVER_LISTEN_PORT,
        description="Port for the MCP server to listen on"
    )

    # Auth server configuration
    AUTH_SERVER_URL: str = Field(
        default="http://localhost:8888",
        description="URL of the authentication server"
    )
    
    INTERNAL_AUTH_HEADER: str = Field(
        default="X-Jarvis-Auth",
        description="Header name for internal JWT authentication (RFC 8707 compliant)"
    )
    # JWT authentication configuration
    SECRET_KEY: Optional[str] = Field(
        default=None,
        description="Secret key for JWT token validation (HS256)"
    )
    JWT_ISSUER: str = Field(
        default="jarvis-auth-server",
        description="Expected JWT token issuer"
    )
    JWT_AUDIENCE: str = Field(
        default="jarvis-registry",
        description="Expected JWT token audience"
    )
    JWT_SELF_SIGNED_KID: str = Field(
        default="self-signed-key-v1",
        description="Key ID for self-signed JWT tokens"
    )

    # Logging configuration
    LOG_LEVEL: int = Field(
        default=logging.INFO,
        description="Logging level (integer constant from logging module)"
    )

    API_VERSION: str = "v1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        # Enable environment variable validation
        validate_default=True,
    )

    @field_validator("REGISTRY_URL")
    @classmethod
    def validate_registry_url(cls, v: str) -> str:
        """Validate and normalize registry base URL."""
        if not v:
            raise ValueError("REGISTRY_URL must be set")
        return v.rstrip("/")
    
    @field_validator("LOG_LEVEL", mode='before')
    @classmethod
    def convert_log_level(cls, v):
        """Convert string log level names to integers (e.g., 'DEBUG' -> 10)."""
        if isinstance(v, str):
            return getattr(logging, v.upper(), logging.INFO)
        return v

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
        logger.info(f"  Registry URL: {self.REGISTRY_URL}")
        logger.info(f"  MCP Transport: {self.MCP_TRANSPORT}")
        logger.info(f"  Listen Port: {self.MCP_SERVER_LISTEN_PORT}")
        logger.info(f"  Auth Server URL: {self.AUTH_SERVER_URL}")
        logger.info(f"  Log Level: {self.LOG_LEVEL}")


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

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format='%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s'
)
logger.setLevel(settings.LOG_LEVEL)

settings.log_config()
