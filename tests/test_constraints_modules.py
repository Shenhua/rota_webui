"""
Tests for Constraint Builders
=============================
Unit tests for the extracted constraint modules.
"""
import pytest
from unittest.mock import MagicMock, patch
from ortools.sat.python import cp_model

from rota.models.constraints import SolverConfig, FairnessMode
from rota.models.person import Person
from rota.solver.edo import EDOPlan


class TestConstraintImport:
    """Test that constraint modules are importable."""
    
    def test_import_hard_constraints(self):
        """Verify all hard constraint builders can be imported."""
        from rota.solver.constraints import (
            add_staffing_constraints,
            add_one_shift_per_day,
            add_night_rest_constraint,
            add_max_nights_constraint,
            add_consecutive_nights_constraint,
            add_edo_constraints,
            add_weekly_hours_constraint,
            add_rolling_48h_constraint,
            add_consecutive_days_constraint,
            add_no_evening_preference,
            add_contractor_pair_constraint,
        )
        # All imports successful
        assert callable(add_staffing_constraints)
        assert callable(add_one_shift_per_day)
        assert callable(add_night_rest_constraint)
        assert callable(add_max_nights_constraint)
        assert callable(add_consecutive_nights_constraint)
        assert callable(add_edo_constraints)
        assert callable(add_weekly_hours_constraint)
        assert callable(add_rolling_48h_constraint)
        assert callable(add_consecutive_days_constraint)
        assert callable(add_no_evening_preference)
        assert callable(add_contractor_pair_constraint)
    
    def test_import_objective_builders(self):
        """Verify all objective builders can be imported."""
        from rota.solver.constraints.objectives import (
            build_cohorts,
            add_unfilled_penalty,
            add_night_fairness_objective,
            add_soir_fairness_objective,
            add_workday_target_objective,
            add_clopening_penalty,
        )
        assert callable(build_cohorts)
        assert callable(add_unfilled_penalty)
        assert callable(add_night_fairness_objective)
        assert callable(add_soir_fairness_objective)
        assert callable(add_workday_target_objective)
        assert callable(add_clopening_penalty)


class TestCohortBuilding:
    """Test cohort building logic."""
    
    def test_cohorts_by_workdays(self):
        """Test grouping by workdays_per_week (default mode)."""
        from rota.solver.constraints.objectives import build_cohorts
        
        people = [
            Person(name="Alice", workdays_per_week=5),
            Person(name="Bob", workdays_per_week=5),
            Person(name="Charlie", workdays_per_week=4),
        ]
        names = [p.name for p in people]
        name_to_person = {p.name: p for p in people}
        
        config = MagicMock()
        config.fairness_mode = FairnessMode.BY_WORKDAYS
        
        cohorts = build_cohorts(names, name_to_person, config)
        
        assert "5j" in cohorts
        assert "4j" in cohorts
        assert set(cohorts["5j"]) == {"Alice", "Bob"}
        assert cohorts["4j"] == ["Charlie"]
    
    def test_cohorts_by_team(self):
        """Test grouping by team."""
        from rota.solver.constraints.objectives import build_cohorts
        
        people = [
            Person(name="Alice", team="Team A"),
            Person(name="Bob", team="Team A"),
            Person(name="Charlie", team="Team B"),
        ]
        names = [p.name for p in people]
        name_to_person = {p.name: p for p in people}
        
        config = MagicMock()
        config.fairness_mode = FairnessMode.BY_TEAM
        
        cohorts = build_cohorts(names, name_to_person, config)
        
        assert "Team A" in cohorts
        assert "Team B" in cohorts
        assert set(cohorts["Team A"]) == {"Alice", "Bob"}
        assert cohorts["Team B"] == ["Charlie"]
    
    def test_cohorts_global(self):
        """Test global (all in one) cohort."""
        from rota.solver.constraints.objectives import build_cohorts
        
        people = [
            Person(name="Alice"),
            Person(name="Bob"),
        ]
        names = [p.name for p in people]
        name_to_person = {p.name: p for p in people}
        
        config = MagicMock()
        config.fairness_mode = FairnessMode.GLOBAL
        
        cohorts = build_cohorts(names, name_to_person, config)
        
        assert "all" in cohorts
        assert set(cohorts["all"]) == {"Alice", "Bob"}


class TestBaseClassesImport:
    """Test that base solver classes are importable."""
    
    def test_import_base_solver(self):
        """Verify base solver classes can be imported."""
        from rota.solver.base import (
            SolverStatus,
            SolverResult,
            BaseSolver,
            BaseSchedule,
            Validatable,
            Scoreable,
        )
        
        assert SolverStatus.OPTIMAL.value == "optimal"
        assert SolverStatus.INFEASIBLE.value == "infeasible"
        
        # Test SolverResult
        result = SolverResult(
            status=SolverStatus.OPTIMAL,
            solve_time_seconds=1.5,
            message="Success"
        )
        assert result.is_success
        assert result.solve_time_seconds == 1.5


class TestEdgeCases:
    """Test edge cases identified in the audit."""
    
    def test_contractor_preserved_in_from_dict(self):
        """Verify is_contractor is preserved during serialization."""
        person = Person(name="Contractor A", is_contractor=True)
        data = person.to_dict()
        
        assert data["is_contractor"] == True
        
        restored = Person.from_dict(data)
        assert restored.is_contractor == True
    
    def test_duplicate_names_rejected(self):
        """Verify CSV loader rejects duplicate names."""
        import pandas as pd
        from rota.io.csv_loader import load_team
        
        df = pd.DataFrame({
            "name": ["Alice", "Bob", "Alice"],  # Duplicate Alice
            "workdays_per_week": [5, 5, 5],
        })
        
        with pytest.raises(ValueError) as excinfo:
            load_team(df)
        
        assert "Duplicate names" in str(excinfo.value)
        assert "Alice" in str(excinfo.value)
    
    def test_48h_violations_affect_score(self):
        """Verify 48h violations have non-zero weight in scoring."""
        from rota.solver.validation import score_solution, ValidationResult, FairnessMetrics
        
        # Create validation result with 48h violation
        validation = ValidationResult(
            rolling_48h_violations=1
        )
        fairness = FairnessMetrics()
        
        score = score_solution(validation, fairness)
        
        # With non-zero weight, score should be > 0 due to the violation
        assert score >= 5.0  # 5.0 * 1 violation = 5.0 minimum
    
    def test_edo_constraint_applies_to_non_fixed_day(self):
        """Verify EDO people without fixed day get constraint applied."""
        from rota.solver.constraints import add_edo_constraints
        
        model = cp_model.CpModel()
        days = ["Lun", "Mar", "Mer", "Jeu", "Ven"]
        
        # Create person_works variables
        person_works = {"Alice": {1: {}}}
        for d in days:
            person_works["Alice"][1][d] = model.NewBoolVar(f"works_Alice_1_{d}")
        
        # EDO plan: Alice gets EDO in week 1 but no fixed day
        edo_plan = EDOPlan(
            plan={1: {"Alice"}},
            fixed={"Alice": ""}  # No fixed day
        )
        
        # Add constraints
        add_edo_constraints(model, person_works, ["Alice"], 1, days, edo_plan)
        
        # Verify model has constraints (at least one OFF day required)
        assert model.Proto().constraints  # Should have at least one constraint
