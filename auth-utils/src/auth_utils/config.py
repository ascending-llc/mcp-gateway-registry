from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthUtilsSettings(BaseSettings):
    """Configuration for auth-utils."""

    scopes_config_path: str = Field(
        default="config/scopes.yml",
        description="Path to the scopes configuration YAML file",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )


settings = AuthUtilsSettings()
