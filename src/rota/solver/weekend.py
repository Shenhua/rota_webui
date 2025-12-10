"""Weekend solver module using CP-SAT."""
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from ortools.sat.python import cp_model
from rota.models.person import Person


@dataclass
class WeekendConfig:
    """Configuration for weekend solver."""
    num_weeks: int
    staff_per_shift: int = 2  # 2 for Day, 2 for Night
    time_limit_seconds: int = 30
    max_weekends_per_month: int = 2  # Default max weekends per month (UI option)
    
    # Weights
    weight_fairness: int = 10
    weight_split_weekend: int = 5  # Penalty for working both Sat and Sun (unless 24h on one day)
    weight_24h_balance: int = 5    # Balance number of 24h shifts proportionally
    weight_consecutive_weekends: int = 50 # Penalty for working W and W+1
    
    # Hard constraints
    forbid_consecutive_nights: bool = True  # Forbid Sat N + Sun N


@dataclass
class WeekendAssignment:
    """Represents a single shift assignment on a weekend."""
    person: Person
    week: int
    day: str  # "Sam" or "Dim"
    shift: str  # "D" or "N"
    
    @property
    def hours(self) -> int:
        """Return shift hours (12h each)."""
        return 12


@dataclass
class WeekendResult:
    """Result of weekend solver."""
    assignments: List[WeekendAssignment]
    status: str
    solve_time: float
    message: str = ""
    
    def get_person_hours(self, person_name: str, week: int) -> int:
        """Get total hours worked by a person in a specific weekend."""
        return sum(
            a.hours for a in self.assignments 
            if a.person.name == person_name and a.week == week
        )
    
    def get_person_shift_type(self, person_name: str, week: int) -> str:
        """Return shift type: '24h', '12h', or 'OFF'."""
        hours = self.get_person_hours(person_name, week)
        if hours >= 24:
            return "24h"
        elif hours >= 12:
            return "12h"
        return "OFF"


