"""Tests for EDO system."""
import pytest

from rota.models.person import Person
from rota.solver.edo import (
    EDOPlan,
    build_edo_plan,
    get_edo_count_per_week,
    is_edo_day,
    mark_edo_in_schedule,
)


class TestBuildEDOPlan:
    """Tests for build_edo_plan function."""
    
    @pytest.fixture
    def eligible_team(self):
        """Team with 8 EDO-eligible people."""
        return [
            Person(name=f"P{i}", workdays_per_week=4, edo_eligible=True)
            for i in range(8)
        ]
    
    @pytest.fixture
    def mixed_team(self):
        """Mixed team: some eligible, some not."""
        people = []
        for i in range(6):
            people.append(Person(name=f"E{i}", workdays_per_week=4, edo_eligible=True))
        for i in range(4):
            people.append(Person(name=f"N{i}", workdays_per_week=3, edo_eligible=False))
        return people
    
    def test_basic_plan_structure(self, eligible_team):
        """Test EDO plan has correct structure."""
        plan = build_edo_plan(eligible_team, weeks=4)
        
        assert isinstance(plan, EDOPlan)
        assert len(plan.plan) == 4
        assert all(w in plan.plan for w in range(1, 5))
    
    def test_alternation_half_half(self, eligible_team):
        """Test 50/50 alternation by week."""
        plan = build_edo_plan(eligible_team, weeks=4)
        
        # Week 1 (odd) and Week 2 (even) should have different people
        week1_edo = plan.plan[1]
        week2_edo = plan.plan[2]
        
        # Should have 4 people each (8 / 2)
        assert len(week1_edo) == 4
        assert len(week2_edo) == 4
        
        # Should be disjoint (different halves)
        assert len(week1_edo & week2_edo) == 0
    
    def test_odd_even_pattern(self, eligible_team):
        """Test odd weeks match, even weeks match."""
        plan = build_edo_plan(eligible_team, weeks=4)
        
        # Odd weeks should have same people
        assert plan.plan[1] == plan.plan[3]
        
        # Even weeks should have same people  
        assert plan.plan[2] == plan.plan[4]
    
    def test_only_eligible_get_edo(self, mixed_team):
        """Test non-eligible people don't get EDO."""
        plan = build_edo_plan(mixed_team, weeks=2)
        
        all_edo = set()
        for week_edo in plan.plan.values():
            all_edo.update(week_edo)
        
        # Only E* names should appear
        assert all(name.startswith("E") for name in all_edo)
        assert not any(name.startswith("N") for name in all_edo)
    
    def test_fixed_day_mapping(self):
        """Test fixed EDO day is captured."""
        people = [
            Person(name="Fixed", edo_eligible=True, edo_fixed_day="Mer"),
            Person(name="NoFix", edo_eligible=True, edo_fixed_day=""),
        ]
        
        plan = build_edo_plan(people, weeks=2)
        
        assert plan.fixed["Fixed"] == "Mer"
        assert plan.fixed["NoFix"] == ""
    
    def test_global_fixed_day(self):
        """Test global fixed day override."""
        people = [
            Person(name="P1", edo_eligible=True),
            Person(name="P2", edo_eligible=True),
        ]
        
        plan = build_edo_plan(people, weeks=2, fixed_global="Jeu")
        
        assert plan.fixed["P1"] == "Jeu"
        assert plan.fixed["P2"] == "Jeu"
    
    def test_person_fixed_overrides_global(self):
        """Test person's fixed day takes precedence over global."""
        people = [
            Person(name="Override", edo_eligible=True, edo_fixed_day="Lun"),
        ]
        
        plan = build_edo_plan(people, weeks=2, fixed_global="Ven")
        
        assert plan.fixed["Override"] == "Lun"


class TestEDOCountPerWeek:
    """Tests for get_edo_count_per_week."""
    
    def test_count_per_week(self):
        """Test counting EDOs per week."""
        people = [Person(name=f"P{i}", edo_eligible=True) for i in range(4)]
        plan = build_edo_plan(people, weeks=2)
        
        counts = get_edo_count_per_week(plan)
        
        assert counts[1] == 2
        assert counts[2] == 2


