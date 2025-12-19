"""
Objective Builders for CP-SAT Solver
====================================
Extracted soft constraint / objective logic from solve_pairs().
"""
from typing import Dict, List, Tuple

from ortools.sat.python import cp_model

from rota.models.constraints import FairnessMode, SolverConfig
from rota.models.person import Person
from rota.models.rules import SHIFTS
from rota.solver.edo import EDOPlan
from rota.solver.staffing import WeekStaffing
from rota.utils.logging_setup import SolverLogger

slog = SolverLogger("rota.solver.objectives")


# Type aliases
AssignVars = Dict[str, Dict[int, Dict[str, Dict[str, cp_model.IntVar]]]]
ObjectiveTerms = List[Tuple[cp_model.IntVar, int]]


def build_cohorts(
    names: List[str],
    name_to_person: Dict[str, Person],
    config: SolverConfig,
) -> Dict[str, List[str]]:
    """Build cohort groupings based on fairness mode."""
    cohorts = {}
    
    if config.fairness_mode == FairnessMode.BY_TEAM:
        for p in names:
            team = name_to_person[p].team or "no_team"
            cohorts.setdefault(team, []).append(p)
    elif config.fairness_mode == FairnessMode.GLOBAL:
        cohorts["all"] = names.copy()
    else:  # BY_WORKDAYS (default)
        for p in names:
            wd = name_to_person[p].workdays_per_week
            key = f"{wd}j"
            cohorts.setdefault(key, []).append(p)
    
    slog.step(f"Cohorts ({config.fairness_mode.value}): {[(k, len(v)) for k, v in cohorts.items()]}")
    return cohorts


def add_unfilled_penalty(
    model: cp_model.CpModel,
    unfilled_vars: List[Tuple[cp_model.IntVar, str, int, str]],
    objective_terms: ObjectiveTerms,
) -> None:
    """Add penalty for unfilled slots."""
    slog.step(f"Soft: Penalizing {len(unfilled_vars)} potential unfilled slots")
    total_unfilled = model.NewIntVar(0, len(unfilled_vars) * 10, "total_unfilled")
    model.Add(total_unfilled == sum(uv[0] for uv in unfilled_vars))
    objective_terms.append((total_unfilled, 10000))


def add_night_fairness_objective(
    model: cp_model.CpModel,
    night_counts: Dict[str, cp_model.IntVar],
    names: List[str],
    name_to_person: Dict[str, Person],
    people: List[Person],
    weeks: int,
    days: List[str],
    cohorts: Dict[str, List[str]],
    objective_terms: ObjectiveTerms,
) -> None:
    """Add night fairness objective (proportional distribution)."""
    slog.step("Soft: Night fairness (proportional)")
    
    total_workdays_capacity = sum(p.workdays_per_week for p in people)
    total_night_person_shifts = weeks * len(days) * 2
    
    for p in names:
        person = name_to_person[p]
        night_target = int(round((person.workdays_per_week / total_workdays_capacity) * total_night_person_shifts))
        
        deviation = model.NewIntVar(0, weeks * len(days), f"night_dev_{p}")
        model.Add(deviation >= night_counts[p] - night_target)
        model.Add(deviation >= night_target - night_counts[p])
        objective_terms.append((deviation, 100))
    
    # Minimize spread within cohorts
    for cid, members in cohorts.items():
        if len(members) > 1:
            cohort_night_vars = [night_counts[m] for m in members]
            max_n = model.NewIntVar(0, weeks * len(days), f"max_nights_{cid}")
            min_n = model.NewIntVar(0, weeks * len(days), f"min_nights_{cid}")
            model.AddMaxEquality(max_n, cohort_night_vars)
            model.AddMinEquality(min_n, cohort_night_vars)
            spread = model.NewIntVar(0, weeks * len(days), f"night_spread_{cid}")
            model.Add(spread == max_n - min_n)
            objective_terms.append((spread, 500))


