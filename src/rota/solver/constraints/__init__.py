"""
Constraint Builders for CP-SAT Solver
=====================================
Extracted constraint logic from the monolithic solve_pairs() function.
Each constraint builder takes the model, variables, and config, and adds constraints.
"""
from typing import Dict, List, Tuple

from ortools.sat.python import cp_model

from rota.models.constraints import FairnessMode, SolverConfig
from rota.models.person import Person
from rota.models.rules import SHIFTS
from rota.solver.edo import EDOPlan
from rota.solver.staffing import WeekStaffing
from rota.utils.logging_setup import SolverLogger

slog = SolverLogger("rota.solver.constraints")


# Type aliases for clarity
AssignVars = Dict[str, Dict[int, Dict[str, Dict[str, cp_model.IntVar]]]]
WorksVars = Dict[str, Dict[int, Dict[str, cp_model.IntVar]]]


def add_staffing_constraints(
    model: cp_model.CpModel,
    assign: AssignVars,
    names: List[str],
    weeks: int,
    days: List[str],
    staffing: Dict[int, WeekStaffing],
) -> List[Tuple[cp_model.IntVar, str, int, str]]:
    """
    Add soft staffing constraints (allow unfilled slots).
    
    Returns:
        List of (unfilled_var, shift, week, day) tuples for objective
    """
    slog.step("Constraint: Staffing requirements (Soft - allow gaps)")
    unfilled_vars = []
    
    for w in range(1, weeks + 1):
        for d in days:
            # Day shift (D): pairs need 2 people each
            d_slots = staffing[w].slots[d]["D"]
            d_people_needed = d_slots * 2
            d_assigned = sum(assign[p][w][d]["D"] for p in names)
            d_unfilled = model.NewIntVar(0, d_people_needed, f"unfilled_D_{w}_{d}")
            model.Add(d_assigned + d_unfilled == d_people_needed)
            unfilled_vars.append((d_unfilled, "D", w, d))
            
            # Night shift (N): pairs need 2 people each
            n_slots = staffing[w].slots[d]["N"]
            n_people_needed = n_slots * 2
            n_assigned = sum(assign[p][w][d]["N"] for p in names)
            n_unfilled = model.NewIntVar(0, n_people_needed, f"unfilled_N_{w}_{d}")
            model.Add(n_assigned + n_unfilled == n_people_needed)
            unfilled_vars.append((n_unfilled, "N", w, d))
            
            # Soir shift (S): solo
            s_slots = staffing[w].slots[d].get("S", 0)
            if s_slots > 0:
                s_assigned = sum(assign[p][w][d]["S"] for p in names)
                s_unfilled = model.NewIntVar(0, s_slots, f"unfilled_S_{w}_{d}")
                model.Add(s_assigned + s_unfilled == s_slots)
                unfilled_vars.append((s_unfilled, "S", w, d))
    
    return unfilled_vars


def add_one_shift_per_day(
    model: cp_model.CpModel,
    assign: AssignVars,
    names: List[str],
    weeks: int,
    days: List[str],
) -> None:
    """Add constraint: at most one shift per person per day."""
    slog.step("Constraint: One shift per person per day")
    for p in names:
        for w in range(1, weeks + 1):
            for d in days:
                model.Add(sum(assign[p][w][d][s] for s in ["D", "N", "S"]) <= 1)


def add_night_rest_constraint(
    model: cp_model.CpModel,
    assign: AssignVars,
    person_works: WorksVars,
    names: List[str],
    weeks: int,
    days: List[str],
    config: SolverConfig,
) -> None:
    """Add constraint: no work day after night shift."""
    if not config.forbid_night_to_day:
        return
        
    slog.step("Constraint: No work after night")
    for p in names:
        for w in range(1, weeks + 1):
            for i, d in enumerate(days[:-1]):
                next_d = days[i + 1]
                model.Add(person_works[p][w][next_d] == 0).OnlyEnforceIf(assign[p][w][d]["N"])


def add_max_nights_constraint(
    model: cp_model.CpModel,
    assign: AssignVars,
    names: List[str],
    name_to_person: Dict[str, Person],
    weeks: int,
    days: List[str],
) -> Dict[str, cp_model.IntVar]:
    """
    Add constraint: max nights per person over horizon.
    
    Returns:
        Dict mapping person name to their night count variable
    """
    slog.step("Constraint: Max nights per person")
    night_counts = {}
    
    for p in names:
        person = name_to_person[p]
        night_assignments = [assign[p][w][d]["N"] for w in range(1, weeks + 1) for d in days]
        night_counts[p] = model.NewIntVar(0, weeks * len(days), f"nights_{p}")
        model.Add(night_counts[p] == sum(night_assignments))
        
        if person.max_nights < weeks * len(days):
            model.Add(night_counts[p] <= person.max_nights)
    
    return night_counts


