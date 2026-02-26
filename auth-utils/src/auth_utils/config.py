from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent


class AuthUtilsSettings(BaseSettings):
    """Configuration for auth-utils."""

    scopes_config_path: str = Field(
        default="config/scopes.yml",
        description="Path to the scopes configuration YAML file",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="allow",
    )


settings = AuthUtilsSettings()
