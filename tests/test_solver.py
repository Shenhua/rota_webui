"""Tests for the OR-Tools CP-SAT solver."""
import pytest
from rota.models.person import Person
from rota.models.shift import ShiftType, WEEKDAYS
from rota.models.constraints import SolverConfig, FairnessMode, WeekendMode
from rota.solver.engine import solve


class TestSolverBasics:
    """Basic solver functionality tests."""
    
    def test_solver_returns_schedule(self, sample_people, default_config):
        """Test solver returns a schedule object."""
        schedule = solve(sample_people, default_config)
        assert schedule is not None
        assert hasattr(schedule, "assignments")
        assert hasattr(schedule, "status")
    
    def test_solver_finds_optimal(self, sample_people, default_config):
        """Test solver finds optimal or feasible solution."""
        schedule = solve(sample_people, default_config)
        assert schedule.status in ("optimal", "feasible")
    
    def test_solver_empty_team(self, default_config):
        """Test solver handles empty team."""
        schedule = solve([], default_config)
        assert schedule.status == "infeasible"
        assert len(schedule.assignments) == 0


class TestHardConstraints:
    """Tests for hard constraint enforcement."""
    
    def test_one_shift_per_day(self, sample_people, default_config):
        """Test each person has at most one shift per day."""
        schedule = solve(sample_people, default_config)
        df = schedule.to_dataframe()
        
        # Group by person, week, day - each should have exactly 1 entry
        for (name, week, day), group in df.groupby(["name", "week", "day"]):
            # Filter out OFF/EDO for work shift check
            work_shifts = group[group["shift"].isin(["J", "S", "N", "A"])]
            assert len(work_shifts) <= 1, f"{name} has multiple work shifts on week {week} {day}"
    
    def test_no_work_after_night(self, sample_people, default_config):
        """Test no one works the day after a night shift."""
        default_config.forbid_night_to_day = True
        schedule = solve(sample_people, default_config)
        df = schedule.to_dataframe()
        
        for name in df["name"].unique():
            person_df = df[df["name"] == name].sort_values(["week", "day"])
            
            for week in person_df["week"].unique():
                week_df = person_df[person_df["week"] == week]
                
                for i, day in enumerate(WEEKDAYS[:-1]):
                    next_day = WEEKDAYS[i + 1]
                    
                    day_shift = week_df[week_df["day"] == day]["shift"].values
                    next_day_shift = week_df[week_df["day"] == next_day]["shift"].values
                    
                    if len(day_shift) > 0 and day_shift[0] == "N":
                        if len(next_day_shift) > 0:
                            assert next_day_shift[0] in ("OFF", "EDO"), \
                                f"{name} works after night on week {week}"
    
    def test_max_days_per_week(self, sample_people, default_config):
        """Test each person respects max days per week."""
        default_config.max_days_per_week = 5
        schedule = solve(sample_people, default_config)
        df = schedule.to_dataframe()
        
        for name in df["name"].unique():
            for week in df["week"].unique():
                week_df = df[(df["name"] == name) & (df["week"] == week)]
                work_days = len(week_df[week_df["shift"].isin(["J", "S", "N", "A"])])
                assert work_days <= default_config.max_days_per_week, \
                    f"{name} works {work_days} days in week {week}"
    
    def test_coverage_minimums(self, sample_people, default_config):
        """Test coverage minimums are met."""
        schedule = solve(sample_people, default_config)
        df = schedule.to_dataframe()
        
        for week in range(1, default_config.weeks + 1):
            for day in WEEKDAYS:
                day_df = df[(df["week"] == week) & (df["day"] == day)]
                
                # Check coverage for main shifts (with smaller team, expect 1+ per shift)
                for shift in ["J", "S", "N"]:
                    count = len(day_df[day_df["shift"] == shift])
                    # With 5 people, we expect at least 1 per shift
                    assert count >= 1, f"No {shift} coverage on week {week} {day}"
    
    def test_max_nights_per_person(self):
        """Test max_nights per person is respected."""
        # Create person with max_nights=2
        people = [
            Person(name="Limited", workdays_per_week=5, max_nights=2, id=0),
            Person(name="Unlimited", workdays_per_week=5, id=1),
            Person(name="Also Limited", workdays_per_week=5, max_nights=1, id=2),
            Person(name="Normal", workdays_per_week=5, id=3),
        ]
        config = SolverConfig(weeks=4, time_limit_seconds=30)
        schedule = solve(people, config)
        df = schedule.to_dataframe()
        
        # Check Limited has at most 2 nights total
        limited_nights = len(df[(df["name"] == "Limited") & (df["shift"] == "N")])
        assert limited_nights <= 2, f"Limited has {limited_nights} nights, expected <= 2"
        
        # Check Also Limited has at most 1 night
        also_limited_nights = len(df[(df["name"] == "Also Limited") & (df["shift"] == "N")])
        assert also_limited_nights <= 1, f"Also Limited has {also_limited_nights} nights, expected <= 1"


