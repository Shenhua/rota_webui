"""
Staffing Configuration — Fixed Slot Numbers
============================================
Fixed staffing based on specification:
- Jour (D): 4 pairs = 8 people per day
- Nuit (N): 1 pair = 2 people per day
- Soir (S): 1 solo person per day
"""
from typing import Dict, List, Set
from dataclasses import dataclass

from rota.models.person import Person
from rota.utils.logging_setup import get_logger, log_function_call

logger = get_logger("rota.solver.staffing")

# Days of the week (French abbrev) - Weekdays only
JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven"]

# Shift hours for 48h constraint
SHIFT_HOURS = {
    "D": 10,  # Jour: 7h30-17h30 = 10h
    "J": 10,  # Alias for D (ShiftType.DAY)
    "S": 10,  # Soir: 9h30-19h30 = 10h
    "N": 12,  # Nuit: 19h30-7h30 = 12h
}

# Fixed staffing per day (from specification)
FIXED_STAFFING = {
    "D": 4,  # 4 pairs = 8 people for Jour
    "S": 1,  # 1 solo person for Soir
    "N": 1,  # 1 pair = 2 people for Nuit
}

# Shift types that use pairs vs solo
PAIR_SHIFTS = {"D", "N"}  # 2 people per slot
SOLO_SHIFTS = {"S"}  # 1 person per slot


@dataclass
class WeekStaffing:
    """Staffing requirements for one week."""
    week: int
    slots: Dict[str, Dict[str, int]]  # {day: {"D": n, "S": n, "N": n}}
    total_person_days: int
    edo_count: int
    
    def __repr__(self):
        return f"WeekStaffing(week={self.week}, total_pd={self.total_person_days}, edo={self.edo_count})"
    
    def get_people_needed(self) -> int:
        """Total people needed for this week."""
        total = 0
        for day_slots in self.slots.values():
            for shift, count in day_slots.items():
                if shift in PAIR_SHIFTS:
                    total += count * 2
                else:
                    total += count
        return total


@log_function_call
def derive_staffing(
    people: List[Person],
    weeks: int,
    edo_plan: Dict[int, Set[str]],
    days: List[str] = JOURS,
    custom_staffing: Dict[str, int] = None,
) -> Dict[int, WeekStaffing]:
    """
    Generate fixed staffing for all weeks.
    
    Uses FIXED_STAFFING unless custom_staffing is provided.
    
    Args:
        people: List of Person objects
        weeks: Number of weeks in horizon
        edo_plan: {week: set(names who get EDO this week)}
        days: List of day names
        custom_staffing: Optional override for FIXED_STAFFING
        
    Returns:
        {week: WeekStaffing} with slot counts per day/shift
    """
    logger.info(f"Deriving staffing for {weeks} weeks, {len(people)} people, {len(days)} days/week")
    
    staffing = custom_staffing or FIXED_STAFFING
    logger.info(f"Using staffing: D={staffing['D']} pairs, S={staffing['S']} solo, N={staffing['N']} pairs")
    
    total_wd = sum(p.workdays_per_week for p in people)
    logger.debug(f"Total workdays capacity: {total_wd} per week")
    
    result = {}
    
    for w in range(1, weeks + 1):
        # Count EDO for this week
        edo_count = sum(1 for p in people if p.edo_eligible and p.name in edo_plan.get(w, set()))
        
        # Available person-days this week
        person_days = total_wd - edo_count
        
        # Fixed slots per day
        per_day = {d: dict(staffing) for d in days}
        
        week_staffing = WeekStaffing(
            week=w,
            slots=per_day,
            total_person_days=person_days,
            edo_count=edo_count,
        )
        result[w] = week_staffing
        
        # Calculate people needed
        needed = week_staffing.get_people_needed()
        gap = person_days - needed
        
        logger.debug(f"Week {w}: available={person_days}, needed={needed}, gap={gap:+d}")
        if gap < 0:
            logger.warning(f"Week {w}: UNDERSTAFFED by {-gap} person-days!")
    
    return result


def get_total_slots(staffing: Dict[int, WeekStaffing], shift: str) -> int:
    """Count total slots of a shift type across all weeks."""
    total = 0
    for ws in staffing.values():
        for day_slots in ws.slots.values():
            total += day_slots.get(shift, 0)
    return total


def get_week_slot_count(staffing: Dict[int, WeekStaffing], week: int) -> Dict[str, int]:
    """Get total slot count per shift type for a specific week."""
    if week not in staffing:
        return {"D": 0, "S": 0, "N": 0}
    
    counts = {"D": 0, "S": 0, "N": 0}
    for day_slots in staffing[week].slots.values():
        for shift, count in day_slots.items():
            counts[shift] += count
    return counts


def calculate_people_needed(staffing: Dict[int, WeekStaffing]) -> Dict[str, int]:
    """
    Calculate total people-assignments needed per shift type.
    
    Note: For D/N, each slot needs 2 people (pair).
          For S/A, each slot needs 1 person.
    """
    people = {"D": 0, "S": 0, "N": 0}
    
    for ws in staffing.values():
        for day_slots in ws.slots.values():
            for shift, count in day_slots.items():
                if shift in PAIR_SHIFTS:
                    people[shift] += count * 2
                else:
                    people[shift] += count
    
    return people


def calculate_daily_hours() -> int:
    """
    Calculate total hours covered per day with fixed staffing.
    
    Jour: 4 pairs × 2 people × 10h = 80 person-hours
    Soir: 1 solo × 10h = 10 person-hours  
    Nuit: 1 pair × 2 people × 12h = 24 person-hours
    Total: 114 person-hours per day
    """
    hours = 0
    for shift, slots in FIXED_STAFFING.items():
        if shift in PAIR_SHIFTS:
            hours += slots * 2 * SHIFT_HOURS[shift]
        else:
            hours += slots * SHIFT_HOURS[shift]
    return hours