def add_consecutive_nights_constraint(
    model: cp_model.CpModel,
    assign: AssignVars,
    names: List[str],
    weeks: int,
    days: List[str],
    config: SolverConfig,
) -> None:
    """Add constraint: max consecutive nights in a sequence."""
    if config.max_nights_sequence >= len(days):
        return
        
    slog.step(f"Constraint: Max {config.max_nights_sequence} consecutive nights")
    
    all_days_ordered = [(w, d) for w in range(1, weeks + 1) for d in days]
    
    for p in names:
        window_size = config.max_nights_sequence + 1
        for start_idx in range(len(all_days_ordered) - window_size + 1):
            window_days = all_days_ordered[start_idx:start_idx + window_size]
            window_nights = [assign[p][w][d]["N"] for (w, d) in window_days]
            model.Add(sum(window_nights) <= config.max_nights_sequence)


def add_edo_constraints(
    model: cp_model.CpModel,
    person_works: WorksVars,
    names: List[str],
    weeks: int,
    days: List[str],
    edo_plan: EDOPlan,
) -> None:
    """
    Add EDO (Earned Day Off) constraints.
    
    - Fixed EDO day: force that day off
    - No fixed day: solver picks at least one day off
    """
    slog.step("Constraint: EDO days")
    for p in names:
        for w in range(1, weeks + 1):
            if p in edo_plan.plan.get(w, set()):
                fixed = edo_plan.fixed.get(p, "")
                if fixed and fixed in days:
                    model.Add(person_works[p][w][fixed] == 0)
                else:
                    off_days = [person_works[p][w][d].Not() for d in days]
                    model.Add(sum(off_days) >= 1)


def add_weekly_hours_constraint(
    model: cp_model.CpModel,
    assign: AssignVars,
    names: List[str],
    weeks: int,
    days: List[str],
) -> None:
    """Add constraint: max 48 hours per week (Mon-Fri)."""
    slog.step("Constraint: 48h per week")
    for p in names:
        for w in range(1, weeks + 1):
            week_hours = []
            for d in days:
                for s in ["D", "N", "S"]:
                    week_hours.append(assign[p][w][d][s] * SHIFTS[s].hours)
            model.Add(sum(week_hours) <= 48)


def add_rolling_48h_constraint(
    model: cp_model.CpModel,
    assign: AssignVars,
    names: List[str],
    weeks: int,
    days: List[str],
) -> None:
    """
    Add 48h rolling window constraint (across weeks, weekend = 0h).
    
    Uses flat timeline approach aligned with validation.py:check_rolling_48h().
    """
    slog.step("Constraint: 48h rolling window (Hard)")
    
    for p in names:
        timeline_hours = []
        
        for w in range(1, weeks + 1):
            for d in days:
                hour_expr = sum(
                    assign[p][w][d][s] * SHIFTS[s].hours
                    for s in ["D", "N", "S"]
                )
                timeline_hours.append(hour_expr)
            
            timeline_hours.append(0)  # Saturday
            timeline_hours.append(0)  # Sunday
        
        for i in range(len(timeline_hours) - 6):
            window = timeline_hours[i : i + 7]
            model.Add(sum(window) <= 48)


def add_consecutive_days_constraint(
    model: cp_model.CpModel,
    assign: AssignVars,
    names: List[str],
    weeks: int,
    days: List[str],
    config: SolverConfig,
) -> None:
    """Add constraint: max consecutive work days."""
    max_days = getattr(config, "max_consecutive_days", 6)
    if not max_days or max_days >= 7 * 4:
        return
        
    slog.step(f"Hard: Max {max_days} consecutive workdays")
    for p in names:
        timeline_vars = []
        for w in range(1, weeks + 1):
            for d in days:
                working = model.NewBoolVar(f"working_{p}_{w}_{d}")
                model.Add(sum(assign[p][w][d][s] for s in ["D", "N", "S"]) == working)
                timeline_vars.append(working)
            
            if w < weeks:
                timeline_vars.append(0)  # Saturday
                timeline_vars.append(0)  # Sunday
        
        window_size = max_days + 1
        for i in range(len(timeline_vars) - window_size + 1):
            window = timeline_vars[i : i + window_size]
            model.Add(sum(window) <= max_days)


def add_no_evening_preference(
    model: cp_model.CpModel,
    assign: AssignVars,
    names: List[str],
    name_to_person: Dict[str, Person],
    weeks: int,
    days: List[str],
) -> None:
    """Add constraint: no Soir shifts for people with no_evening=True."""
    slog.step("Constraint: No Soir preferences")
    for p in names:
        person = name_to_person[p]
        if person.no_evening:
            for w in range(1, weeks + 1):
                for d in days:
                    model.Add(assign[p][w][d]["S"] == 0)


def add_contractor_pair_constraint(
    model: cp_model.CpModel,
    assign: AssignVars,
    people: List[Person],
    weeks: int,
    days: List[str],
    config: SolverConfig,
) -> None:
    """Add constraint: contractors must be paired with regular staff."""
    if not config.forbid_contractor_pairs:
        return
        
    contractors = [p.name for p in people if p.is_contractor]
    if len(contractors) < 2:
        return
        
    slog.step(f"Constraint: No contractor pairs ({len(contractors)} contractors)")
    for w in range(1, weeks + 1):
        for d in days:
            for s in ["D", "N"]:  # Only pair shifts
                contractor_count = sum(assign[p][w][d][s] for p in contractors)
                model.Add(contractor_count <= 1)
