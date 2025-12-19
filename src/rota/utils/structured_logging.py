"""
Structured Logging Adapter
==========================
Optional structlog integration for production environments.
Falls back to standard logging if structlog is not installed.

Usage:
    from rota.utils.structured_logging import get_structured_logger
    
    log = get_structured_logger("rota.solver")
    log.info("solve_started", weeks=4, people=10)
"""
from typing import Any, Dict, Optional
import logging

# Try to import structlog, fallback to standard logging wrapper
try:
    import structlog
    from structlog.stdlib import ProcessorStack
    STRUCTLOG_AVAILABLE = True
except ImportError:
    STRUCTLOG_AVAILABLE = False


def configure_structlog(json_output: bool = False) -> None:
    """
    Configure structlog for the application.
    
    Args:
        json_output: If True, output JSON logs (for production).
                    If False, use colored console output (for development).
    """
    if not STRUCTLOG_AVAILABLE:
        logging.getLogger("rota").warning("structlog not installed, using standard logging")
        return
    
    if json_output:
        # Production: JSON output
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        # Development: Colored console output
        structlog.configure(
            processors=[
                structlog.contextvars.merge_contextvars,
                structlog.processors.add_log_level,
                structlog.processors.TimeStamper(fmt="%H:%M:%S"),
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )


class StructuredLoggerAdapter:
    """
    Adapter that provides structlog-like interface using standard logging.
    
    Used when structlog is not installed.
    """
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def _format_kwargs(self, kwargs: Dict[str, Any]) -> str:
        """Format kwargs as key=value pairs."""
        if not kwargs:
            return ""
        return " " + " ".join(f"{k}={v}" for k, v in kwargs.items())
    
    def debug(self, msg: str, **kwargs):
        self.logger.debug(f"{msg}{self._format_kwargs(kwargs)}")
    
    def info(self, msg: str, **kwargs):
        self.logger.info(f"{msg}{self._format_kwargs(kwargs)}")
    
    def warning(self, msg: str, **kwargs):
        self.logger.warning(f"{msg}{self._format_kwargs(kwargs)}")
    
    def error(self, msg: str, **kwargs):
        self.logger.error(f"{msg}{self._format_kwargs(kwargs)}")
    
    def critical(self, msg: str, **kwargs):
        self.logger.critical(f"{msg}{self._format_kwargs(kwargs)}")
    
    def bind(self, **kwargs) -> "StructuredLoggerAdapter":
        """Return self (no-op for standard logging)."""
        return self


def get_structured_logger(name: str) -> Any:
    """
    Get a structured logger.
    
    Returns structlog logger if available, otherwise a compatible adapter.
    
    Args:
        name: Logger name (e.g., "rota.solver")
        
    Returns:
        Logger with structured logging interface
    """
    if STRUCTLOG_AVAILABLE:
        return structlog.get_logger(name)
    else:
        return StructuredLoggerAdapter(name)


# Context management for request-scoped logging
def bind_context(**kwargs) -> None:
    """
    Bind context variables for all subsequent log calls.
    
    Args:
        **kwargs: Context values (e.g., request_id="abc123")
    """
    if STRUCTLOG_AVAILABLE:
        import structlog.contextvars
        structlog.contextvars.bind_contextvars(**kwargs)


def clear_context() -> None:
    """Clear all context variables."""
    if STRUCTLOG_AVAILABLE:
        import structlog.contextvars
        structlog.contextvars.clear_contextvars()
