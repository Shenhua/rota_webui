"""Tests for validation and scoring."""
import pytest
from rota.models.person import Person
from rota.models.constraints import SolverConfig
from rota.solver.staffing import derive_staffing, JOURS
from rota.solver.edo import build_edo_plan
from rota.solver.pairs import solve_pairs, PairSchedule, PairAssignment
from rota.solver.validation import (
    validate_schedule,
    calculate_fairness,
    score_solution,
    ValidationResult,
    FairnessMetrics,
)


class TestValidateSchedule:
    """Tests for validate_schedule function."""
    
    @pytest.fixture
    def team(self):
        """Standard test team."""
        people = []
        for i in range(12):
            people.append(Person(name=f"P{i}", workdays_per_week=4))
        for i in range(4):
            people.append(Person(name=f"Q{i}", workdays_per_week=3))
        return people
    
    @pytest.fixture
    def schedule_and_context(self, team):
        """Generate a valid schedule for testing."""
        config = SolverConfig(weeks=1, forbid_night_to_day=False, time_limit_seconds=30)
        edo_plan = build_edo_plan(team, config.weeks)
        staffing = derive_staffing(team, config.weeks, edo_plan.plan)
        schedule = solve_pairs(team, config, staffing, edo_plan)
        return schedule, team, edo_plan, staffing
    
    def test_validate_returns_result(self, schedule_and_context):
        """Test validate returns a ValidationResult."""
        schedule, team, edo_plan, staffing = schedule_and_context
        
        result = validate_schedule(schedule, team, edo_plan, staffing)
        
        assert isinstance(result, ValidationResult)
    
    def test_valid_schedule_has_no_duplicates(self, schedule_and_context):
        """Test valid schedule has no duplicates."""
        schedule, team, edo_plan, staffing = schedule_and_context
        
        result = validate_schedule(schedule, team, edo_plan, staffing)
        
        assert result.doublons_jour == 0
    
    def test_validation_result_as_dict(self):
        """Test as_dict method."""
        result = ValidationResult(slots_vides=2, doublons_jour=1)
        
        d = result.as_dict()
        
        assert d["Slots_vides"] == 2
        assert d["doublons_jour"] == 1


class TestCalculateFairness:
    """Tests for calculate_fairness function."""
    
    def test_fairness_with_empty_schedule(self):
        """Test fairness with empty schedule."""
        schedule = PairSchedule(assignments=[], weeks=1, people_count=0, status="optimal")
        people = []
        
        fairness = calculate_fairness(schedule, people)
        
        assert fairness.night_std == 0.0
        assert fairness.eve_std == 0.0
    
    def test_fairness_by_workdays(self):
        """Test fairness grouping by workdays."""
        people = [
            Person(name="A", workdays_per_week=4),
            Person(name="B", workdays_per_week=4),
            Person(name="C", workdays_per_week=3),
        ]
        assignments = [
            PairAssignment(1, "Lun", "N", 0, "A", "B"),
            PairAssignment(1, "Mar", "N", 0, "A", "B"),  # A and B have 2 nights each
        ]
        schedule = PairSchedule(assignments=assignments, weeks=1, people_count=3, status="optimal")
        
        fairness = calculate_fairness(schedule, people, cohort_mode="by-wd")
        
        # 4j cohort: A=2, B=2 -> std dev = 0
        assert "4j" in fairness.night_std_by_cohort
        assert fairness.night_std_by_cohort["4j"] == 0.0


class TestScoreSolution:
    """Tests for score_solution function."""
    
    def test_perfect_schedule_score_zero(self):
        """Test perfect schedule has score 0 (excluding fairness)."""
        validation = ValidationResult()  # All zeros
        fairness = FairnessMetrics()  # All zeros
        
        score = score_solution(validation, fairness)
        
        assert score == 0.0
    
    def test_score_weights(self):
        """Test scoring weights match legacy."""
        # One of each violation
        validation = ValidationResult(
            slots_vides=1,
            doublons_jour=1,
            nuit_suivie_travail=1,
            soir_vers_jour=1,
            ecarts_hebdo_jours=1,
            ecarts_horizon_personnes=1,
        )
        fairness = FairnessMetrics(night_std=1.0, eve_std=1.0)
        
        score = score_solution(validation, fairness)
        
        # 10*1 + 5*1 + 3*1 + 1*1 + 2*1 + 2*1 + 10*1 + 3*1 = 36
        assert score == 36.0
    
    def test_slots_vides_highest_weight(self):
        """Test unfilled slots have highest weight."""
        validation = ValidationResult(slots_vides=1)
        fairness = FairnessMetrics()
        
        score = score_solution(validation, fairness)
        
        assert score == 10.0  # Weight = 10


class TestValidationResult:
    """Tests for ValidationResult class."""
    
    def test_has_critical_issues_false(self):
        """Test no critical issues."""
        result = ValidationResult(soir_vers_jour=5)  # Not critical
        
        assert not result.has_critical_issues
    
    def test_has_critical_issues_true_slots(self):
        """Test critical issue: unfilled slots."""
        result = ValidationResult(slots_vides=1)
        
        assert result.has_critical_issues
    
    def test_has_critical_issues_true_duplicates(self):
        """Test critical issue: duplicates."""
        result = ValidationResult(doublons_jour=1)
        
        assert result.has_critical_issues
