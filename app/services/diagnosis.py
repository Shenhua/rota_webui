"""
Scenario Diagnosis Service
==========================
Analyzes the schedule to determine its state (Surplus, Deficit, Balanced).
"""
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from rota.models.person import Person
from rota.solver.pairs import PairSchedule
from rota.solver.edo import EDOPlan
from rota.solver.validation import ScheduleValidation
from rota.solver.staffing import WeekStaffing

@dataclass
class ScenarioResult:
    """Result of the diagnosis."""
    scenario_type: str  # "DEFICIT", "SURPLUS", "BALANCED"
    message: str
    details: List[Dict[str, Any]]
    metrics: Dict[str, Any]

class DiagnosisService:
    """Encapsulates business logic for schedule analysis."""
    
    @staticmethod
    def diagnose(
        schedule: PairSchedule, 
        people: List[Person], 
        validation: ScheduleValidation,
        edo_plan: EDOPlan,
        staffing: Optional[WeekStaffing] = None
    ) -> ScenarioResult:
        """
        Analyze the schedule and return a diagnosis.
        """
        # 1. Deficit Check (Priority)
        deficit_slots = validation.slots_vides
        if deficit_slots > 0:
            return DiagnosisService._diagnose_deficit(validation, staffing)
            
        # 2. Capacity Check (Surplus vs Balanced)
        # Calculate theoretical capacity vs actual assignment
        total_capacity = 0
        total_worked = 0
        schedule_weeks = schedule.weeks
        
        for p in people:
            # Capacity: workdays * weeks - EDOs
            edo_count = sum(1 for w in range(1, schedule_weeks+1) if p.name in edo_plan.plan.get(w, set()))
            total_capacity += (p.workdays_per_week * schedule_weeks - edo_count)
            
            # Worked: count actual shifts
            total_worked += schedule.count_shifts(p.name, 'D') + \
                            schedule.count_shifts(p.name, 'S') + \
                            schedule.count_shifts(p.name, 'N') + \
                            schedule.count_shifts(p.name, 'A')
                            
        surplus = total_capacity - total_worked
        
        metrics = {
            "capacity": total_capacity,
            "worked": total_worked,
            "surplus": surplus,
            "deficit_slots": deficit_slots
        }

        if surplus > 5:  # Threshold for significant surplus
            return ScenarioResult(
                scenario_type="SURPLUS",
                message=f"Surplus de Capacité ({surplus} créneaux disponibles)",
                details=[],
                metrics=metrics
            )
        else:
            return ScenarioResult(
                scenario_type="BALANCED",
                message="Planning Tendu / Équilibré (Juste-à-temps)",
                details=[],
                metrics=metrics
            )
            
    @staticmethod
    def _diagnose_deficit(validation: ScheduleValidation, staffing: Optional[WeekStaffing]) -> ScenarioResult:
        """Analyze missing slots."""
        missing_data = []
        
        # Determine specific needs
        gap_types = {"unfilled_slot", "incomplete_pair"}
        for v in validation.violations:
            if v.type in gap_types:
                count = getattr(v, "count", 1)
                # Estimate people needed
                people_needed = 1 if v.type == "incomplete_pair" else (count * 2 if v.shift in ["D", "N"] else count)
                shift_name = {"D": "Jour", "S": "Soir", "N": "Nuit"}.get(v.shift, v.shift)
                
                missing_data.append({
                    "Semaine": v.week, 
                    "Jour": v.day, 
                    "Quart": shift_name,
                    "Type": "Paire incomplète" if v.type == "incomplete_pair" else "Slot vide",
                    "Besoins": people_needed,
                    "Message": v.message
                })
                
        metrics = {"deficit_slots": validation.slots_vides}
        
        return ScenarioResult(
            scenario_type="DEFICIT",
            message=f"Déficit de Personnel: {validation.slots_vides} quarts non pourvus",
            details=missing_data,
            metrics=metrics
        )
