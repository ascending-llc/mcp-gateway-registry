from functools import lru_cache
from env_settings import EnvSettings
from database import FlightDatabaseManager

# Simple singleton providers
@lru_cache()
def get_env() -> EnvSettings:
    return EnvSettings()


@lru_cache()
def get_db_manager() -> FlightDatabaseManager:
    env = get_env()
    return FlightDatabaseManager(env.db_path)