class WeekendSolver:
    """Solver for weekend schedules (Sat/Sun)."""

    def __init__(self, config: WeekendConfig, people: List[Person], friday_night_workers: Dict[int, List[str]] = None):
        self.config = config
        self.people = [p for p in people if p.available_weekends]
        self.all_people = people  # Keep reference to all
        self.friday_night_workers = friday_night_workers or {}
        self.model = cp_model.CpModel()
        self.vars = {}  # (person_id, week, day, shift) -> BoolVar
        self.days = ["Sam", "Dim"]  # French: Samedi, Dimanche
        self.shifts = ["D", "N"]
        self.consecutive_penalties = [] # Store consecutive penalties to add to objective later
        self.total_deficits = [] # Store deficit variables

    def solve(self) -> WeekendResult:
        """Run the solver."""
        if not self.people:
            return WeekendResult([], "INFEASIBLE", 0.0, "Aucun personnel éligible week-end.")

        self._create_variables()
        self._add_coverage_constraints()
        self._add_workload_constraints()
        self._add_consistency_constraints()
        self._add_fairness_objective()

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = self.config.time_limit_seconds
        solver.parameters.log_search_progress = False
        
        status_val = solver.Solve(self.model)
        status_str = solver.StatusName(status_val)
        
        assignments = []
        if status_str in ("OPTIMAL", "FEASIBLE"):
            assignments = self._extract_solution(solver)
            
        return WeekendResult(
            assignments=assignments,
            status=status_str,
            solve_time=solver.WallTime(),
            message=f"Résolu avec statut {status_str}"
        )

    def _create_variables(self):
        """Create decision variables."""
        for p in self.people:
            for w in range(1, self.config.num_weeks + 1):
                for d in self.days:
                    for s in self.shifts:
                        self.vars[(p.id, w, d, s)] = self.model.NewBoolVar(
                            f"work_p{p.id}_w{w}_{d}_{s}"
                        )

    def _add_coverage_constraints(self):
        """Ensure staffing requirements are met (soft constraint)."""
        # 2 per shift per day
        target = self.config.staff_per_shift
        self.total_deficits = []
        
        for w in range(1, self.config.num_weeks + 1):
            for d in self.days:
                for s in self.shifts:
                    staff_vars = [
                        self.vars[(p.id, w, d, s)] 
                        for p in self.people
                    ]
                    
                    # Deficit variable: 0 if met, N if missing N people
                    deficit = self.model.NewIntVar(0, target, f"deficit_w{w}_{d}_{s}")
                    self.model.Add(sum(staff_vars) + deficit == target)
                    self.total_deficits.append(deficit)

    def _add_workload_constraints(self):
        """Personal workload limits."""
        for p in self.people:
            # Use config max_weekends_per_month or person-specific if set
            max_per_month = getattr(p, 'max_weekends_per_month', self.config.max_weekends_per_month)
            if max_per_month is None:
                max_per_month = self.config.max_weekends_per_month
            
            num_months = max(1, self.config.num_weeks / 4.0)
            max_weekends_total = int(max_per_month * num_months)
            
            # Track which weekends are worked
            weekend_worked_vars = []
            
            for w in range(1, self.config.num_weeks + 1):
                # Defines if person works at all this weekend
                is_working_weekend = self.model.NewBoolVar(f"working_weekend_p{p.id}_w{w}")
                weekend_shifts = [
                    self.vars[(p.id, w, d, s)] 
                    for d in self.days for s in self.shifts
                ]
                
                # Link is_working_weekend
                self.model.Add(sum(weekend_shifts) > 0).OnlyEnforceIf(is_working_weekend)
                self.model.Add(sum(weekend_shifts) == 0).OnlyEnforceIf(is_working_weekend.Not())
                weekend_worked_vars.append(is_working_weekend)

                # Max 24h per weekend (2 shifts max)
                self.model.Add(sum(weekend_shifts) <= 2)
                
                # Repos après nuit logic within weekend:
                # If working Sam Night, cannot work Dim Day.
                sat_n = self.vars[(p.id, w, "Sam", "N")]
                sun_d = self.vars[(p.id, w, "Dim", "D")]
                self.model.Add(sat_n + sun_d <= 1)

            # Max weekends over horizon
            if max_weekends_total > 0:
                 self.model.Add(sum(weekend_worked_vars) <= max_weekends_total)
            
            # Spreading: Penalize consecutive weekends
            for i in range(len(weekend_worked_vars) - 1):
                consecutive = self.model.NewBoolVar(f"consecutive_we_p{p.id}_w{i}")
                self.model.AddBoolAnd([weekend_worked_vars[i], weekend_worked_vars[i+1]]).OnlyEnforceIf(consecutive)
                self.model.AddBoolOr([weekend_worked_vars[i].Not(), weekend_worked_vars[i+1].Not()]).OnlyEnforceIf(consecutive.Not())
                # Store penalty to minimize later
                self.consecutive_penalties.append(consecutive * self.config.weight_consecutive_weekends)

    def _add_fairness_objective(self):
        """Minimize deviation and penalties with proportional fairness."""
        penalties = []
        
        # Add collected penalties from workload constraints
        if self.consecutive_penalties:
            penalties.extend(self.consecutive_penalties)
        
        # Calculate total workdays capacity for proportional fairness
        total_workdays = sum(p.workdays_per_week for p in self.people)
        total_shifts_needed = self.config.num_weeks * 2 * 2 * self.config.staff_per_shift # Correct total needed
        
        # Track shifts per person for proportional target
        total_shifts_per_person = []
        
        for p in self.people:
            # Proportional target based on workdays
            target = int(round((p.workdays_per_week / total_workdays) * total_shifts_needed))
            
            total_shifts = self.model.NewIntVar(0, self.config.num_weeks * 4, f"total_shifts_p{p.id}")
            all_p_shifts = [
                self.vars[(p.id, w, d, s)]
                for w in range(1, self.config.num_weeks + 1)
                for d in self.days
                for s in self.shifts
            ]
            self.model.Add(total_shifts == sum(all_p_shifts))
            total_shifts_per_person.append((total_shifts, target, p.id))
            
            # Add deviation from target to penalties
            deviation = self.model.NewIntVar(0, self.config.num_weeks * 4, f"dev_p{p.id}")
            self.model.Add(deviation >= total_shifts - target)
            self.model.Add(deviation >= target - total_shifts)
            penalties.append(deviation * self.config.weight_fairness)
        
        # Split weekend penalty (working both Sam and Dim)
        for p in self.people:
            for w in range(1, self.config.num_weeks + 1):
                works_sat = self.model.NewBoolVar(f"works_sat_p{p.id}_w{w}")
                works_sun = self.model.NewBoolVar(f"works_sun_p{p.id}_w{w}")
                
                sat_shifts = [self.vars[(p.id, w, "Sam", s)] for s in self.shifts]
                sun_shifts = [self.vars[(p.id, w, "Dim", s)] for s in self.shifts]
                
                self.model.Add(sum(sat_shifts) > 0).OnlyEnforceIf(works_sat)
                self.model.Add(sum(sat_shifts) == 0).OnlyEnforceIf(works_sat.Not())
                
                self.model.Add(sum(sun_shifts) > 0).OnlyEnforceIf(works_sun)
                self.model.Add(sum(sun_shifts) == 0).OnlyEnforceIf(works_sun.Not())
                
                # Penalty if both true
                both_days = self.model.NewBoolVar(f"both_days_p{p.id}_w{w}")
                self.model.AddBoolAnd([works_sat, works_sun]).OnlyEnforceIf(both_days)
                self.model.AddBoolOr([works_sat.Not(), works_sun.Not()]).OnlyEnforceIf(both_days.Not())
                
                penalties.append(both_days * self.config.weight_split_weekend)
        
        # 24h balance: Track 24h shifts and balance proportionally
        for p in self.people:
            shifts_24h = []
            for w in range(1, self.config.num_weeks + 1):
                is_24h = self.model.NewBoolVar(f"is_24h_p{p.id}_w{w}")
                weekend_shifts = [
                    self.vars[(p.id, w, d, s)] 
                    for d in self.days for s in self.shifts
                ]
                # 24h = exactly 2 shifts in one weekend
                self.model.Add(sum(weekend_shifts) == 2).OnlyEnforceIf(is_24h)
                self.model.Add(sum(weekend_shifts) != 2).OnlyEnforceIf(is_24h.Not())
                shifts_24h.append(is_24h)
            
            # Proportional 24h target
            total_workdays = max(1, sum(p.workdays_per_week for p in self.people))
            target_24h = max(1, int(round((p.workdays_per_week / total_workdays) * self.config.num_weeks)))
            total_24h = self.model.NewIntVar(0, self.config.num_weeks, f"total_24h_p{p.id}")
            self.model.Add(total_24h == sum(shifts_24h))
            
            dev_24h = self.model.NewIntVar(0, self.config.num_weeks, f"dev_24h_p{p.id}")
            self.model.Add(dev_24h >= total_24h - target_24h)
            self.model.Add(dev_24h >= target_24h - total_24h)
            penalties.append(dev_24h * self.config.weight_24h_balance)

        # Minimize global range (max - min shifts)
        if total_shifts_per_person:
            shift_vars = [t[0] for t in total_shifts_per_person]
            min_s = self.model.NewIntVar(0, self.config.num_weeks * 4, "min_shifts")
            max_s = self.model.NewIntVar(0, self.config.num_weeks * 4, "max_shifts")
            self.model.AddMinEquality(min_s, shift_vars)
            self.model.AddMaxEquality(max_s, shift_vars)
            penalties.append((max_s - min_s) * self.config.weight_fairness)

        # Minimize deficits (Highest priority)
        if hasattr(self, 'total_deficits'):
            weight_deficit = 100000  # Very high cost for missing a slot
            penalties.append(sum(self.total_deficits) * weight_deficit)

        self.model.Minimize(sum(penalties))

    def _extract_solution(self, solver: cp_model.CpSolver) -> List[WeekendAssignment]:
        """Convert solver vars to assignments."""
        assignments = []
        for p in self.people:
            for w in range(1, self.config.num_weeks + 1):
                for d in self.days:
                    for s in self.shifts:
                        if solver.BooleanValue(self.vars[(p.id, w, d, s)]):
                            assignments.append(WeekendAssignment(
                                person=p,
                                week=w,
                                day=d,
                                shift=s
                            ))
        return assignments

    def _add_consistency_constraints(self):
        """Add constraints linking to week schedule and internal consistency."""
        # 1. Fri Night -> Sat Day forbidden
        for w, workers in self.friday_night_workers.items():
            if w > self.config.num_weeks: continue
            for name in workers:
                p = next((p for p in self.people if p.name == name), None)
                if p:
                    # Forbid Sat Day
                    if (p.id, w, "Sam", "D") in self.vars:
                         self.model.Add(self.vars[(p.id, w, "Sam", "D")] == 0)
        
        # 2. No consecutive nights (Sat N + Sun N)
        if self.config.forbid_consecutive_nights:
            for p in self.people:
                for w in range(1, self.config.num_weeks + 1):
                    sat_n = self.vars.get((p.id, w, "Sam", "N"))
                    sun_n = self.vars.get((p.id, w, "Dim", "N"))
                    if sat_n is not None and sun_n is not None:
                        # Cannot work both nights
                        self.model.Add(sat_n + sun_n <= 1)


@dataclass
class WeekendValidation:
    unused_agents: List[str]                  # Names of agents with 0 shifts
    consecutive_3_plus: List[Tuple[str, int]] # (Name, StartWeek)
    
def validate_weekend_schedule(result: WeekendResult, people: List[Person], weeks: int) -> WeekendValidation:
    if result.status not in ["OPTIMAL", "FEASIBLE"]:
        return WeekendValidation([], [])
        
    shifts_per_person = {p.name: [] for p in people}
    for a in result.assignments:
        shifts_per_person[a.person.name].append(a.week)
        
    unused = [name for name, shifts in shifts_per_person.items() if not shifts]
    
    consecutive = []
    for name, shifts in shifts_per_person.items():
        weeks_worked = sorted(list(set(shifts)))
        # Check for sequence of 3
        for i in range(len(weeks_worked) - 2):
            if weeks_worked[i+1] == weeks_worked[i] + 1 and weeks_worked[i+2] == weeks_worked[i] + 2:
                consecutive.append((name, weeks_worked[i]))
                
    return WeekendValidation(unused, consecutive)
