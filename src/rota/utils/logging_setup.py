"""
Rota Optimizer — Logging Infrastructure
========================================
Multi-level logging with file rotation and function tracing.

Levels:
    TRACE (5): Function entry/exit with arguments
    DEBUG (10): Variable values, constraint details
    INFO (20): Progress, key decisions
    WARNING (30): Soft constraint violations
    ERROR (40): Hard constraint failures, exceptions
"""
import logging
import functools
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional, Any, Callable
from datetime import datetime


# Custom TRACE level (below DEBUG)
TRACE = 5
logging.addLevelName(TRACE, "TRACE")


def trace(self, message, *args, **kwargs):
    """Log at TRACE level."""
    if self.isEnabledFor(TRACE):
        self._log(TRACE, message, args, **kwargs)


logging.Logger.trace = trace


class ColoredFormatter(logging.Formatter):
    """Formatter with ANSI colors for console output."""
    
    COLORS = {
        TRACE: "\033[90m",      # Gray
        logging.DEBUG: "\033[36m",     # Cyan
        logging.INFO: "\033[32m",      # Green
        logging.WARNING: "\033[33m",   # Yellow
        logging.ERROR: "\033[31m",     # Red
        logging.CRITICAL: "\033[35m",  # Magenta
    }
    RESET = "\033[0m"
    
    def format(self, record):
        color = self.COLORS.get(record.levelno, "")
        message = super().format(record)
        if color and sys.stdout.isatty():
            return f"{color}{message}{self.RESET}"
        return message


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = "logs/rota.log",
    console_level: Optional[str] = None,
    max_bytes: int = 5 * 1024 * 1024,  # 5 MB
    backup_count: int = 3,
) -> logging.Logger:
    """
    Configure application logging.
    
    Args:
        level: Minimum log level for file output
        log_file: Path to log file (None = no file logging)
        console_level: Console log level (defaults to level)
        max_bytes: Max size before rotation
        backup_count: Number of backup files to keep
        
    Returns:
        Root logger for the application
    """
    # Get root rota logger
    logger = logging.getLogger("rota")
    logger.setLevel(TRACE)  # Capture everything, handlers filter
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Parse level strings
    file_level = getattr(logging, level.upper(), logging.INFO)
    cons_level = getattr(logging, (console_level or level).upper(), logging.INFO)
    
    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(cons_level)
    console_format = ColoredFormatter(
        "[%(asctime)s] %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S"
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler with rotation
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setLevel(file_level)
        file_format = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)
    
    logger.info(f"Logging initialized: console={cons_level}, file={file_level if log_file else 'disabled'}")
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.
    
    Args:
        name: Module name (e.g., "rota.solver")
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def log_function_call(func: Callable) -> Callable:
    """
    Decorator to log function entry and exit with arguments.
    
    Usage:
        @log_function_call
        def my_function(x, y):
            return x + y
    """
    logger = logging.getLogger(f"rota.{func.__module__}")
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        
        # Log entry
        args_str = ", ".join([repr(a)[:50] for a in args[:3]])  # Limit arg length
        kwargs_str = ", ".join([f"{k}={repr(v)[:30]}" for k, v in list(kwargs.items())[:3]])
        call_str = f"{args_str}, {kwargs_str}" if kwargs_str else args_str
        logger.log(TRACE, f"→ {func_name}({call_str})")
        
        try:
            result = func(*args, **kwargs)
            result_str = repr(result)[:100] if result is not None else "None"
            logger.log(TRACE, f"← {func_name} returned: {result_str}")
            return result
        except Exception as e:
            logger.error(f"✖ {func_name} raised: {type(e).__name__}: {e}")
            raise
    
    return wrapper


def log_constraint(
    logger: logging.Logger,
    name: str,
    satisfied: bool,
    details: str = "",
    level: int = logging.DEBUG
):
    """
    Log a constraint check result.
    
    Args:
        logger: Logger to use
        name: Constraint name
        satisfied: Whether constraint is satisfied
        details: Additional information
        level: Log level for this constraint
    """
    status = "✓" if satisfied else "✗"
    msg = f"[{status}] {name}"
    if details:
        msg += f" — {details}"
    
    if satisfied:
        logger.log(level, msg)
    else:
        logger.warning(msg)


class SolverLogger:
    """Structured logger for solver operations."""
    
    def __init__(self, name: str = "rota.solver"):
        self.logger = logging.getLogger(name)
        self.indent = 0
    
    def _prefix(self) -> str:
        return "  " * self.indent
    
    def phase(self, name: str):
        """Log start of a major phase."""
        self.logger.info(f"{'='*20} {name} {'='*20}")
    
    def step(self, description: str):
        """Log a step within a phase."""
        self.logger.info(f"{self._prefix()}▸ {description}")
    
    def detail(self, key: str, value: Any):
        """Log a detail at DEBUG level."""
        self.logger.debug(f"{self._prefix()}  {key}: {value}")
    
    def constraint(self, name: str, satisfied: bool, details: str = ""):
        """Log constraint check."""
        log_constraint(self.logger, name, satisfied, details)
    
    def enter(self, context: str):
        """Enter a nested context."""
        self.logger.debug(f"{self._prefix()}┌─ {context}")
        self.indent += 1
    
    def exit(self, context: str = ""):
        """Exit a nested context."""
        self.indent = max(0, self.indent - 1)
        if context:
            self.logger.debug(f"{self._prefix()}└─ {context}")


# Default logger instance
_default_logger: Optional[logging.Logger] = None


def init_logging(level: str = "INFO", log_file: str = "logs/rota.log"):
    """Initialize logging for the application."""
    global _default_logger
    _default_logger = setup_logging(level=level, log_file=log_file)
    return _default_logger


def get_default_logger() -> logging.Logger:
    """Get the default application logger."""
    global _default_logger
    if _default_logger is None:
        _default_logger = setup_logging()
    return _default_logger