class TestIsEDODay:
    """Tests for is_edo_day function."""
    
    def test_not_in_plan(self):
        """Test person not in EDO plan."""
        plan = EDOPlan(plan={1: {"Alice"}}, fixed={})
        
        assert not is_edo_day(plan, "Bob", 1, "Lun", {})
    
    def test_fixed_day_available(self):
        """Test fixed day when available."""
        plan = EDOPlan(plan={1: {"Alice"}}, fixed={"Alice": "Mer"})
        
        assert is_edo_day(plan, "Alice", 1, "Mer", {})
        assert not is_edo_day(plan, "Alice", 1, "Lun", {})
    
    def test_fixed_day_busy(self):
        """Test fixed day when busy."""
        plan = EDOPlan(plan={1: {"Alice"}}, fixed={"Alice": "Mer"})
        assigned = {("Alice", 1, "Mer"): "J"}  # Wednesday busy
        
        assert not is_edo_day(plan, "Alice", 1, "Mer", assigned)


class TestMarkEDOInSchedule:
    """Tests for mark_edo_in_schedule."""
    
    def test_mark_edo_fixed_day(self):
        """Test marking EDO on fixed day."""
        plan = EDOPlan(plan={1: {"Alice"}}, fixed={"Alice": "Mer"})
        schedule = {}
        
        day = mark_edo_in_schedule(plan, "Alice", 1, schedule)
        
        assert day == "Mer"
        assert schedule[("Alice", 1, "Mer")] == "EDO"
    
    def test_mark_edo_first_off(self):
        """Test marking EDO on first OFF day."""
        plan = EDOPlan(plan={1: {"Alice"}}, fixed={"Alice": ""})
        schedule = {
            ("Alice", 1, "Lun"): "J",
            ("Alice", 1, "Mar"): "S",
        }
        
        day = mark_edo_in_schedule(plan, "Alice", 1, schedule)
        
        assert day == "Mer"  # First unassigned day
        assert schedule[("Alice", 1, "Mer")] == "EDO"
    
    def test_mark_edo_conflict(self):
        """Test EDO* when fixed day is busy."""
        plan = EDOPlan(plan={1: {"Alice"}}, fixed={"Alice": "Lun"})
        schedule = {("Alice", 1, "Lun"): "N"}  # Monday busy
        
        day = mark_edo_in_schedule(plan, "Alice", 1, schedule)
        
        # Should mark first available as EDO*
        assert day == "Mar"
        assert schedule[("Alice", 1, "Mar")] == "EDO*"
    
    def test_not_in_plan(self):
        """Test no EDO for person not in plan."""
        plan = EDOPlan(plan={1: {"Alice"}}, fixed={})
        schedule = {}
        
        day = mark_edo_in_schedule(plan, "Bob", 1, schedule)
        
        assert day is None


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_empty_team(self):
        """Test with no eligible people."""
        people = [Person(name="P", edo_eligible=False)]
        plan = build_edo_plan(people, weeks=2)
        
        assert all(len(s) == 0 for s in plan.plan.values())
    
    def test_single_eligible(self):
        """Test with single eligible person."""
        people = [Person(name="Solo", edo_eligible=True)]
        plan = build_edo_plan(people, weeks=4)
        
        # Single person: rounds up to 1, so all in first half
        assert "Solo" in plan.plan[1]  # Odd week
        assert "Solo" not in plan.plan[2]  # Even week
    
    def test_two_eligible(self):
        """Test with two eligible people."""
        people = [
            Person(name="A", edo_eligible=True),
            Person(name="B", edo_eligible=True),
        ]
        plan = build_edo_plan(people, weeks=2)
        
        # Should split 1-1
        assert len(plan.plan[1]) == 1
        assert len(plan.plan[2]) == 1
        assert plan.plan[1] != plan.plan[2]
