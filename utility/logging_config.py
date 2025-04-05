import logging
import logging.handlers
import os
import json
import sys
import time
from pathlib import Path


class RequestIdFilter(logging.Filter):
    """Add request_id to log records if available."""

    def filter(self, record):
        if not hasattr(record, 'request_id'):
            record.request_id = '-'
        return True


class JSONFormatter(logging.Formatter):
    """Format logs as JSON for better parsing in production."""

    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, 'request_id', '-'),
            "thread": record.threadName,
        }

        if hasattr(record, 'duration'):
            log_record["duration_ms"] = record.duration

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


def setup_logging(log_level=None, json_logs=False):
    """Configure logging for the application."""

    # Get log level from environment or use default
    if log_level is None:
        log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    numeric_level = getattr(logging, log_level, logging.INFO)

    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Clear existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Configure formatters
    if json_logs:
        formatter = JSONFormatter()
        # For Docker, ensure we're using consistent line endings
        stderr_formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - [%(request_id)s] - %(name)s - %(message)s"
        )
        stderr_formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - [%(request_id)s] - %(name)s - %(message)s"
        )

    # Request ID filter
    request_id_filter = RequestIdFilter()

    # Console handlers for stdout and stderr
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(numeric_level)
    stdout_handler.addFilter(request_id_filter)
    stdout_handler.addFilter(lambda record: record.levelno < logging.ERROR)
    stdout_handler.setFormatter(formatter)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.ERROR)
    stderr_handler.addFilter(request_id_filter)
    stderr_handler.setFormatter(stderr_formatter)

    # File handlers
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / "app.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5
    )
    file_handler.setLevel(numeric_level)
    file_handler.addFilter(request_id_filter)
    file_handler.setFormatter(formatter)

    error_file_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / "error.log",
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5
    )
    error_file_handler.setLevel(logging.ERROR)
    error_file_handler.addFilter(request_id_filter)
    error_file_handler.setFormatter(formatter)

    # Add handlers to root logger
    root_logger.addHandler(stdout_handler)
    root_logger.addHandler(stderr_handler)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(error_file_handler)

    # Disable other loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # Return configured logger
    return logging.getLogger("supreme_court_agent")


def get_logger(name=None):
    """Get a logger with the given name."""
    if name is None:
        return logging.getLogger("supreme_court_agent")
    return logging.getLogger(f"supreme_court_agent.{name}")


class LoggingMiddleware:
    """Middleware to add request ID and log request/response details."""

    def __init__(self, app):
        self.app = app
        self.logger = get_logger("middleware")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        request_id = f"{int(start_time * 1000)}"

        # Create a logging context with request_id
        logging_context = {"request_id": request_id}

        # Add request_id to the scope for use in endpoints
        scope["request_id"] = request_id

        # Log the request
        path = scope.get("path", "")
        method = scope.get("method", "")
        self.logger.info(f"Request started: {method} {path}", extra=logging_context)

        # Process the request and capture any exceptions
        try:
            await self.app(scope, receive, send)
            duration = int((time.time() - start_time) * 1000)
            self.logger.info(
                f"Request completed: {method} {path} in {duration}ms",
                extra={"request_id": request_id, "duration": duration}
            )
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            self.logger.exception(
                f"Request failed: {method} {path} in {duration}ms - {str(e)}",
                extra={"request_id": request_id, "duration": duration}
            )
            raise