"""
Tests for SessionStateManager
=============================
"""
import pytest
from unittest.mock import MagicMock, patch
from app.state.session import SessionStateManager

@pytest.fixture
def mock_streamlit():
    with patch("app.state.session.st") as mock_st:
        mock_st.session_state = {}
        yield mock_st

def test_init_state(mock_streamlit):
    """Test initialization of defaults."""
    SessionStateManager.init_state()
    
    assert "people" in mock_streamlit.session_state
    assert "config_weeks" in mock_streamlit.session_state
    assert mock_streamlit.session_state["config_weeks"] == 4

def test_property_access(mock_streamlit):
    """Test getter and setter access."""
    SessionStateManager.init_state()
    state = SessionStateManager()
    
    # Defaults
    assert state.schedule is None
    
    # Set value
    mock_schedule = MagicMock()
    state.schedule = mock_schedule
    
    assert mock_streamlit.session_state["schedule"] == mock_schedule
    assert state.schedule == mock_schedule

def test_clear_results(mock_streamlit):
    """Test clearing results."""
    SessionStateManager.init_state()
    state = SessionStateManager()
    
    state.schedule = MagicMock()
    state.best_score = 100.0
    
    state.clear_results()
    
    assert state.schedule is None
    assert state.best_score is None