def add_soir_fairness_objective(
    model: cp_model.CpModel,
    assign: AssignVars,
    names: List[str],
    name_to_person: Dict[str, Person],
    people: List[Person],
    weeks: int,
    days: List[str],
    staffing: Dict[int, WeekStaffing],
    cohorts: Dict[str, List[str]],
    objective_terms: ObjectiveTerms,
) -> Dict[str, cp_model.IntVar]:
    """
    Add Soir fairness objective.
    
    Returns:
        Dict mapping person name to their soir count variable
    """
    slog.step("Soft: Soir fairness (proportional)")
    
    total_workdays_capacity = sum(p.workdays_per_week for p in people)
    total_soir_slots = sum(staffing[w].slots[d].get("S", 0) for w in range(1, weeks + 1) for d in days)
    
    soir_counts = {}
    for p in names:
        person = name_to_person[p]
        soir_assignments = [assign[p][w][d]["S"] for w in range(1, weeks + 1) for d in days]
        soir_counts[p] = model.NewIntVar(0, weeks * len(days), f"soirs_{p}")
        model.Add(soir_counts[p] == sum(soir_assignments))
        
        soir_target = int(round((person.workdays_per_week / total_workdays_capacity) * total_soir_slots))
        deviation = model.NewIntVar(0, weeks * len(days), f"soir_dev_{p}")
        model.Add(deviation >= soir_counts[p] - soir_target)
        model.Add(deviation >= soir_target - soir_counts[p])
        objective_terms.append((deviation, 50))
    
    # Minimize spread within cohorts
    for cid, members in cohorts.items():
        if len(members) > 1:
            cohort_soir_vars = [soir_counts[m] for m in members]
            max_s = model.NewIntVar(0, weeks * len(days), f"max_soirs_{cid}")
            min_s = model.NewIntVar(0, weeks * len(days), f"min_soirs_{cid}")
            model.AddMaxEquality(max_s, cohort_soir_vars)
            model.AddMinEquality(min_s, cohort_soir_vars)
            spread = model.NewIntVar(0, weeks * len(days), f"soir_spread_{cid}")
            model.Add(spread == max_s - min_s)
            objective_terms.append((spread, 300))
    
    return soir_counts


def add_workday_target_objective(
    model: cp_model.CpModel,
    assign: AssignVars,
    names: List[str],
    name_to_person: Dict[str, Person],
    weeks: int,
    days: List[str],
    edo_plan: EDOPlan,
    objective_terms: ObjectiveTerms,
) -> None:
    """Add workday target deviation objective with hard cap."""
    slog.step("Soft: Workday target deviation")
    
    total_deviation = model.NewIntVar(0, len(names) * weeks * len(days), "total_deviation")
    deviation_terms = []
    
    for p in names:
        person = name_to_person[p]
        edo_weeks = sum(1 for w in range(1, weeks + 1) if p in edo_plan.plan.get(w, set()))
        target = person.workdays_per_week * weeks - edo_weeks
        
        person_total = model.NewIntVar(0, weeks * len(days), f"total_{p}")
        all_shifts = [assign[p][w][d][s] for w in range(1, weeks + 1) for d in days for s in ["D", "N", "S"]]
        model.Add(person_total == sum(all_shifts))
        
        # HARD constraint: Never exceed target
        model.Add(person_total <= target)
        
        # Soft: minimize undershoot
        undershoot = model.NewIntVar(0, weeks * len(days), f"undershoot_{p}")
        model.Add(undershoot >= target - person_total)
        deviation_terms.append(undershoot)
    
    model.Add(total_deviation == sum(deviation_terms))
    objective_terms.append((total_deviation, 5))


def add_clopening_penalty(
    model: cp_model.CpModel,
    assign: AssignVars,
    names: List[str],
    weeks: int,
    days: List[str],
    objective_terms: ObjectiveTerms,
) -> None:
    """Add penalty for Soir→Jour (clopening) patterns."""
    slog.step("Soft: Soir→Jour penalty")
    
    clopening_count = model.NewIntVar(0, len(names) * weeks * len(days), "clopenings")
    clopening_terms = []
    
    for p in names:
        for w in range(1, weeks + 1):
            for d_idx in range(len(days) - 1):
                d = days[d_idx]
                d_next = days[d_idx + 1]
                
                clopening = model.NewBoolVar(f"clop_{p}_{w}_{d}")
                model.AddBoolAnd([assign[p][w][d]["S"], assign[p][w][d_next]["D"]]).OnlyEnforceIf(clopening)
                model.AddBoolOr([assign[p][w][d]["S"].Not(), assign[p][w][d_next]["D"].Not()]).OnlyEnforceIf(clopening.Not())
                clopening_terms.append(clopening)
    
    if clopening_terms:
        model.Add(clopening_count == sum(clopening_terms))
        objective_terms.append((clopening_count, 1))
