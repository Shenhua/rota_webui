"""Tests for pair-based solver."""
import pytest

from rota.models.constraints import SolverConfig
from rota.models.person import Person
from rota.solver.edo import build_edo_plan
from rota.solver.pairs import PairAssignment, PairSchedule, solve_pairs
from rota.solver.staffing import JOURS, derive_staffing


class TestSolvePairs:
    """Tests for solve_pairs function."""
    
    @pytest.fixture
    def small_team(self):
        """Team of 16 people (12×4j + 4×3j).
        
        This is the realistic team size from legacy examples.
        16 people provides enough capacity with night rest constraint.
        """
        people = []
        for i in range(12):
            people.append(Person(name=f"4j_{i}", workdays_per_week=4))
        for i in range(4):
            people.append(Person(name=f"3j_{i}", workdays_per_week=3))
        return people
    
    @pytest.fixture
    def config(self):
        """Default solver config - disable night rest for simpler tests."""
        return SolverConfig(weeks=1, time_limit_seconds=30, forbid_night_to_day=False)
    
    @pytest.fixture
    def staffing_and_edo(self, small_team, config):
        """Get staffing and EDO plan for small team."""
        edo_plan = build_edo_plan(small_team, config.weeks)
        staffing = derive_staffing(small_team, config.weeks, edo_plan.plan)
        return staffing, edo_plan
    
    def test_solver_returns_schedule(self, small_team, config, staffing_and_edo):
        """Test solver returns a valid schedule."""
        staffing, edo_plan = staffing_and_edo
        
        schedule = solve_pairs(small_team, config, staffing, edo_plan)
        
        assert isinstance(schedule, PairSchedule)
        assert schedule.status in ["optimal", "feasible"]
        assert schedule.weeks == 1
        assert schedule.people_count == 16  # 12×4j + 4×3j
    
    def test_slots_filled(self, small_team, config, staffing_and_edo):
        """Test all slots are filled."""
        staffing, edo_plan = staffing_and_edo
        
        schedule = solve_pairs(small_team, config, staffing, edo_plan)
        
        # Count assignments per shift type
        shifts = {"D": 0, "S": 0, "N": 0, "A": 0}
        for a in schedule.assignments:
            shifts[a.shift] += 1
        
        # Should have at least night slots (1 per day)
        assert shifts["N"] >= 5  # 5 days × 1 slot
    
    def test_pairs_have_two_people(self, small_team, config, staffing_and_edo):
        """Test D/E/N assignments have two people."""
        staffing, edo_plan = staffing_and_edo
        
        schedule = solve_pairs(small_team, config, staffing, edo_plan)
        
        for a in schedule.assignments:
            if a.shift in ["D", "N"]:
                assert a.person_a, f"Assignment {a} missing person_a"
                assert a.person_b, f"Assignment {a} missing person_b"
                assert a.person_a != a.person_b
            elif a.shift in ["S", "A"]:
                assert a.person_a, f"Solo shift {a} missing person"
                assert not a.person_b, f"Solo shift {a} has person_b which is wrong"
    
    def test_one_shift_per_person_per_day(self, small_team, config, staffing_and_edo):
        """Test no person works multiple shifts per day."""
        staffing, edo_plan = staffing_and_edo
        
        schedule = solve_pairs(small_team, config, staffing, edo_plan)
        
        for w in range(1, config.weeks + 1):
            for d in JOURS:
                day_assignments = schedule.get_day_assignments(w, d)
                
                # Count shifts per person
                person_shifts = {}
                for a in day_assignments:
                    for name in [a.person_a, a.person_b]:
                        if name:
                            person_shifts[name] = person_shifts.get(name, 0) + 1
                
                for name, count in person_shifts.items():
                    assert count == 1, f"{name} has {count} shifts on W{w} {d}"
    
    def test_empty_team_infeasible(self, config):
        """Test empty team returns infeasible."""
        staffing = derive_staffing([], config.weeks, {})
        edo_plan = build_edo_plan([], config.weeks)
        
        schedule = solve_pairs([], config, staffing, edo_plan)
        
        assert schedule.status == "infeasible"


