import logging
import json
import os
import sys
import time
import uuid
from typing import Any, Dict, Optional

# Configure log levels based on environment
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Create a logger
logger = logging.getLogger("recallist")

# Set the log level
log_level = getattr(logging, LOG_LEVEL, logging.INFO)
logger.setLevel(log_level)

# Create a handler for stdout
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(log_level)

# Create a formatter
if ENVIRONMENT == "development":
    # More human-readable format for development
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
else:
    # JSON formatter for production (better for CloudWatch Logs)
    class JsonFormatter(logging.Formatter):
        def format(self, record):
            log_record = {
                "timestamp": int(time.time() * 1000),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }
            
            # Add exception info if available
            if record.exc_info:
                log_record["exception"] = self.formatException(record.exc_info)
            
            # Add extra fields from record
            if hasattr(record, "request_id"):
                log_record["request_id"] = record.request_id
                
            if hasattr(record, "extra") and record.extra:
                log_record.update(record.extra)
                
            return json.dumps(log_record)
    
    formatter = JsonFormatter()

# Set the formatter for the handler
handler.setFormatter(formatter)

# Add the handler to the logger
logger.addHandler(handler)

# Prevent logs from propagating to the root logger
logger.propagate = False

# Request ID context
_request_id_context = {}

def set_request_id(request_id: Optional[str] = None) -> str:
    """
    Set a request ID for the current context.
    If no request_id is provided, a new UUID is generated.
    
    Args:
        request_id: Optional request ID to use
        
    Returns:
        The request ID that was set
    """
    if request_id is None:
        request_id = str(uuid.uuid4())
    _request_id_context["request_id"] = request_id
    return request_id

def get_request_id() -> Optional[str]:
    """
    Get the request ID for the current context.
    
    Returns:
        The request ID or None if not set
    """
    return _request_id_context.get("request_id")

def clear_request_id() -> None:
    """
    Clear the request ID for the current context.
    """
    _request_id_context.pop("request_id", None)

def _log(level: int, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """
    Internal logging function that adds request_id to the log record.
    
    Args:
        level: Log level
        message: Log message
        extra: Extra fields to include in the log record
    """
    if extra is None:
        extra = {}
    
    # Add request_id to extra if available
    request_id = get_request_id()
    if request_id:
        extra["request_id"] = request_id
    
    # Create a log record with extra fields
    logger.log(level, message, extra={"extra": extra})

def debug(message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """
    Log a debug message.
    
    Args:
        message: Log message
        extra: Extra fields to include in the log record
    """
    _log(logging.DEBUG, message, extra)

def info(message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """
    Log an info message.
    
    Args:
        message: Log message
        extra: Extra fields to include in the log record
    """
    _log(logging.INFO, message, extra)

def warning(message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """
    Log a warning message.
    
    Args:
        message: Log message
        extra: Extra fields to include in the log record
    """
    _log(logging.WARNING, message, extra)

def error(message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """
    Log an error message.
    
    Args:
        message: Log message
        extra: Extra fields to include in the log record
    """
    _log(logging.ERROR, message, extra)

def critical(message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """
    Log a critical message.
    
    Args:
        message: Log message
        extra: Extra fields to include in the log record
    """
    _log(logging.CRITICAL, message, extra)

def exception(message: str, extra: Optional[Dict[str, Any]] = None) -> None:
    """
    Log an exception message.
    
    Args:
        message: Log message
        extra: Extra fields to include in the log record
    """
    if extra is None:
        extra = {}
    
    # Add request_id to extra if available
    request_id = get_request_id()
    if request_id:
        extra["request_id"] = request_id
    
    # Log the exception with extra fields
    logger.exception(message, extra={"extra": extra})