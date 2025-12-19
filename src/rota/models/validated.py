"""
Pydantic Validated Models
=========================
Optional Pydantic validation layer for configuration objects.
Falls back gracefully if Pydantic is not installed.

Usage:
    from rota.models.validated import ValidatedSolverConfig
    
    config = ValidatedSolverConfig(weeks=4, time_limit_seconds=60)
    
Note: Original dataclass models remain unchanged for backward compatibility.
"""
from typing import List, Optional

# Try Pydantic import with graceful fallback
try:
    from pydantic import BaseModel, Field, field_validator, model_validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseModel = object
    
    # Create dummy decorators if Pydantic not available
    def Field(*args, **kwargs):
        return None
    def field_validator(*args, **kwargs):
        def decorator(func):
            return func
        return decorator
    def model_validator(*args, **kwargs):
        def decorator(func):
            return func
        return decorator


if PYDANTIC_AVAILABLE:
    from enum import Enum
    
    class FairnessModeEnum(str, Enum):
        """Fairness distribution modes."""
        NONE = "none"
        BY_WORKDAYS = "by-wd"
        BY_TEAM = "by-team"
        GLOBAL = "global"
    
    class WeekendModeEnum(str, Enum):
        """Weekend scheduling modes."""
        DISABLED = "disabled"
        INTEGRATED = "integrated"
        SEPARATE = "separate"
    
    class ValidatedSolverConfig(BaseModel):
        """
        Pydantic-validated solver configuration.
        
        Use this for strict validation at API boundaries.
        Can be converted to/from the dataclass SolverConfig.
        """
        # Horizon
        weeks: int = Field(default=4, ge=1, le=52, description="Number of weeks to schedule")
        
        # Solver behavior
        time_limit_seconds: int = Field(default=60, ge=5, le=600, description="Max solve time")
        num_workers: int = Field(default=4, ge=1, le=32)
        parallel_portfolio: bool = Field(default=False)
        workers_per_solve: int = Field(default=0, ge=0)
        
        # Weekend
        include_weekends: bool = Field(default=False)
        weekend_mode: WeekendModeEnum = Field(default=WeekendModeEnum.DISABLED)
        
        # Hard constraints
        forbid_night_to_day: bool = Field(default=True, description="No work after night shift")
        max_consecutive_days: int = Field(default=6, ge=1, le=7)
        min_rest_after_night: int = Field(default=1, ge=0, le=3)
        max_nights_sequence: int = Field(default=3, ge=1, le=7)
        max_evenings_sequence: int = Field(default=3, ge=1, le=7)
        max_days_per_week: int = Field(default=5, ge=1, le=7)
        forbid_contractor_pairs: bool = Field(default=True)
        
        # EDO
        edo_enabled: bool = Field(default=True)
        
        # Fairness
        fairness_mode: FairnessModeEnum = Field(default=FairnessModeEnum.BY_WORKDAYS)
        night_fairness_weight: float = Field(default=10.0, ge=0, le=100)
        evening_fairness_weight: float = Field(default=3.0, ge=0, le=100)
        
        # Soft constraint weights
        preference_weight: float = Field(default=1.0, ge=0, le=10)
        
        # Legacy
        impose_targets: bool = Field(default=True)
        alpha: float = Field(default=1.0, ge=0, le=10)
        
        @field_validator("weeks")
        @classmethod
        def validate_weeks(cls, v: int) -> int:
            """Ensure weeks is reasonable."""
            if v < 1:
                raise ValueError("weeks must be at least 1")
            if v > 52:
                raise ValueError("weeks cannot exceed 52")
            return v
        
        @model_validator(mode="after")
        def validate_model(self):
            """Cross-field validation."""
            if self.max_nights_sequence > self.max_consecutive_days:
                raise ValueError("max_nights_sequence cannot exceed max_consecutive_days")
            return self
        
        def to_dataclass(self):
            """Convert to dataclass SolverConfig for solver compatibility."""
            from rota.models.constraints import SolverConfig, FairnessMode, WeekendMode
            
            return SolverConfig(
                weeks=self.weeks,
                time_limit_seconds=self.time_limit_seconds,
                num_workers=self.num_workers,
                parallel_portfolio=self.parallel_portfolio,
                workers_per_solve=self.workers_per_solve,
                include_weekends=self.include_weekends,
                weekend_mode=WeekendMode(self.weekend_mode.value),
                forbid_night_to_day=self.forbid_night_to_day,
                max_consecutive_days=self.max_consecutive_days,
                min_rest_after_night=self.min_rest_after_night,
                max_nights_sequence=self.max_nights_sequence,
                max_evenings_sequence=self.max_evenings_sequence,
                max_days_per_week=self.max_days_per_week,
                forbid_contractor_pairs=self.forbid_contractor_pairs,
                edo_enabled=self.edo_enabled,
                fairness_mode=FairnessMode(self.fairness_mode.value),
                night_fairness_weight=self.night_fairness_weight,
                evening_fairness_weight=self.evening_fairness_weight,
                preference_weight=self.preference_weight,
                impose_targets=self.impose_targets,
                alpha=self.alpha,
            )
        
        @classmethod
        def from_dataclass(cls, config) -> "ValidatedSolverConfig":
            """Create from dataclass SolverConfig."""
            return cls(
                weeks=config.weeks,
                time_limit_seconds=config.time_limit_seconds,
                num_workers=config.num_workers,
                parallel_portfolio=config.parallel_portfolio,
                workers_per_solve=config.workers_per_solve,
                include_weekends=config.include_weekends,
                weekend_mode=WeekendModeEnum(config.weekend_mode.value),
                forbid_night_to_day=config.forbid_night_to_day,
                max_consecutive_days=config.max_consecutive_days,
                min_rest_after_night=config.min_rest_after_night,
                max_nights_sequence=config.max_nights_sequence,
                max_evenings_sequence=config.max_evenings_sequence,
                max_days_per_week=config.max_days_per_week,
                forbid_contractor_pairs=config.forbid_contractor_pairs,
                edo_enabled=config.edo_enabled,
                fairness_mode=FairnessModeEnum(config.fairness_mode.value),
                night_fairness_weight=config.night_fairness_weight,
                evening_fairness_weight=config.evening_fairness_weight,
                preference_weight=config.preference_weight,
                impose_targets=config.impose_targets,
                alpha=config.alpha,
            )
        
        class Config:
            """Pydantic model config."""
            use_enum_values = True
            validate_assignment = True

else:
    # Fallback when Pydantic not installed
    class ValidatedSolverConfig:
        """Fallback class when Pydantic not installed."""
        def __init__(self, **kwargs):
            raise ImportError(
                "Pydantic is required for ValidatedSolverConfig. "
                "Install with: pip install pydantic>=2.0"
            )
