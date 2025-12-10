"""
Results Export for Analysis
============================
Exports solver results to JSON for easy analysis by AI or scripts.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rota.models.person import Person
from rota.solver.edo import EDOPlan
from rota.solver.pairs import PairSchedule
from rota.solver.validation import FairnessMetrics, ValidationResult
from rota.utils.logging_setup import get_logger

logger = get_logger("rota.io.results_export")

RESULTS_DIR = Path("results")


def export_results(
    schedule: PairSchedule,
    people: List[Person],
    edo_plan: EDOPlan,
    validation: ValidationResult,
    fairness: FairnessMetrics,
    config: Dict[str, Any],
    weights: Dict[str, int],
    run_name: Optional[str] = None,
) -> Path:
    """
    Export complete results to JSON for analysis.
    
    Args:
        schedule: PairSchedule with assignments
        people: List of Person objects
        edo_plan: EDO allocation plan
        validation: Validation results
        fairness: Fairness metrics
        config: Solver configuration dict
        weights: Objective weights dict
        run_name: Optional name for the run
    
    Returns:
        Path to the exported JSON file
    """
    RESULTS_DIR.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = run_name or f"run_{timestamp}"
    output_path = RESULTS_DIR / f"{run_name}.json"
    
    # Build per-person stats
    person_stats = []
    for p in people:
        name = p.name
        j = schedule.count_shifts(name, "D")
        s = schedule.count_shifts(name, "S")  # S = Soir (not E)
        n = schedule.count_shifts(name, "N")
        a = schedule.count_shifts(name, "A")
        total = j + s + n + a
        
        weeks = schedule.weeks
        edo_weeks = sum(1 for w in range(1, weeks + 1) if name in edo_plan.plan.get(w, set()))
        target = p.workdays_per_week * weeks - edo_weeks
        
        person_stats.append({
            "name": name,
            "workdays_per_week": p.workdays_per_week,
            "edo_eligible": p.edo_eligible,
            "edo_fixed_day": p.edo_fixed_day or None,
            "prefers_night": p.prefers_night,
            "no_evening": p.no_evening,
            "max_nights": p.max_nights,
            "team": p.team or None,
            "shifts": {"J": j, "S": s, "N": n, "A": a},
            "total": total,
            "target": target,
            "delta": total - target,
            "edo_weeks": edo_weeks,
        })
    
    # Build cohort summary
    from statistics import pstdev
    cohorts = {}
    for ps in person_stats:
        cid = f"{ps['workdays_per_week']}j"
        cohorts.setdefault(cid, {"members": [], "N": [], "S": []})
        cohorts[cid]["members"].append(ps["name"])
        cohorts[cid]["N"].append(ps["shifts"]["N"])
        cohorts[cid]["S"].append(ps["shifts"]["S"])
    
    cohort_summary = {}
    for cid, data in cohorts.items():
        n_vals, s_vals = data["N"], data["S"]
        cohort_summary[cid] = {
            "count": len(data["members"]),
            "nights": {
                "min": min(n_vals),
                "max": max(n_vals),
                "std": pstdev(n_vals) if len(n_vals) > 1 else 0.0,
            },
            "evenings": {
                "min": min(s_vals),
                "max": max(s_vals),
                "std": pstdev(s_vals) if len(s_vals) > 1 else 0.0,
            }
        }
    
    # Build assignment list
    assignments_list = []
    for a in schedule.assignments:
        assignments_list.append({
            "week": a.week,
            "day": a.day,
            "shift": a.shift,
            "slot": a.slot_idx,
            "person_a": a.person_a,
            "person_b": a.person_b or None,
        })
    
    # Build complete result object
    result = {
        "meta": {
            "timestamp": datetime.now().isoformat(),
            "run_name": run_name,
        },
        "config": {
            "weeks": config.get("weeks"),
            "time_limit_seconds": config.get("time_limit_seconds"),
            "tries": config.get("tries"),
            "seed": config.get("seed"),
            "forbid_night_to_day": config.get("forbid_night_to_day"),
            "edo_enabled": config.get("edo_enabled"),
            "max_nights_sequence": config.get("max_nights_sequence"),
            "fairness_mode": config.get("fairness_mode"),
        },
        "weights": weights,
        "team": {
            "count": len(people),
            "by_workdays": {cid: len(data["members"]) for cid, data in cohorts.items()},
        },
        "solver": {
            "status": schedule.status,
            "solve_time_seconds": schedule.solve_time_seconds,
            "internal_score": schedule.score,
            "stats": schedule.stats,
        },
        "validation": validation.as_dict(),
        "fairness": {
            "night_std": fairness.night_std,
            "eve_std": fairness.eve_std,
            "by_cohort": {
                "nights": fairness.night_std_by_cohort,
                "evenings": fairness.eve_std_by_cohort,
            }
        },
        "cohort_summary": cohort_summary,
        "person_stats": person_stats,
        "assignments": assignments_list,
    }
    
    # Write to file
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Results exported to {output_path}")
    
    return output_path
