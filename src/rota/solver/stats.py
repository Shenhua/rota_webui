"""
Centralized Person Statistics
==============================
Single source of truth for all per-person statistics calculations.
Used by web view, Excel, PDF, and JSON exports.
"""
from dataclasses import dataclass
from typing import Dict, List

from rota.models.person import Person
from rota.solver.edo import EDOPlan
from rota.solver.pairs import PairSchedule
from rota.utils.logging_setup import get_logger

logger = get_logger("rota.solver.stats")


@dataclass
class PersonStats:
    """Statistics for a single person."""
    name: str
    jours: int      # D (Day) shifts
    soirs: int      # S (Soir) shifts
    nuits: int      # N (Night) shifts
    admin: int      # A (Admin) shifts
    total: int      # Total worked days
    target: int     # Expected workdays (workdays_per_week * weeks - edo_weeks)
    delta: int      # Difference (total - target)
    edo_weeks: int  # Number of EDO days taken
    
    # Additional metadata
    workdays_per_week: int = 0
    edo_eligible: bool = False


def calculate_person_stats(
    schedule: PairSchedule,
    people: List[Person],
    edo_plan: EDOPlan,
) -> List[PersonStats]:
    """
    Calculate statistics for all people. Single source of truth.
    
    Uses:
        - schedule.weeks for week count
        - schedule.count_shifts() for shift counts
        - edo_plan.plan for EDO tracking
    
    Args:
        schedule: The solved schedule
        people: List of Person objects
        edo_plan: EDO allocation plan
        
    Returns:
        List of PersonStats, one per person
    """
    weeks = schedule.weeks
    stats = []
    
    for p in people:
        name = p.name
        
        # Count shifts using schedule method (D, S, N, A codes)
        j = schedule.count_shifts(name, 'D')
        s = schedule.count_shifts(name, 'S')
        n = schedule.count_shifts(name, 'N')
        a = schedule.count_shifts(name, 'A')
        total = j + s + n + a
        
        # Count EDO weeks
        edo_weeks = sum(
            1 for w in range(1, weeks + 1) 
            if name in edo_plan.plan.get(w, set())
        )
        
        # Target = expected workdays minus EDO
        target = p.workdays_per_week * weeks - edo_weeks
        
        stats.append(PersonStats(
            name=name,
            jours=j,
            soirs=s,
            nuits=n,
            admin=a,
            total=total,
            target=target,
            delta=total - target,
            edo_weeks=edo_weeks,
            workdays_per_week=p.workdays_per_week,
            edo_eligible=p.edo_eligible,
        ))
    
    logger.debug(f"Calculated stats for {len(stats)} people, {weeks} weeks")
    return stats


def stats_to_dict_list(stats: List[PersonStats]) -> List[Dict]:
    """Convert stats to list of dicts for DataFrame or export."""
    return [
        {
            "Nom": s.name,
            "Jours": s.jours,
            "Soirs": s.soirs,
            "Nuits": s.nuits,
            "Admin": s.admin,
            "Total": s.total,
            "Cible": s.target,
            "Δ": s.delta,
            "EDO": s.edo_weeks,
        }
        for s in stats
    ]

