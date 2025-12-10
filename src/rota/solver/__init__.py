# rota/solver - OR-Tools CP-SAT scheduling solver
from .engine import solve
from .pairs import solve_pairs, PairSchedule, PairAssignment
from .staffing import derive_staffing, WeekStaffing, JOURS
from .edo import build_edo_plan, EDOPlan
from .validation import validate_schedule, calculate_fairness, score_solution, ValidationResult, FairnessMetrics

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
