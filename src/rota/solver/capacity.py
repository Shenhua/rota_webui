"""
Capacity Analysis
=================
Calculate team capacity vs. requirements to determine
staffing needs (excess or deficit).
"""
from dataclasses import dataclass
from typing import Dict, List, Optional

from rota.models.person import Person
from rota.solver.pairs import PairSchedule
from rota.solver.edo import EDOPlan
from rota.solver.staffing import WeekStaffing


@dataclass
class CapacityAnalysis:
    """Results of capacity analysis."""
    
    # Team capacity
    total_available_person_days: int  # Sum of all person-days available
    total_edo_days: int               # Days used for EDO
    net_capacity: int                 # Available - EDO
    
    # Requirements
    total_required_person_shifts: int # Sum of all required person-shifts
    total_assigned_person_shifts: int # Sum of all assigned person-shifts
    unfilled_person_shifts: int       # Required - Assigned
    
    # Summary
    capacity_balance: int             # Net capacity - required (positive = excess)
    
    # Per-shift breakdown
    by_shift: Dict[str, Dict]         # {"D": {"required": x, "assigned": y, "gap": z}}
    
    # Recommendations
    agents_needed: float              # Estimated additional agents (if negative = deficit)
    excess_agent_days: float          # Agent-days that could be freed up
    utilization_percent: float        # Overall utilization


def calculate_capacity(
    schedule: PairSchedule,
    people: List[Person],
    staffing: Dict[int, WeekStaffing],
    edo_plan: EDOPlan,
    efficiency_factor: float = 0.85,
) -> CapacityAnalysis:
    """
    Analyze team capacity vs. requirements.
    
    Args:
        schedule: Solved schedule
        people: Team members
        staffing: Staffing requirements per week
        edo_plan: EDO assignments
        efficiency_factor: Accounts for constraint overhead (default 0.85)
        
    Returns:
        CapacityAnalysis with all metrics
    """
    weeks = schedule.weeks
    
    # === Calculate team capacity ===
    total_available = 0
    total_edo = 0
    
    for p in people:
        person_weeks_capacity = p.workdays_per_week * weeks
        person_edo = sum(1 for w in range(1, weeks + 1) if p.name in edo_plan.plan.get(w, set()))
        
        total_available += person_weeks_capacity
        total_edo += person_edo
    
    net_capacity = total_available - total_edo
    
    # === Calculate requirements ===
    total_required = 0
    by_shift = {"D": {"required": 0, "assigned": 0}, 
                "S": {"required": 0, "assigned": 0}, 
                "N": {"required": 0, "assigned": 0}}
    
    for w in range(1, weeks + 1):
        if w not in staffing:
            continue
        week_staffing = staffing[w]
        for day, slots in week_staffing.slots.items():
            for shift_code, count in slots.items():
                if shift_code in ["D", "N"]:
                    # Pairs: each slot = 2 people
                    required_people = count * 2
                else:
                    # Solo: each slot = 1 person
                    required_people = count
                
                total_required += required_people
                if shift_code in by_shift:
                    by_shift[shift_code]["required"] += required_people
    
    # === Count assigned ===
    total_assigned = 0
    for a in schedule.assignments:
        people_in_slot = 0
        if a.person_a:
            people_in_slot += 1
        if a.person_b:
            people_in_slot += 1
        
        total_assigned += people_in_slot
        if a.shift in by_shift:
            by_shift[a.shift]["assigned"] += people_in_slot
    
    # Calculate gaps per shift
    for shift in by_shift:
        by_shift[shift]["gap"] = by_shift[shift]["required"] - by_shift[shift]["assigned"]
    
    unfilled = total_required - total_assigned
    capacity_balance = net_capacity - total_required
    
    # === Recommendations ===
    # Average workdays per person
    avg_workdays = sum(p.workdays_per_week for p in people) / len(people) if people else 4
    
    if unfilled > 0:
        # Need more people
        # Agent-days needed / (effective days per agent)
        effective_days_per_agent = avg_workdays * weeks * efficiency_factor
        agents_needed = unfilled / effective_days_per_agent if effective_days_per_agent > 0 else 0
        excess_agent_days = 0
    else:
        agents_needed = 0
        excess_agent_days = abs(capacity_balance) if capacity_balance > 0 else 0
    
    utilization = (total_assigned / net_capacity * 100) if net_capacity > 0 else 0
    
    return CapacityAnalysis(
        total_available_person_days=total_available,
        total_edo_days=total_edo,
        net_capacity=net_capacity,
        total_required_person_shifts=total_required,
        total_assigned_person_shifts=total_assigned,
        unfilled_person_shifts=unfilled,
        capacity_balance=capacity_balance,
        by_shift=by_shift,
        agents_needed=agents_needed,
        excess_agent_days=excess_agent_days,
        utilization_percent=utilization,
    )


def capacity_to_dict(analysis: CapacityAnalysis) -> Dict:
    """Convert analysis to dict for export."""
    return {
        "total_available_person_days": analysis.total_available_person_days,
        "total_edo_days": analysis.total_edo_days,
        "net_capacity": analysis.net_capacity,
        "total_required_person_shifts": analysis.total_required_person_shifts,
        "total_assigned_person_shifts": analysis.total_assigned_person_shifts,
        "unfilled_person_shifts": analysis.unfilled_person_shifts,
        "capacity_balance": analysis.capacity_balance,
        "by_shift": analysis.by_shift,
        "agents_needed": round(analysis.agents_needed, 1),
        "excess_agent_days": round(analysis.excess_agent_days, 1),
        "utilization_percent": round(analysis.utilization_percent, 1),
    }
