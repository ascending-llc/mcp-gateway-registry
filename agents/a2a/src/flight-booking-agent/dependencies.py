"""Dependency injection module for Flight Booking Agent."""

import logging
from functools import lru_cache

from database import BookingDatabaseManager
from env_settings import EnvSettings

# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,  # Set the log level to INFO
    # Define log message format
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


# Simple singleton providers
@lru_cache
def get_env() -> EnvSettings:
    """Get environment settings singleton."""
    logger.debug("Getting environment settings")
    return EnvSettings()


@lru_cache
def get_db_manager() -> BookingDatabaseManager:
    """Get database manager singleton."""
    env = get_env()
    logger.debug(f"Getting database manager with db_path: {env.db_path}")
    return BookingDatabaseManager(env.db_path)
