"""
EDO (Earned Day Off) System
===========================
Manages EDO allocation with 50/50 alternation by week.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from rota.models.person import Person
from rota.solver.staffing import JOURS
from rota.utils.logging_setup import get_logger, log_function_call

logger = get_logger("rota.solver.edo")


@dataclass
class EDOPlan:
    """EDO allocation plan."""
    plan: Dict[int, Set[str]]  # {week: set(names who get EDO)}
    fixed: Dict[str, str]      # {name: fixed_day or ""}
    
    def get_edo_day(self, name: str, week: int) -> Optional[str]:
        """Get the EDO day for a person in a week, if any."""
        if name not in self.plan.get(week, set()):
            return None
        
        fixed = self.fixed.get(name, "")
        if fixed and fixed in JOURS:
            return fixed
        return None  # Will be assigned dynamically


@log_function_call
def build_edo_plan(
    people: List[Person],
    weeks: int,
    fixed_global: Optional[str] = None,
) -> EDOPlan:
    """
    Build EDO assignment plan.
    
    Algorithm (from legacy_v29.py):
        - Group eligible people by workdays_per_week
        - Split each group 50/50
        - Odd weeks: first half gets EDO
        - Even weeks: second half gets EDO
    
    Args:
        people: List of Person objects
        weeks: Number of weeks in horizon
        fixed_global: Global EDO day override
        
    Returns:
        EDOPlan with week assignments and fixed days
    """
    logger.info(f"Building EDO plan for {weeks} weeks")
    
    plan = {w: set() for w in range(1, weeks + 1)}
    
    # Group eligible people by workdays_per_week
    groups: Dict[int, List[str]] = {}
    for p in people:
        if p.edo_eligible:
            wd = p.workdays_per_week
            groups.setdefault(wd, []).append(p.name)
    
    logger.debug(f"EDO groups: {[(k, len(v)) for k, v in groups.items()]}")
    
    # Split each group and alternate by week
    for wd, names in groups.items():
        names = sorted(names)  # Deterministic ordering
        half = (len(names) + 1) // 2  # Round up for first half
        
        first_half = names[:half]
        second_half = names[half:]
        
        logger.debug(f"Group {wd}j: {len(first_half)} first half, {len(second_half)} second half")
        
        for w in range(1, weeks + 1):
            if w % 2 == 1:  # Odd weeks
                plan[w].update(first_half)
            else:  # Even weeks
                plan[w].update(second_half)
    
    # Build fixed day mapping
    fixed = {}
    for p in people:
        if p.edo_fixed_day and p.edo_fixed_day in JOURS:
            fixed[p.name] = p.edo_fixed_day
        elif fixed_global and fixed_global in JOURS:
            fixed[p.name] = fixed_global
        else:
            fixed[p.name] = ""
    
    logger.info(f"EDO plan: {sum(len(s) for s in plan.values())} total EDO days over {weeks} weeks")
    
    return EDOPlan(plan=plan, fixed=fixed)


def get_edo_count_per_week(edo_plan: EDOPlan) -> Dict[int, int]:
    """Get count of EDOs per week."""
    return {w: len(names) for w, names in edo_plan.plan.items()}


def is_edo_day(
    edo_plan: EDOPlan,
    name: str,
    week: int,
    day: str,
    assigned_shifts: Dict[Tuple[str, int, str], str],
) -> bool:
    """
    Determine if a specific day is this person's EDO.
    
    Logic:
        1. If person not in EDO plan for this week: False
        2. If person has fixed day and it's OFF: that day is EDO
        3. Else: first OFF day of week is EDO
        
    Args:
        edo_plan: The EDO plan
        name: Person name
        week: Week number
        day: Day to check
        assigned_shifts: {(name, week, day): shift} for checking what's assigned
        
    Returns:
        True if this day should be marked as EDO
    """
    # Check if person gets EDO this week
    if name not in edo_plan.plan.get(week, set()):
        return False
    
    # Check if this person has a fixed day
    fixed = edo_plan.fixed.get(name, "")
    if fixed and fixed in JOURS:
        # Fixed day requested
        if day == fixed:
            # Check if this day is available (not already assigned)
            shift = assigned_shifts.get((name, week, day))
            if shift is None or shift == "OFF":
                return True
        return False
    
    # No fixed day: find first OFF day
    for d in JOURS:
        shift = assigned_shifts.get((name, week, d))
        if shift is None or shift == "OFF":
            return d == day
    
    return False


def mark_edo_in_schedule(
    edo_plan: EDOPlan,
    name: str,
    week: int,
    schedule: Dict[Tuple[str, int, str], str],
) -> Optional[str]:
    """
    Mark EDO in schedule and return the EDO day.
    
    Args:
        edo_plan: The EDO plan
        name: Person name
        week: Week number
        schedule: Mutable schedule dict to update
        
    Returns:
        Day that was marked as EDO, or None
    """
    if name not in edo_plan.plan.get(week, set()):
        return None
    
    fixed = edo_plan.fixed.get(name, "")
    
    # Try fixed day first
    if fixed and fixed in JOURS:
        key = (name, week, fixed)
        current = schedule.get(key)
        if current is None or current == "OFF":
            schedule[key] = "EDO"
            return fixed
        else:
            # Fixed day is busy - mark first OFF as EDO* 
            for d in JOURS:
                k = (name, week, d)
                if schedule.get(k) is None or schedule.get(k) == "OFF":
                    schedule[k] = "EDO*"  # Conflict indicator
                    return d
    else:
        # No fixed day: first OFF becomes EDO
        for d in JOURS:
            key = (name, week, d)
            current = schedule.get(key)
            if current is None or current == "OFF":
                schedule[key] = "EDO"
                return d
    
    return None
