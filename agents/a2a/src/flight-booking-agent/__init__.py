"""Flight Booking Agent Package."""

import logging

from .agent import (
    agent,
    app,
)
from .database import BookingDatabaseManager
from .env_settings import env_settings
from .tools import FLIGHT_BOOKING_TOOLS

# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,  # Set the log level to INFO
    # Define log message format
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

__all__ = ["FLIGHT_BOOKING_TOOLS", "BookingDatabaseManager", "agent", "app", "env_settings"]
