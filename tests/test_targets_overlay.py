"""
Tests for the legacy bridge (targets_overlay.py).
Ensures that the refactor from engine.py to pairs.py maintains API compatibility.
"""
import pandas as pd
import pytest

from rota.engine.targets_overlay import SolveResult, solve


@pytest.fixture
def simple_team_df():
    """Create a simple team DataFrame."""
    return pd.DataFrame([
        {
            "name": f"P{i}",
            "workdays_per_week": 4 if i < 8 else 3,
            "prefers_night": i % 4 == 0,
            "team": "A" if i < 6 else "B",
             "edo_eligible": True,
        }
        for i in range(12)  # 12 people
    ])

def test_solve_returns_correct_result_structure(simple_team_df):
    """Test that solve() returns a SolveResult with expected fields."""
    
    # Simple config object (could be argparse Namespace or class)
    class LegacyConfig:
        weeks = 1
        tries = 1
        time_limit_seconds = 5
        fairness_mode = "by-wd"
    
    cfg = LegacyConfig()
    
    result = solve(simple_team_df, cfg=cfg)
    
    assert isinstance(result, SolveResult)
    assert isinstance(result.assignments, pd.DataFrame)
    assert not result.assignments.empty
    
    # Check DataFrame columns (Legacy format)
    expected_cols = ["name", "week", "day", "shift"]
    for col in expected_cols:
        assert col in result.assignments.columns
        
    # Check Summary
    assert "score" in result.summary
    assert "status" in result.summary
    assert result.summary["weeks"] == 1
    assert result.summary["people"] == 12
    
    # Check Metrics
    assert "violations" in result.metrics_json
    assert "fairness" in result.metrics_json

def test_solve_ignores_tries_parameter(simple_team_df):
    """
    Legacy bridge explicitly ignores 'tries'.
    Refactored version supports it, but verify it runs regardless.
    """
    class LegacyConfig:
        weeks = 1
        tries = 20 # High number, should be fast if ignored or parallel
        time_limit_seconds = 2
    
    cfg = LegacyConfig()
    result = solve(simple_team_df, cfg=cfg)
    assert result.summary["status"] in ["optimal", "feasible", "unknown"]

def test_solve_handles_csv_path(tmp_path, simple_team_df):
    """Test csv loading from path."""
    csv_path = tmp_path / "team.csv"
    simple_team_df.to_csv(csv_path, index=False)
    
    class LegacyConfig:
        weeks = 1
        time_limit_seconds = 5
        
    result = solve(str(csv_path), cfg=LegacyConfig())
    assert not result.assignments.empty
