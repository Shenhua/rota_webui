"""Pytest configuration and fixtures."""
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest

from rota.models.constraints import SolverConfig
from rota.models.person import Person


@pytest.fixture
def sample_people():
    """Create a sample team for testing."""
    return [
        Person(name="Alice", workdays_per_week=5, id=0),
        Person(name="Bob", workdays_per_week=5, prefers_night=True, id=1),
        Person(name="Charlie", workdays_per_week=4, no_evening=True, id=2),
        Person(name="Diana", workdays_per_week=4, max_nights=2, id=3),
        Person(name="Eve", workdays_per_week=5, edo_eligible=True, id=4),
    ]


@pytest.fixture
def default_config():
    """Default solver configuration."""
    return SolverConfig(weeks=2, time_limit_seconds=30)


@pytest.fixture
def team_dummy_path():
    """Path to the test data file."""
    return Path(__file__).parent.parent / "team_dummy.csv"
