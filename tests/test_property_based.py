"""
Property-Based Tests with Hypothesis
====================================
Tests that verify invariants hold for arbitrary valid inputs.
Falls back to regular pytest tests if Hypothesis not installed.
"""
import pytest

# Try Hypothesis import with graceful fallback
try:
    from hypothesis import given, strategies as st, settings, assume
    HYPOTHESIS_AVAILABLE = True
except ImportError:
    HYPOTHESIS_AVAILABLE = False
    # Create dummy decorator
    def given(*args, **kwargs):
        def decorator(func):
            return pytest.mark.skip(reason="Hypothesis not installed")(func)
        return decorator
    
    class st:
        @staticmethod
        def integers(*args, **kwargs):
            return None
        @staticmethod
        def text(*args, **kwargs):
            return None
        @staticmethod
        def booleans():
            return None
        @staticmethod
        def floats(*args, **kwargs):
            return None
        @staticmethod
        def lists(*args, **kwargs):
            return None
        @staticmethod
        def sampled_from(*args, **kwargs):
            return None


class TestPersonProperties:
    """Property-based tests for Person model."""
    
    @given(
        name=st.text(min_size=1, max_size=50),
        workdays=st.integers(min_value=1, max_value=7),
        prefers_night=st.booleans(),
        max_nights=st.integers(min_value=0, max_value=99),
    )
    def test_person_serialization_roundtrip(self, name, workdays, prefers_night, max_nights):
        """Person should survive to_dict -> from_dict roundtrip."""
        if not HYPOTHESIS_AVAILABLE:
            pytest.skip("Hypothesis not installed")
            
        from rota.models.person import Person
        
        # Skip if name is empty after strip
        if not name.strip():
            return
        
        person = Person(
            name=name,
            workdays_per_week=workdays,
            prefers_night=prefers_night,
            max_nights=max_nights,
        )
        
        data = person.to_dict()
        restored = Person.from_dict(data)
        
        assert restored.name == person.name
        assert restored.workdays_per_week == person.workdays_per_week
        assert restored.prefers_night == person.prefers_night
        assert restored.max_nights == person.max_nights
    
    @given(is_contractor=st.booleans())
    def test_contractor_flag_preserved(self, is_contractor):
        """is_contractor flag should survive serialization."""
        if not HYPOTHESIS_AVAILABLE:
            pytest.skip("Hypothesis not installed")
            
        from rota.models.person import Person
        
        person = Person(name="Test", is_contractor=is_contractor)
        data = person.to_dict()
        restored = Person.from_dict(data)
        
        assert restored.is_contractor == is_contractor


class TestSolverConfigProperties:
    """Property-based tests for SolverConfig."""
    
    @given(
        weeks=st.integers(min_value=1, max_value=52),
        time_limit=st.integers(min_value=5, max_value=600),
    )
    def test_config_serialization_roundtrip(self, weeks, time_limit):
        """SolverConfig should survive to_dict -> from_dict roundtrip."""
        if not HYPOTHESIS_AVAILABLE:
            pytest.skip("Hypothesis not installed")
            
        from rota.models.constraints import SolverConfig
        
        config = SolverConfig(
            weeks=weeks,
            time_limit_seconds=time_limit,
        )
        
        data = config.to_dict()
        restored = SolverConfig.from_dict(data)
        
        assert restored.weeks == config.weeks
        assert restored.time_limit_seconds == config.time_limit_seconds


class TestValidationProperties:
    """Property-based tests for validation logic."""
    
    @given(
        slots_vides=st.integers(min_value=0, max_value=100),
        doublons=st.integers(min_value=0, max_value=50),
        violations_48h=st.integers(min_value=0, max_value=20),
    )
    def test_score_is_non_negative(self, slots_vides, doublons, violations_48h):
        """Score should always be non-negative."""
        if not HYPOTHESIS_AVAILABLE:
            pytest.skip("Hypothesis not installed")
            
        from rota.solver.validation import score_solution, ValidationResult, FairnessMetrics
        
        validation = ValidationResult(
            slots_vides=slots_vides,
            doublons_jour=doublons,
            rolling_48h_violations=violations_48h,
        )
        fairness = FairnessMetrics()
        
        score = score_solution(validation, fairness)
        
        assert score >= 0, f"Score should be >= 0, got {score}"
    
    @given(violations_48h=st.integers(min_value=1, max_value=20))
    def test_48h_violations_increase_score(self, violations_48h):
        """More 48h violations should increase score (worse)."""
        if not HYPOTHESIS_AVAILABLE:
            pytest.skip("Hypothesis not installed")
            
        from rota.solver.validation import score_solution, ValidationResult, FairnessMetrics
        
        # Score with violations
        validation_with = ValidationResult(rolling_48h_violations=violations_48h)
        fairness = FairnessMetrics()
        score_with = score_solution(validation_with, fairness)
        
        # Score without violations
        validation_without = ValidationResult(rolling_48h_violations=0)
        score_without = score_solution(validation_without, fairness)
        
        assert score_with > score_without, "48h violations should increase score"


class TestConstraintInvariants:
    """Property tests for constraint invariants."""
    
    @given(
        nights=st.integers(min_value=0, max_value=10),
        consecutive_days=st.integers(min_value=1, max_value=7),
    )
    def test_max_nights_less_than_consecutive(self, nights, consecutive_days):
        """max_nights_sequence should logically be <= max_consecutive_days."""
        if not HYPOTHESIS_AVAILABLE:
            pytest.skip("Hypothesis not installed")
            
        # This is a property that should hold for valid configs
        # The Pydantic validator enforces this
        if nights <= consecutive_days:
            from rota.models.constraints import SolverConfig
            
            config = SolverConfig(
                max_nights_sequence=nights,
                max_consecutive_days=consecutive_days,
            )
            
            assert config.max_nights_sequence <= config.max_consecutive_days