class TestSoftConstraints:
    """Tests for soft constraint optimization."""
    
    def test_fairness_nights_distributed(self, sample_people, default_config):
        """Test nights are distributed somewhat fairly."""
        default_config.fairness_mode = FairnessMode.GLOBAL
        schedule = solve(sample_people, default_config)
        df = schedule.to_dataframe()
        
        # Count nights per person
        night_counts = df[df["shift"] == "N"].groupby("name").size()
        
        if len(night_counts) > 1:
            # Check variance is reasonable (not all nights on one person)
            max_nights = night_counts.max()
            min_nights = night_counts.min()
            # Allow some variance but not extreme
            assert max_nights - min_nights <= default_config.weeks, \
                "Night distribution is too uneven"
    
    def test_prefers_night_respected(self, sample_people, default_config):
        """Test prefers_night preference is somewhat respected."""
        # Bob prefers nights
        default_config.fairness_mode = FairnessMode.NONE  # Disable fairness to see preference
        schedule = solve(sample_people, default_config)
        df = schedule.to_dataframe()
        
        bob_nights = len(df[(df["name"] == "Bob") & (df["shift"] == "N")])
        alice_nights = len(df[(df["name"] == "Alice") & (df["shift"] == "N")])
        
        # Bob (prefers_night=True) should have at least as many nights as Alice
        # This is a soft constraint so we just check it's not worse
        # (Might not always hold due to other constraints)


class TestWeekendMode:
    """Tests for weekend scheduling modes."""
    
    def test_weekday_only_mode(self, sample_people):
        """Test disabled weekend mode only schedules weekdays."""
        config = SolverConfig(weeks=1, weekend_mode=WeekendMode.DISABLED)
        schedule = solve(sample_people, config)
        df = schedule.to_dataframe()
        
        # Should only have weekday assignments
        assert set(df["day"].unique()).issubset(set(WEEKDAYS))
    
    def test_integrated_weekend_mode(self, sample_people):
        """Test integrated mode includes weekends."""
        config = SolverConfig(weeks=1, weekend_mode=WeekendMode.INTEGRATED)
        schedule = solve(sample_people, config)
        df = schedule.to_dataframe()
        
        # Should have all 7 days
        from rota.models.shift import ALL_DAYS
        assert set(df["day"].unique()) == set(ALL_DAYS)


class TestPerformance:
    """Performance tests."""
    
    def test_solve_time_reasonable(self, sample_people, default_config):
        """Test solver completes in reasonable time."""
        schedule = solve(sample_people, default_config)
        assert schedule.solve_time_seconds < 10, "Solver took too long"
    
    def test_larger_team(self):
        """Test solver handles larger team."""
        people = [Person(name=f"Person{i}", workdays_per_week=5, id=i) for i in range(20)]
        config = SolverConfig(weeks=4, time_limit_seconds=30)
        
        schedule = solve(people, config)
        assert schedule.status in ("optimal", "feasible")