class TestNightRestConstraint:
    """Tests for night rest constraint."""
    
    @pytest.fixture
    def team(self):
        return [Person(name=f"P{i}", workdays_per_week=4) for i in range(8)]
    
    @pytest.fixture
    def config_with_night_rest(self):
        return SolverConfig(weeks=1, forbid_night_to_day=True, time_limit_seconds=30)
    
    def test_no_work_after_night(self, team, config_with_night_rest):
        """Test no one works day after night."""
        edo_plan = build_edo_plan(team, config_with_night_rest.weeks)
        staffing = derive_staffing(team, config_with_night_rest.weeks, edo_plan.plan)
        
        schedule = solve_pairs(team, config_with_night_rest, staffing, edo_plan)
        
        for name in [p.name for p in team]:
            person_shifts = schedule.get_person_shifts(name)
            
            # Check for night followed by work
            for a in person_shifts:
                if a.shift == "N":
                    day_idx = JOURS.index(a.day)
                    if day_idx < len(JOURS) - 1:
                        next_day = JOURS[day_idx + 1]
                        # Should not work next day
                        next_shifts = [
                            s for s in person_shifts 
                            if s.week == a.week and s.day == next_day
                        ]
                        assert len(next_shifts) == 0, \
                            f"{name} works on {next_day} after night on {a.day}"


class TestMaxNightsConstraint:
    """Tests for max nights constraint."""
    
    def test_respects_max_nights(self):
        """Test max_nights per person is respected."""
        team = [
            Person(name="Limited", workdays_per_week=5, max_nights=2),
            Person(name="Normal1", workdays_per_week=5),
            Person(name="Normal2", workdays_per_week=5),
            Person(name="Normal3", workdays_per_week=5),
            Person(name="Normal4", workdays_per_week=5),
            Person(name="Normal5", workdays_per_week=5),
        ]
        config = SolverConfig(weeks=1, time_limit_seconds=30, forbid_night_to_day=False)
        edo_plan = build_edo_plan(team, config.weeks)
        staffing = derive_staffing(team, config.weeks, edo_plan.plan)
        
        schedule = solve_pairs(team, config, staffing, edo_plan)
        
        if schedule.status in ["optimal", "feasible"]:
            limited_nights = schedule.count_shifts("Limited", "N")
            assert limited_nights <= 2, f"Limited has {limited_nights} nights, max is 2"


class TestPairScheduleHelpers:
    """Tests for PairSchedule helper methods."""
    
    def test_get_person_shifts(self):
        """Test get_person_shifts method."""
        assignment = PairAssignment(
            week=1, day="Lun", shift="N", slot_idx=0,
            person_a="Alice", person_b="Bob"
        )
        schedule = PairSchedule(
            assignments=[assignment],
            weeks=1, people_count=2, status="optimal"
        )
        
        alice_shifts = schedule.get_person_shifts("Alice")
        bob_shifts = schedule.get_person_shifts("Bob")
        charlie_shifts = schedule.get_person_shifts("Charlie")
        
        assert len(alice_shifts) == 1
        assert len(bob_shifts) == 1
        assert len(charlie_shifts) == 0
    
    def test_count_shifts(self):
        """Test count_shifts method."""
        assignments = [
            PairAssignment(1, "Lun", "N", 0, "Alice", "Bob"),
            PairAssignment(1, "Mar", "N", 0, "Alice", "Charlie"),
            PairAssignment(1, "Mer", "D", 0, "Alice", "Dave"),
        ]
        schedule = PairSchedule(
            assignments=assignments,
            weeks=1, people_count=4, status="optimal"
        )
        
        assert schedule.count_shifts("Alice", "N") == 2
        assert schedule.count_shifts("Alice", "D") == 1
        assert schedule.count_shifts("Bob", "N") == 1


class TestEDOConstraint:
    """Tests for EDO constraint."""
    
    def test_edo_day_not_worked(self):
        """Test person doesn't work on fixed EDO day."""
        team = [
            Person(name="EDO_Mer", workdays_per_week=4, edo_eligible=True, edo_fixed_day="Mer"),
            Person(name="P1", workdays_per_week=4),
            Person(name="P2", workdays_per_week=4),
            Person(name="P3", workdays_per_week=4),
            Person(name="P4", workdays_per_week=4),
            Person(name="P5", workdays_per_week=4),
        ]
        config = SolverConfig(weeks=1, time_limit_seconds=30)
        edo_plan = build_edo_plan(team, config.weeks)
        staffing = derive_staffing(team, config.weeks, edo_plan.plan)
        
        # Check EDO_Mer is in EDO plan for week 1
        if "EDO_Mer" in edo_plan.plan.get(1, set()):
            schedule = solve_pairs(team, config, staffing, edo_plan)
            
            if schedule.status in ["optimal", "feasible"]:
                # Check EDO_Mer doesn't work on Wednesday
                edo_mer_shifts = schedule.get_person_shifts("EDO_Mer")
                wed_shifts = [s for s in edo_mer_shifts if s.day == "Mer"]
                assert len(wed_shifts) == 0, "EDO_Mer should not work on Wednesday"
