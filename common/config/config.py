"""
    If other services inherit this setting, the subclass will override the setting of this class,
     in the following order: environment variables -> parent class -> subclass.

     Unified management of all configuration variables.
"""
from pathlib import Path

from pydantic_settings import SettingsConfigDict, BaseSettings

BASE_DIR = Path(__file__).resolve().parent


class SharedSettings(BaseSettings):
    DEBUG: bool = False

    SECRET_KEY: str = None
    SESSION_COOKIE_NAME: str = "mcp_gateway_session"
    SESSION_OPENID_USER_ID: str = "openid_user_id"
    SESSION_OPENID_ACCESS_TOKEN: str = "openid_access_token"
    SESSION_MAX_AGE_SECONDS: int = 60 * 60 * 8  # 8 hours



    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="allow"
    )


settings = SharedSettings()
