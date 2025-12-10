"""Configuration for the scheduling solver - re-export from models."""
# Backwards compatibility: re-export from new location
from rota.models.constraints import CoverageTarget, FairnessMode, SolverConfig, WeekendMode

# Legacy alias
SolveConfig = SolverConfig

__all__ = ["SolveConfig", "SolverConfig", "FairnessMode", "WeekendMode", "CoverageTarget"]
