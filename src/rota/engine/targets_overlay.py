"""Bridge module to connect the new solver to the legacy UI API."""
from dataclasses import dataclass
from typing import Any, Dict, Optional

import pandas as pd

from rota.io.csv_loader import load_team
from rota.models.constraints import FairnessMode, SolverConfig
from rota.models.person import Person
from rota.solver.engine import solve as ortools_solve


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
    
    if cfg is not None:
        # Extract values from legacy config
        if hasattr(cfg, "weeks"):
            solver_cfg.weeks = int(cfg.weeks)
        if hasattr(cfg, "tries"):
            # OR-Tools doesn't need restarts - it's deterministic
            pass
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
    
    # Run solver
    schedule = ortools_solve(people, solver_cfg)
    
    # Convert to legacy format
    assignments_df = schedule.to_dataframe()
    
    summary = {
        "weeks": schedule.weeks,
        "people": schedule.people_count,
        "score": schedule.score,
        "status": schedule.status,
        "solve_time": schedule.solve_time_seconds,
        "vacancies": schedule.violations.get("vacancies", 0),
    }
    
    metrics_json = {
        "violations": schedule.violations,
        "fairness": schedule.fairness_metrics,
        "config": solver_cfg.to_dict(),
    }
    
    return SolveResult(
        assignments=assignments_df,
        summary=summary,
        metrics_json=metrics_json,
    )


# Legacy alias for backwards compatibility
SolveConfig = SolverConfig
