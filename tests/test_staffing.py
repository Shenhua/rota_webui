"""Tests for staffing derivation."""
import pytest
from rota.models.person import Person
from rota.solver.staffing import (
    derive_staffing,
    get_total_slots,
    get_week_slot_count,
    calculate_people_needed,
    WeekStaffing,
    JOURS,
)


class TestDeriveStaffing:
    """Tests for derive_staffing function."""
    
    @pytest.fixture
    def team_4j(self):
        """Team of 8 people working 4 days/week."""
        return [Person(name=f"P{i}", workdays_per_week=4) for i in range(8)]
    
    @pytest.fixture
    def mixed_team(self):
        """Mixed team: 12×4j + 4×3j = 60 days/week."""
        people = []
        for i in range(12):
            people.append(Person(name=f"4j_{i}", workdays_per_week=4, edo_eligible=True))
        for i in range(4):
            people.append(Person(name=f"3j_{i}", workdays_per_week=3, edo_eligible=False))
        return people
    
    def test_basic_staffing_no_edo(self, team_4j):
        """Test staffing with no EDO."""
        edo_plan = {}
        staffing = derive_staffing(team_4j, weeks=2, edo_plan=edo_plan)
        
        assert len(staffing) == 2
        assert 1 in staffing
        assert 2 in staffing
        
        # 8 people × 4 days = 32 person-days (even, no admin)
        assert staffing[1].total_person_days == 32
        assert staffing[1].edo_count == 0
    
    def test_staffing_with_edo(self, mixed_team):
        """Test staffing accounts for EDO."""
        # Week 1: half of 4j people get EDO (6 people)
        edo_plan = {
            1: {"4j_0", "4j_1", "4j_2", "4j_3", "4j_4", "4j_5"},
            2: {"4j_6", "4j_7", "4j_8", "4j_9", "4j_10", "4j_11"},
        }
        
        staffing = derive_staffing(mixed_team, weeks=2, edo_plan=edo_plan)
        
        # Total WD = 12×4 + 4×3 = 60
        # Week 1: 60 - 6 = 54 person-days
        assert staffing[1].edo_count == 6
        assert staffing[1].total_person_days == 54
    
    def test_night_pairs_per_day(self, team_4j):
        """Test that each day has at least 1 night pair."""
        edo_plan = {}
        staffing = derive_staffing(team_4j, weeks=1, edo_plan=edo_plan)
        
        for day in JOURS:
            assert staffing[1].slots[day]["N"] >= 1, f"Day {day} should have at least 1 night pair"
    
    # def test_admin_on_odd_days(self):
    #     """Test admin slot added when person-days is odd."""
    #     # Deprecated: derive_staffing uses FIXED_STAFFING, does not auto-assign Admin.
    #     pass
    
    def test_day_evening_distribution(self, team_4j):
        """Test D/E pairs distributed round-robin."""
        edo_plan = {}
        staffing = derive_staffing(team_4j, weeks=1, edo_plan=edo_plan)
        
        # Count total D and E slots
        total_d = sum(staffing[1].slots[d]["D"] for d in JOURS)
        total_e = sum(staffing[1].slots[d]["S"] for d in JOURS)
        
        # With FIXED_STAFFING: D=4, S=1 per day
        # Week (5 days): D=20, S=5
        assert total_d == 20
        assert total_e == 5
    
    def test_staffing_output_structure(self, team_4j):
        """Test WeekStaffing structure."""
        edo_plan = {}
        staffing = derive_staffing(team_4j, weeks=1, edo_plan=edo_plan)
        
        ws = staffing[1]
        assert isinstance(ws, WeekStaffing)
        assert ws.week == 1
        assert isinstance(ws.slots, dict)
        assert all(d in ws.slots for d in JOURS)
        assert all(s in ws.slots["Lun"] for s in ["D", "S", "N"])  # No Admin shift


class TestStaffingHelpers:
    """Tests for helper functions."""
    
    @pytest.fixture
    def sample_staffing(self):
        """Create sample staffing for testing."""
        people = [Person(name=f"P{i}", workdays_per_week=4) for i in range(8)]
        return derive_staffing(people, weeks=2, edo_plan={})
    
    def test_get_total_slots(self, sample_staffing):
        """Test get_total_slots."""
        total_n = get_total_slots(sample_staffing, "N")
        
        # 2 weeks × 5 days × 1 pair/day = 10 slots
        assert total_n == 10
    
    def test_get_week_slot_count(self, sample_staffing):
        """Test get_week_slot_count."""
        counts = get_week_slot_count(sample_staffing, 1)
        
        assert "D" in counts
        assert "S" in counts
        assert "N" in counts
        # Note: Admin (A) removed from system
        assert counts["N"] == 5  # 5 days × 1 pair
    
    def test_calculate_people_needed(self, sample_staffing):
        """Test calculate_people_needed accounts for pairs."""
        people_needed = calculate_people_needed(sample_staffing)
        
        # Night: 10 slots × 2 people = 20
        assert people_needed["N"] == 20


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_empty_team(self):
        """Test with empty team."""
        staffing = derive_staffing([], weeks=1, edo_plan={})
        
        assert len(staffing) == 1
        assert staffing[1].total_person_days == 0
    
    def test_single_person(self):
        """Test with single person."""
        people = [Person(name="Solo", workdays_per_week=5)]
        staffing = derive_staffing(people, weeks=1, edo_plan={})
        
        assert staffing[1].total_person_days == 5
    
    def test_zero_weeks(self):
        """Test with zero weeks."""
        people = [Person(name="P", workdays_per_week=4)]
        staffing = derive_staffing(people, weeks=0, edo_plan={})
        
        assert len(staffing) == 0
