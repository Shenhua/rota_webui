"""Tests for data models."""
from rota.models.constraints import FairnessMode, SolverConfig, WeekendMode
from rota.models.person import Person
from rota.models.schedule import Assignment, Schedule
from rota.models.shift import ALL_DAYS, WEEKDAYS, WEEKEND, ShiftType, normalize_day


class TestShiftType:
    """Tests for ShiftType enum."""
    
    def test_shift_values(self):
        """Test shift type values match expected codes."""
        assert ShiftType.DAY.value == "J"
        assert ShiftType.EVENING.value == "S"
        assert ShiftType.NIGHT.value == "N"
        assert ShiftType.ADMIN.value == "A"
        assert ShiftType.OFF.value == "OFF"
        assert ShiftType.EDO.value == "EDO"
    
    def test_shift_hours(self):
        """Test hours property for each shift type."""
        assert ShiftType.DAY.hours == 10
        assert ShiftType.EVENING.hours == 10
        assert ShiftType.NIGHT.hours == 12
        assert ShiftType.ADMIN.hours == 8
        assert ShiftType.OFF.hours == 0
        assert ShiftType.EDO.hours == 0
    
    def test_is_work(self):
        """Test is_work property."""
        assert ShiftType.DAY.is_work is True
        assert ShiftType.NIGHT.is_work is True
        assert ShiftType.OFF.is_work is False
        assert ShiftType.EDO.is_work is False
    
    def test_from_string(self):
        """Test parsing shifts from various string formats."""
        # Standard codes
        assert ShiftType.from_string("J") == ShiftType.DAY
        assert ShiftType.from_string("S") == ShiftType.EVENING
        assert ShiftType.from_string("N") == ShiftType.NIGHT
        
        # French names
        assert ShiftType.from_string("jour") == ShiftType.DAY
        assert ShiftType.from_string("soir") == ShiftType.EVENING
        assert ShiftType.from_string("nuit") == ShiftType.NIGHT
        
        # Case insensitive
        assert ShiftType.from_string("JOUR") == ShiftType.DAY
        assert ShiftType.from_string("Nuit") == ShiftType.NIGHT
        
        # English
        assert ShiftType.from_string("day") == ShiftType.DAY
        assert ShiftType.from_string("evening") == ShiftType.EVENING


class TestDayConstants:
    """Tests for day constants and normalization."""
    
    def test_weekdays(self):
        assert WEEKDAYS == ["Lun", "Mar", "Mer", "Jeu", "Ven"]
        assert len(WEEKDAYS) == 5
    
    def test_weekend(self):
        assert WEEKEND == ["Sam", "Dim"]
        assert len(WEEKEND) == 2
    
    def test_all_days(self):
        assert ALL_DAYS == WEEKDAYS + WEEKEND
        assert len(ALL_DAYS) == 7
    
    def test_normalize_day(self):
        """Test day normalization from various formats."""
        # French abbreviations
        assert normalize_day("lun") == "Lun"
        assert normalize_day("mar") == "Mar"
        
        # English
        assert normalize_day("monday") == "Lun"
        assert normalize_day("tuesday") == "Mar"
        
        # Case insensitive
        assert normalize_day("LUN") == "Lun"
        assert normalize_day("MONDAY") == "Lun"


class TestPerson:
    """Tests for Person dataclass."""
    
    def test_person_creation(self):
        """Test creating a person with default values."""
        p = Person(name="Test")
        assert p.name == "Test"
        assert p.workdays_per_week == 5
        assert p.prefers_night is False
        assert p.no_evening is False
        assert p.max_nights == 99
        assert p.edo_eligible is False
    
    def test_person_custom_values(self):
        """Test creating a person with custom values."""
        p = Person(
            name="Alice",
            workdays_per_week=4,
            prefers_night=True,
            no_evening=True,
            max_nights=5,
            edo_eligible=True,
            edo_fixed_day="Mer",
            team="Team A"
        )
        assert p.workdays_per_week == 4
        assert p.prefers_night is True
        assert p.no_evening is True
        assert p.max_nights == 5
        assert p.edo_eligible is True
        assert p.edo_fixed_day == "Mer"
        assert p.team == "Team A"
    
    def test_person_cohort_id(self):
        """Test cohort ID generation."""
        p1 = Person(name="A", workdays_per_week=4)
        assert p1.cohort_id == "4j"
        
        p2 = Person(name="B", workdays_per_week=5, team="Team X")
        assert p2.cohort_id == "Team X"  # Team takes precedence
    
    def test_person_to_dict(self):
        """Test serialization to dict."""
        p = Person(name="Test", workdays_per_week=4)
        d = p.to_dict()
        assert d["name"] == "Test"
        assert d["workdays_per_week"] == 4
    
    def test_person_from_dict(self):
        """Test deserialization from dict."""
        d = {"name": "Alice", "workdays_per_week": 4, "prefers_night": True}
        p = Person.from_dict(d)
        assert p.name == "Alice"
        assert p.workdays_per_week == 4
        assert p.prefers_night is True


class TestSchedule:
    """Tests for Schedule dataclass."""
    
    def test_empty_schedule(self):
        """Test empty schedule."""
        s = Schedule()
        assert len(s.assignments) == 0
        assert s.to_dataframe().empty
    
    def test_schedule_with_assignments(self):
        """Test schedule with assignments."""
        assignments = [
            Assignment("Alice", 1, "Lun", ShiftType.DAY),
            Assignment("Alice", 1, "Mar", ShiftType.EVENING),
            Assignment("Bob", 1, "Lun", ShiftType.NIGHT),
        ]
        s = Schedule(assignments=assignments, weeks=1, people_count=2)
        
        df = s.to_dataframe()
        assert len(df) == 3
        assert set(df["name"]) == {"Alice", "Bob"}
    
    def test_schedule_summary(self):
        """Test schedule summary."""
        s = Schedule(weeks=4, people_count=10, score=5.5, status="optimal")
        summary = s.summary()
        assert summary["weeks"] == 4
        assert summary["people"] == 10
        assert summary["score"] == 5.5
        assert summary["status"] == "optimal"


class TestSolverConfig:
    """Tests for SolverConfig dataclass."""
    
    def test_default_config(self):
        """Test default configuration values."""
        cfg = SolverConfig()
        assert cfg.weeks == 12  # Default changed by RULES
        assert cfg.forbid_night_to_day is True
        assert cfg.max_nights_sequence == 3
        assert cfg.fairness_mode == FairnessMode.BY_WORKDAYS
        assert cfg.weekend_mode == WeekendMode.DISABLED
    
    def test_get_days(self):
        """Test get_days based on weekend mode."""
        cfg1 = SolverConfig(weekend_mode=WeekendMode.DISABLED)
        assert cfg1.get_days() == WEEKDAYS
        
        cfg2 = SolverConfig(weekend_mode=WeekendMode.INTEGRATED)
        assert cfg2.get_days() == ALL_DAYS
    
    def test_config_serialization(self):
        """Test config to_dict and from_dict."""
        cfg = SolverConfig(weeks=8, fairness_mode=FairnessMode.GLOBAL)
        d = cfg.to_dict()
        assert d["weeks"] == 8
        assert d["fairness_mode"] == "global"
        
        cfg2 = SolverConfig.from_dict(d)
        assert cfg2.weeks == 8
        assert cfg2.fairness_mode == FairnessMode.GLOBAL
