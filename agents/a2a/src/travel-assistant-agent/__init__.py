"""Travel Assistant Agent Package."""

import logging

from .agent import (
    agent,
    app,
)
from .database import FlightDatabaseManager
from .env_settings import env_settings
from .tools import TRAVEL_ASSISTANT_TOOLS

# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,  # Set the log level to INFO
    # Define log message format
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

__all__ = ["app", "agent", "env_settings", "FlightDatabaseManager", "TRAVEL_ASSISTANT_TOOLS"]
