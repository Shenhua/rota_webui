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


@dataclass
class CoverageStats:
    """Coverage statistics for a single slot (week, day, shift)."""
    week: int
    day: str
    shift: str
    required: int   # Slots required by staffing
    assigned: int   # Slots actually filled
    gap: int        # required - assigned (positive = understaffed)


def calculate_coverage(
    schedule: PairSchedule,
    staffing: Dict,  # Dict[int, WeekStaffing] from derive_staffing
    days: List[str] = None,
) -> List[CoverageStats]:
    """
    Calculate coverage for all slots. Single source of truth.
    
    Args:
        schedule: The solved schedule
        staffing: Staffing requirements from derive_staffing
        days: List of day codes (defaults to JOURS)
        
    Returns:
        List of CoverageStats, one per (week, day, shift) slot
    """
    if days is None:
        from rota.solver.staffing import JOURS
        days = JOURS
    
    # Get slot counts from schedule
    slot_counts = schedule.get_slot_counts()
    
    coverage = []
    weeks = schedule.weeks
    
    for w in range(1, weeks + 1):
        week_staffing = staffing.get(w)
        if not week_staffing:
            continue
            
        for d in days:
            day_slots = week_staffing.slots.get(d, {})
            for shift_code in ["D", "S", "N"]:
                required = day_slots.get(shift_code, 0)
                assigned = slot_counts.get((w, d, shift_code), 0)
                gap = required - assigned
                
                coverage.append(CoverageStats(
                    week=w,
                    day=d,
                    shift=shift_code,
                    required=required,
                    assigned=assigned,
                    gap=gap,
                ))
    
    return coverage


def get_total_gaps(coverage: List[CoverageStats]) -> int:
    """Get total number of unfilled slots (gaps)."""
    return sum(max(0, c.gap) for c in coverage)


def get_coverage_percentage(coverage: List[CoverageStats]) -> float:
    """Get overall coverage percentage."""
    total_required = sum(c.required for c in coverage)
    total_assigned = sum(c.assigned for c in coverage)
    if total_required == 0:
        return 100.0
    return (total_assigned / total_required) * 100.0
