"""Tests for multi-seed optimizer."""
import pytest

from rota.models.constraints import SolverConfig
from rota.models.person import Person
from rota.solver.optimizer import optimize, solve_with_validation


class TestOptimize:
    """Tests for optimize function."""
    
    @pytest.fixture
    def team(self):
        """Standard test team."""
        people = []
        for i in range(15):
            people.append(Person(name=f"P{i}", workdays_per_week=4))
        for i in range(5):
            people.append(Person(name=f"Q{i}", workdays_per_week=3))
        return people
    
    def test_single_try(self, team):
        """Test optimization with single try."""
        config = SolverConfig(weeks=1, forbid_night_to_day=False, time_limit_seconds=30)
        
        schedule, best_seed, best_score = optimize(team, config, tries=1, seed=42)
        
        assert schedule.status in ["optimal", "feasible"]
        assert best_seed == 42
        assert best_score < float("inf")
    
    def test_multiple_tries(self, team):
        """Test optimization finds best across tries."""
        config = SolverConfig(weeks=1, forbid_night_to_day=False, time_limit_seconds=30)
        
        # With OR-Tools, multiple tries should all give similar results
        schedule, best_seed, best_score = optimize(team, config, tries=3, seed=100)
        
        assert schedule.status in ["optimal", "feasible"]
        assert best_seed >= 100
        assert best_score < float("inf")
    
    def test_stats_recorded(self, team):
        """Test optimization stats are recorded."""
        config = SolverConfig(weeks=1, forbid_night_to_day=False, time_limit_seconds=30)
        
        schedule, _, _ = optimize(team, config, tries=2, seed=1)
        
        assert "best_seed" in schedule.stats
        assert "tries" in schedule.stats
        assert schedule.stats["tries"] == 2


class TestSolveWithValidation:
    """Tests for solve_with_validation function."""
    
    @pytest.fixture
    def team(self):
        """Standard test team."""
        return [Person(name=f"P{i}", workdays_per_week=4) for i in range(16)]
    
    def test_returns_schedule_and_score(self, team):
        """Test returns schedule and score."""
        config = SolverConfig(weeks=1, forbid_night_to_day=False, time_limit_seconds=30)
        
        schedule, score = solve_with_validation(team, config)
        
        assert schedule.status in ["optimal", "feasible"]
        assert score < float("inf")
        assert schedule.score == score
    
    def test_infeasible_returns_inf(self):
        """Test infeasible returns infinite score."""
        # Too few people
        team = [Person(name="Solo", workdays_per_week=2)]
        config = SolverConfig(weeks=1, time_limit_seconds=10)
        
        schedule, score = solve_with_validation(team, config)
        
        # May be infeasible or feasible depending on staffing
        if schedule.status == "infeasible":
            assert score == float("inf")
