# Configure logging with file and console handlers
import logging
import sys

from registry.core.config import settings


def setup_logging():
    """Configure logging to write to both file and console."""
    # Ensure log directory exists
    log_dir = settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    # Define log file path
    log_file = log_dir / "registry.log"

    # Get log level from settings
    log_level_str = settings.LOG_LEVEL.upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Create formatters
    file_formatter = logging.Formatter(
        "%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s"
    )

    console_formatter = logging.Formatter(
        "%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s"
    )

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # File handler with UTF-8 encoding
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(file_formatter)

    # Console handler with UTF-8 encoding for Windows compatibility
    # Reconfigure stdout to use UTF-8 encoding to handle emoji characters
    if sys.platform == "win32":
        try:
            # Try to reconfigure stdout to use UTF-8
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            # Python < 3.7 doesn't have reconfigure, ignore
            pass

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_formatter)

    # Add handlers to root logger
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    return root_logger


logger = setup_logging()
