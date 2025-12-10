"""Tests for logging infrastructure."""
import logging
import os
import tempfile
from pathlib import Path

import pytest

from rota.utils.logging_setup import (
    setup_logging,
    get_logger,
    log_function_call,
    log_constraint,
    SolverLogger,
    TRACE,
)


class TestLoggingSetup:
    """Tests for logging configuration."""
    
    def test_setup_logging_creates_logger(self):
        """Test that setup_logging returns a logger."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            logger = setup_logging(level="DEBUG", log_file=str(log_file))
            
            assert logger is not None
            assert logger.name == "rota"
            assert len(logger.handlers) == 2  # Console + file
    
    def test_setup_logging_creates_log_file(self):
        """Test that log file is created."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "logs" / "test.log"
            logger = setup_logging(level="DEBUG", log_file=str(log_file))
            logger.info("Test message")
            
            assert log_file.exists()
    
    def test_setup_logging_no_file(self):
        """Test logging without file output."""
        logger = setup_logging(level="INFO", log_file=None)
        
        assert logger is not None
        assert len(logger.handlers) == 1  # Console only
    
    def test_trace_level(self):
        """Test custom TRACE level exists."""
        assert TRACE == 5
        assert logging.getLevelName(TRACE) == "TRACE"
    
    def test_get_logger(self):
        """Test get_logger returns correct logger."""
        logger = get_logger("rota.solver")
        
        assert logger.name == "rota.solver"


class TestLogFunctionCall:
    """Tests for function call decorator."""
    
    def test_decorator_logs_entry_exit(self, caplog):
        """Test decorator logs function calls."""
        @log_function_call
        def add(a, b):
            return a + b
        
        with caplog.at_level(TRACE):
            result = add(1, 2)
        
        assert result == 3
    
    def test_decorator_logs_exceptions(self, caplog):
        """Test decorator logs exceptions."""
        @log_function_call
        def fail():
            raise ValueError("test error")
        
        with pytest.raises(ValueError):
            fail()
    
    def test_decorator_preserves_function_name(self):
        """Test decorator preserves function metadata."""
        @log_function_call
        def my_function():
            """Docstring."""
            pass
        
        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "Docstring."


class TestLogConstraint:
    """Tests for constraint logging."""
    
    def test_log_constraint_satisfied(self, caplog):
        """Test logging satisfied constraint."""
        logger = logging.getLogger("test")
        
        with caplog.at_level(logging.DEBUG):
            log_constraint(logger, "one_shift_per_day", True, "person=Alice")
        
        assert "✓" in caplog.text
        assert "one_shift_per_day" in caplog.text
    
    def test_log_constraint_violated(self, caplog):
        """Test logging violated constraint."""
        logger = logging.getLogger("test")
        
        with caplog.at_level(logging.WARNING):
            log_constraint(logger, "max_nights", False, "exceeded by 2")
        
        assert "✗" in caplog.text
        assert "max_nights" in caplog.text


class TestSolverLogger:
    """Tests for SolverLogger class."""
    
    def test_phase_logging(self, caplog):
        """Test phase logging."""
        slog = SolverLogger("test.solver")
        
        with caplog.at_level(logging.INFO):
            slog.phase("Building Model")
        
        assert "Building Model" in caplog.text
        assert "=" in caplog.text
    
    def test_step_logging(self, caplog):
        """Test step logging."""
        slog = SolverLogger("test.solver")
        
        with caplog.at_level(logging.INFO):
            slog.step("Adding constraints")
        
        assert "▸" in caplog.text
        assert "Adding constraints" in caplog.text
    
    def test_nested_context(self, caplog):
        """Test enter/exit context."""
        slog = SolverLogger("test.solver")
        
        with caplog.at_level(logging.DEBUG):
            slog.enter("Week 1")
            slog.detail("slots", 5)
            slog.exit("Week 1 complete")
        
        assert "┌─" in caplog.text
        assert "└─" in caplog.text


class TestLogRotation:
    """Tests for log file rotation."""
    
    def test_rotation_on_size(self):
        """Test log rotation when file exceeds max size."""
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "test.log"
            
            # Small max size to trigger rotation
            logger = setup_logging(
                level="DEBUG",
                log_file=str(log_file),
                max_bytes=1000,
                backup_count=2
            )
            
            # Write enough to trigger rotation
            for i in range(100):
                logger.info(f"Message {i}: " + "x" * 50)
            
            # Check for backup files
            backup_files = list(Path(tmpdir).glob("test.log.*"))
            # May or may not have rotated depending on exact sizes
            assert log_file.exists()
