# rota/solver - OR-Tools CP-SAT scheduling solver
from .edo import EDOPlan, build_edo_plan
from .engine import solve
from .pairs import PairAssignment, PairSchedule, solve_pairs
from .staffing import JOURS, WeekStaffing, derive_staffing
from .validation import (
    FairnessMetrics,
    ValidationResult,
    calculate_fairness,
    score_solution,
    validate_schedule,
)

__all__ = [
    "solve",
    "solve_pairs",
    "PairSchedule", 
    "PairAssignment",
    "derive_staffing",
    "WeekStaffing",
    "JOURS",
    "build_edo_plan",
    "EDOPlan",
    "validate_schedule",
    "calculate_fairness",
    "score_solution",
    "ValidationResult",
    "FairnessMetrics",
]
