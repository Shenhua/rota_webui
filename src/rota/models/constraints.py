"""Solver configuration and constraint definitions."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class FairnessMode(str, Enum):
    """Fairness distribution modes."""
    NONE = "none"
    BY_WORKDAYS = "by-wd"  # Cohorts by workdays_per_week
    BY_TEAM = "by-team"  # Cohorts by team field
    GLOBAL = "global"  # All people in one cohort


class WeekendMode(str, Enum):
    """Weekend scheduling modes."""
    DISABLED = "disabled"  # No weekend scheduling (Mon-Fri only)
    INTEGRATED = "integrated"  # Weekend follows same rules as weekdays
    SEPARATE = "separate"  # Weekend has its own coverage targets


@dataclass
class CoverageTarget:
    """Coverage requirement for a specific day and shift."""
    day: str
    shift: str  # J, S, N, A
    required: int = 0
    weight: float = 1.0  # For soft constraint optimization


@dataclass
class SolverConfig:
    """Configuration for the scheduling solver."""
    
    # Horizon
    weeks: int = 4
    
    # Solver behavior
    time_limit_seconds: int = 60
    num_workers: int = 4
    parallel_portfolio: bool = False  # If True, enables parallel seeds in optimizer
    workers_per_solve: int = 0 # If > 0, overrides internal CP-SAT worker count. 0 = Auto.
    
    # Days to schedule
    include_weekends: bool = False
    weekend_mode: WeekendMode = WeekendMode.DISABLED
    
    # Coverage targets (weekday)
    weekday_targets: List[CoverageTarget] = field(default_factory=list)
    # Coverage targets (weekend) - only used if weekend_mode != DISABLED
    weekend_targets: List[CoverageTarget] = field(default_factory=list)
    
    # Hard constraints
    forbid_night_to_day: bool = True  # No work day after night
    max_consecutive_days: int = 6  # Max consecutive working days (global)
    min_rest_after_night: int = 1  # Days of rest after night
    max_nights_sequence: int = 3  # Max consecutive nights
    max_evenings_sequence: int = 3  # Max consecutive evenings
    max_days_per_week: int = 5  # Max work days per week
    
    # EDO policy
    edo_enabled: bool = True
    
    # Fairness
    fairness_mode: FairnessMode = FairnessMode.BY_WORKDAYS
    night_fairness_weight: float = 10.0  # Weight for night distribution in objective
    evening_fairness_weight: float = 3.0  # Weight for evening distribution
    
    # Soft constraint weights
    preference_weight: float = 1.0  # Weight for honoring preferences
    
    # Legacy compatibility
    impose_targets: bool = True  # If True, treat targets as hard caps (no overtime)
    alpha: float = 1.0  # Composite scoring weight

    def get_days(self) -> List[str]:
        """Get list of days to schedule based on weekend mode."""
        from .shift import ALL_DAYS, WEEKDAYS
        if self.weekend_mode == WeekendMode.DISABLED:
            return WEEKDAYS
        return ALL_DAYS

    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "weeks": self.weeks,
            "time_limit_seconds": self.time_limit_seconds,
            "include_weekends": self.include_weekends,
            "weekend_mode": self.weekend_mode.value,
            "forbid_night_to_day": self.forbid_night_to_day,
            "min_rest_after_night": self.min_rest_after_night,
            "max_nights_sequence": self.max_nights_sequence,
            "max_evenings_sequence": self.max_evenings_sequence,
            "max_days_per_week": self.max_days_per_week,
            "edo_enabled": self.edo_enabled,
            "fairness_mode": self.fairness_mode.value,
            "night_fairness_weight": self.night_fairness_weight,
            "evening_fairness_weight": self.evening_fairness_weight,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "SolverConfig":
        """Create from dictionary."""
        cfg = cls()
        for key, value in d.items():
            if hasattr(cfg, key):
                if key == "fairness_mode":
                    value = FairnessMode(value) if value else FairnessMode.NONE
                elif key == "weekend_mode":
                    value = WeekendMode(value) if value else WeekendMode.DISABLED
                setattr(cfg, key, value)
        return cfg
