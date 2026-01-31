"""
Centralized logging configuration.
Uses Python's built-in logging (no external services required).

Logs are automatically captured by Render for viewing in the dashboard.
"""

import logging
import sys
from datetime import datetime


def setup_logger(name: str = "secondbrain") -> logging.Logger:
    """
    Set up structured logger with consistent formatting.

    Logs are captured by Render automatically (no Papertrail needed).

    Args:
        name: Logger name (typically module name)

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Only configure if not already configured
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Console handler (captured by Render)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)

    # Structured format: [TIMESTAMP] [LEVEL] [MODULE] message
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False  # Don't propagate to root logger

    return logger


# Convenience functions for quick logging

def log_info(module: str, message: str, **kwargs):
    """
    Log info with context.

    Example:
        log_info("BoxConnector", "Starting sync", folder_id="12345", tenant_id="abc")
    """
    logger = setup_logger(module)
    extra_info = " ".join([f"{k}={v}" for k, v in kwargs.items()])
    logger.info(f"{message} {extra_info}" if extra_info else message)


def log_error(module: str, message: str, error: Exception = None, **kwargs):
    """
    Log error with context.

    Example:
        log_error("BoxConnector", "Download failed", error=e, file_id="12345")
    """
    logger = setup_logger(module)
    extra_info = " ".join([f"{k}={v}" for k, v in kwargs.items()])
    full_message = f"{message} {extra_info}" if extra_info else message
    if error:
        logger.error(f"{full_message} | Error: {str(error)}", exc_info=True)
    else:
        logger.error(full_message)


def log_warning(module: str, message: str, **kwargs):
    """
    Log warning with context.

    Example:
        log_warning("BoxConnector", "File size exceeds limit", file_size=10000000)
    """
    logger = setup_logger(module)
    extra_info = " ".join([f"{k}={v}" for k, v in kwargs.items()])
    logger.warning(f"{message} {extra_info}" if extra_info else message)


def log_debug(module: str, message: str, **kwargs):
    """
    Log debug information.

    Only visible when log level is set to DEBUG.

    Example:
        log_debug("BoxConnector", "Processing file", file_name="doc.pdf")
    """
    logger = setup_logger(module)
    extra_info = " ".join([f"{k}={v}" for k, v in kwargs.items()])
    logger.debug(f"{message} {extra_info}" if extra_info else message)


# Module-level logger instance for direct use
logger = setup_logger()
