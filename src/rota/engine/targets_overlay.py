"""Bridge module to connect the new solver to the legacy UI API."""
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

from rota.io.csv_loader import load_team
from rota.models.constraints import FairnessMode, SolverConfig
from rota.models.person import Person
from rota.solver.edo import build_edo_plan

# Use new solver components
from rota.solver.optimizer import optimize
from rota.solver.staffing import derive_staffing
from rota.solver.validation import calculate_fairness, validate_schedule


@dataclass
class SolveResult:
    """Legacy-compatible result format for UI."""
    assignments: pd.DataFrame
    summary: Dict[str, Any]
    metrics_json: Dict[str, Any]


def solve(csv_path: str, cfg: Optional[Any] = None) -> SolveResult:
    """
    Solve scheduling problem - compatible with legacy UI expectations.
    
    Args:
        csv_path: Path to team CSV, or can be a DataFrame
        cfg: Configuration object (legacy SolveConfig or new SolverConfig)
        
    Returns:
        SolveResult with assignments DataFrame and metadata
    """
    # Load team
    if isinstance(csv_path, pd.DataFrame):
        people = [Person.from_dict(row.to_dict()) for _, row in csv_path.iterrows()]
    else:
        people = load_team(csv_path)
    
    # Build solver config from legacy config if provided
    solver_cfg = SolverConfig()
    tries = 1
    
    if cfg is not None:
        # Extract values from legacy config
        if hasattr(cfg, "weeks"):
            solver_cfg.weeks = int(cfg.weeks)
        if hasattr(cfg, "tries"):
            # Now we RESPECT tries!
            tries = int(cfg.tries)
        if hasattr(cfg, "time_limit_seconds"):
            solver_cfg.time_limit_seconds = int(cfg.time_limit_seconds)
        if hasattr(cfg, "forbid_night_to_day"):
            solver_cfg.forbid_night_to_day = bool(cfg.forbid_night_to_day)
        if hasattr(cfg, "max_nights_seq") or hasattr(cfg, "max_nights_sequence"):
            solver_cfg.max_nights_sequence = int(
                getattr(cfg, "max_nights_sequence", getattr(cfg, "max_nights_seq", 3))
            )
        if hasattr(cfg, "max_evenings_seq") or hasattr(cfg, "max_evenings_sequence"):
            solver_cfg.max_evenings_sequence = int(
                getattr(cfg, "max_evenings_sequence", getattr(cfg, "max_evenings_seq", 3))
            )
        if hasattr(cfg, "max_days_per_week"):
            solver_cfg.max_days_per_week = int(cfg.max_days_per_week)
        if hasattr(cfg, "allow_edo") or hasattr(cfg, "edo_enabled"):
            solver_cfg.edo_enabled = bool(
                getattr(cfg, "edo_enabled", getattr(cfg, "allow_edo", True))
            )
        
        # Fairness mode mapping
        if hasattr(cfg, "fairness_mode"):
            fm = cfg.fairness_mode
            if fm in ("none", "None"):
                solver_cfg.fairness_mode = FairnessMode.NONE
            elif fm in ("by-wd", "cohorts_days_per_week", "by_workdays"):
                solver_cfg.fairness_mode = FairnessMode.BY_WORKDAYS
            elif fm in ("global", "fair_nights"):
                solver_cfg.fairness_mode = FairnessMode.GLOBAL
            elif fm in ("by-team",):
                solver_cfg.fairness_mode = FairnessMode.BY_TEAM
    
    # Run solver (Pair-based optimizer)
    # Note: custom_staffing defaults to None
    schedule, best_seed, best_score = optimize(
        people, 
        solver_cfg, 
        tries=tries,
        seed=0,  # Auto-seed usually handled by caller or inside optimize (if 0/None)
        cohort_mode=solver_cfg.fairness_mode.value
    )
    
    # Re-calculate validation metrics for result
    edo_plan = build_edo_plan(people, solver_cfg.weeks)
    staffing = derive_staffing(people, solver_cfg.weeks, edo_plan.plan)
    
    if schedule.status in ["optimal", "feasible"]:
        validation = validate_schedule(schedule, people, edo_plan, staffing)
        fairness = calculate_fairness(schedule, people, solver_cfg.fairness_mode.value)
        
        # Build metrics dict
        # violations_dict not needed for legacy counts format
        # Actually validation.violations is list of Violation objects.
        # But legacy likely expected raw dicts or objects? 
        # engine.py returned 'schedule.violations' which was Dict[str, int] of counts? 
        # Let's check engine.py outline again or older snippet.
        # Snippet 133 says violations: Dict[str, int].
        # But validation_result in validation.py has .violations as List[Violation].
        # We need to adapt it. Legacy summary expects "vacancies" count.
        
        vacancies = validation.slots_vides
        
        # Reconstruct counters for legacy metrics_json
        # Summary dict (counts)
        violations_counts = {
            "vacancies": vacancies,
            "rolling_48h": validation.rolling_48h_violations,
            "night_to_day": validation.nuit_suivie_travail,
            "soiree_to_day": validation.soir_vers_jour
        }
        
        fairness_dict = {
            "night_std": fairness.night_std,
            "eve_std": fairness.eve_std
        }
    else:
        violations_counts = {}
        fairness_dict = {}
        vacancies = 0

    # Convert assignments (PairSchedule) -> DataFrame (Legacy format)
    rows = []
    for a in schedule.assignments:
        # Flatten pair
        # Person A
        if a.person_a:
             rows.append({
                 "name": a.person_a,
                 "week": a.week,
                 "day": a.day,
                 "shift": a.shift # "D", "N", "S"
             })
        # Person B (if any)
        if a.person_b:
             rows.append({
                 "name": a.person_b,
                 "week": a.week,
                 "day": a.day,
                 "shift": a.shift
             })
    
    assignments_df = pd.DataFrame(rows)
    if assignments_df.empty:
         assignments_df = pd.DataFrame(columns=["name", "week", "day", "shift"])
    
    summary = {
        "weeks": schedule.weeks,
        "people": schedule.people_count,
        "score": schedule.score,
        "status": schedule.status,
        "solve_time": schedule.solve_time_seconds,
        "vacancies": vacancies,
        "best_seed": best_seed
    }
    
    metrics_json = {
        "violations": violations_counts,
        "fairness": fairness_dict,
        "config": solver_cfg.to_dict(),
    }
    
    return SolveResult(
        assignments=assignments_df,
        summary=summary,
        metrics_json=metrics_json,
    )


# Legacy alias for backwards compatibility
SolveConfig = SolverConfig
