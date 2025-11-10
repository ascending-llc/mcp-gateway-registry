from functools import lru_cache
from env_settings import EnvSettings
from database import BookingDatabaseManager

# Simple singleton providers
@lru_cache()
def get_env() -> EnvSettings:
    return EnvSettings()


@lru_cache()
def get_db_manager() -> BookingDatabaseManager:
    env = get_env()
    return BookingDatabaseManager(env.db_path)