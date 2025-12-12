"""
Pair-Based OR-Tools Solver (Optimized)
======================================
Schedules staff using CP-SAT constraint programming.

OPTIMIZATION: Uses Person-Shift variables (O(N)) instead of Pair variables (O(N^2)).
Pairs are reconstructed in the output phase.

Key model:
- Jour (D) and Nuit (N): require 2 people per slot (pairs reconstructed post-solve)
- Soir (S): solo shifts, 1 person per slot
- Variables: assign[person][week][day][shift] = 1 if person works this shift
"""
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ortools.sat.python import cp_model

from rota.models.constraints import FairnessMode, SolverConfig
from rota.models.person import Person
from rota.models.rules import SHIFTS
from rota.solver.edo import EDOPlan
from rota.solver.staffing import JOURS, WeekStaffing
from rota.utils.logging_setup import SolverLogger, get_logger

logger = get_logger("rota.solver.engine")
slog = SolverLogger("rota.solver.engine")


@dataclass
class PairAssignment:
    """A single pair assignment."""
    week: int
    day: str
    shift: str
    slot_idx: int
    person_a: str
    person_b: str  # Empty for solo shifts (S)
    
    def __repr__(self):
        if self.person_b:
            return f"W{self.week} {self.day} {self.shift}#{self.slot_idx}: {self.person_a} / {self.person_b}"
        return f"W{self.week} {self.day} {self.shift}#{self.slot_idx}: {self.person_a}"


@dataclass
class PairSchedule:
    """Complete schedule with pair assignments."""
    assignments: List[PairAssignment]
    weeks: int
    people_count: int
    status: str  # "optimal", "feasible", "infeasible"
    score: float = 0.0
    solve_time_seconds: float = 0.0
    stats: Dict = field(default_factory=dict)
    
    def get_person_shifts(self, name: str) -> List[PairAssignment]:
        """Get all shifts for a person."""
        return [a for a in self.assignments 
                if a.person_a == name or a.person_b == name]
    
    def get_day_assignments(self, week: int, day: str) -> List[PairAssignment]:
        """Get all assignments for a specific day."""
        return [a for a in self.assignments 
                if a.week == week and a.day == day]
    
    def count_shifts(self, name: str, shift: str) -> int:
        """Count shifts of a type for a person."""
        return sum(1 for a in self.assignments 
                   if (a.person_a == name or a.person_b == name) and a.shift == shift)
    
    def get_person_day_matrix(self, code_map: Optional[Dict[str, str]] = None) -> Dict[tuple, str]:
        """
        Build matrix of (name, week, day) -> shift code.
        
        Args:
            code_map: Optional mapping of shift codes (e.g., {"D": "J"} for display)
            
        Returns:
            Dict mapping (person_name, week, day) to shift code
        """
        matrix = {}
        for a in self.assignments:
            code = code_map.get(a.shift, a.shift) if code_map else a.shift
            if a.person_a:
                matrix[(a.person_a, a.week, a.day)] = code
            if a.person_b:
                matrix[(a.person_b, a.week, a.day)] = code
        return matrix
    
    def get_slot_counts(self) -> Dict[tuple, int]:
        """
        Get assignment counts per (week, day, shift) slot.
        
        Returns:
            Dict mapping (week, day, shift) to count of assigned slots
        """
        from collections import defaultdict
        counts = defaultdict(int)
        for a in self.assignments:
            counts[(a.week, a.day, a.shift)] += 1
        return dict(counts)


def solve_pairs(
    people: List[Person],
    config: SolverConfig,
    staffing: Dict[int, WeekStaffing],
    edo_plan: EDOPlan,
    days: List[str] = JOURS,
) -> PairSchedule:
    """
    Solve scheduling problem with pair assignments.
    
    Uses Person-Shift model for efficiency, reconstructs pairs in output.
    
    Args:
        people: List of Person objects
        config: Solver configuration
        staffing: Slot requirements per week/day/shift
        edo_plan: EDO allocation plan
        days: Days of the week
        
    Returns:
        PairSchedule with assignments
    """
    start_time = time.time()
    weeks = config.weeks
    
    slog.phase("Building Person-Shift Model")
    logger.info(f"Solving: {len(people)} people, {weeks} weeks, {len(days)} days/week")
    
    if not people:
        return PairSchedule(
            assignments=[],
            weeks=weeks,
            people_count=0,
            status="infeasible",
            solve_time_seconds=time.time() - start_time,
        )
    
    model = cp_model.CpModel()
    names = [p.name for p in people]
    name_to_person = {p.name: p for p in people}
    
    # ========== Variables ==========
    slog.step("Creating Person-Shift variables")
    
    # assign[p][w][d][s] = 1 if person p works shift s on day d of week w
    assign = {}
    for p in names:
        assign[p] = {}
        for w in range(1, weeks + 1):
            assign[p][w] = {}
            for d in days:
                assign[p][w][d] = {}
                for s in ["D", "N", "S"]:
                    var_name = f"assign_{p}_{w}_{d}_{s}"
                    assign[p][w][d][s] = model.NewBoolVar(var_name)
    
    # Helper: person_works[p][w][d] = 1 if person works any shift on that day
    person_works = {}
    for p in names:
        person_works[p] = {}
        for w in range(1, weeks + 1):
            person_works[p][w] = {}
            for d in days:
                var_name = f"works_{p}_{w}_{d}"
                person_works[p][w][d] = model.NewBoolVar(var_name)
    
    num_vars = len(names) * weeks * len(days) * 4
    logger.debug(f"Created {num_vars} assignment variables (Person-Shift model)")
    
    # ========== Hard Constraints ==========
    slog.phase("Adding Hard Constraints")
    
    # 1. Staffing requirements: SOFT constraint (allow unfilled slots)
    # Unfilled slots will be reported to manager for external contractors
    # D: 4 pairs = 8 people, N: 1 pair = 2 people, S: 1 solo
    slog.step("Constraint: Staffing requirements (Soft - allow gaps)")
    unfilled_vars = []
    
    for w in range(1, weeks + 1):
        for d in days:
            # Day shift (D): 4 pairs = 8 people
            d_slots = staffing[w].slots[d]["D"]
            d_people_needed = d_slots * 2
            d_assigned = sum(assign[p][w][d]["D"] for p in names)
            d_unfilled = model.NewIntVar(0, d_people_needed, f"unfilled_D_{w}_{d}")
            model.Add(d_assigned + d_unfilled == d_people_needed)
            unfilled_vars.append((d_unfilled, "D", w, d))
            
            # Night shift (N): 1 pair = 2 people
            n_slots = staffing[w].slots[d]["N"]
            n_people_needed = n_slots * 2
            n_assigned = sum(assign[p][w][d]["N"] for p in names)
            n_unfilled = model.NewIntVar(0, n_people_needed, f"unfilled_N_{w}_{d}")
            model.Add(n_assigned + n_unfilled == n_people_needed)
            unfilled_vars.append((n_unfilled, "N", w, d))
            
            # Soir shift (S): solo
            s_slots = staffing[w].slots[d].get("S", 0)
            if s_slots > 0:
                s_assigned = sum(assign[p][w][d]["S"] for p in names)
                s_unfilled = model.NewIntVar(0, s_slots, f"unfilled_S_{w}_{d}")
                model.Add(s_assigned + s_unfilled == s_slots)
                unfilled_vars.append((s_unfilled, "S", w, d))
    
    # 2. Link person_works to shift assignments
    slog.step("Constraint: Link person_works helper")
    for p in names:
        for w in range(1, weeks + 1):
            for d in days:
                # person_works = 1 if any shift is assigned
                all_shifts = [assign[p][w][d][s] for s in ["D", "N", "S"]]
                model.AddMaxEquality(person_works[p][w][d], all_shifts)
    
    # 3. At most one shift per person per day
    slog.step("Constraint: One shift per person per day")
    for p in names:
        for w in range(1, weeks + 1):
            for d in days:
                model.Add(sum(assign[p][w][d][s] for s in ["D", "N", "S"]) <= 1)
    
    # 4. No work after night (rest day required)
    if config.forbid_night_to_day:
        slog.step("Constraint: No work after night")
        for p in names:
            for w in range(1, weeks + 1):
                for i, d in enumerate(days[:-1]):
                    next_d = days[i + 1]
                    # If worked night today, don't work tomorrow
                    model.Add(person_works[p][w][next_d] == 0).OnlyEnforceIf(assign[p][w][d]["N"])
    
    # 5. Max nights per person (over horizon)
    slog.step("Constraint: Max nights per person")
    night_counts = {}
    for p in names:
        person = name_to_person[p]
        night_assignments = [assign[p][w][d]["N"] for w in range(1, weeks + 1) for d in days]
        night_counts[p] = model.NewIntVar(0, weeks * len(days), f"nights_{p}")
        model.Add(night_counts[p] == sum(night_assignments))
        
        if person.max_nights < weeks * len(days):
            model.Add(night_counts[p] <= person.max_nights)
    
    # 5b. Max consecutive nights (sequence limit)
    if config.max_nights_sequence < len(days):
        slog.step(f"Constraint: Max {config.max_nights_sequence} consecutive nights")
        
        # Build ordered list of all days across weeks
        all_days_ordered = [(w, d) for w in range(1, weeks + 1) for d in days]
        
        for p in names:
            window_size = config.max_nights_sequence + 1
            for start_idx in range(len(all_days_ordered) - window_size + 1):
                window_days = all_days_ordered[start_idx:start_idx + window_size]
                window_nights = [assign[p][w][d]["N"] for (w, d) in window_days]
                model.Add(sum(window_nights) <= config.max_nights_sequence)
    
    # 6. EDO: Person doesn't work on EDO day
    slog.step("Constraint: EDO days")
    for p in names:
        for w in range(1, weeks + 1):
            if p in edo_plan.plan.get(w, set()):
                fixed = edo_plan.fixed.get(p, "")
                if fixed and fixed in days:
                    model.Add(person_works[p][w][fixed] == 0)
    
    # 7. 48h/week constraint: max 48 hours per week (Mon-Fri)
    slog.step("Constraint: 48h per week")
    for p in names:
        for w in range(1, weeks + 1):
            week_hours = []
            for d in days:
                for s in ["D", "N", "S"]:
                    week_hours.append(assign[p][w][d][s] * SHIFTS[s].hours)
            model.Add(sum(week_hours) <= 48)
    
    # 7b. 48h rolling window constraint (across weeks, weekend = 0h)
    # Optimized: Direct linear constraint without intermediate IntVars
    slog.step("Constraint: 48h rolling window (Hard)")
    # Note: Day indices are 0=Mon, 1=Tue, ..., 4=Fri
    
    # Pre-build assignment hour expressions for each person/day
    # hours_expr[p][(w,d)] = linear expression for hours worked
    hours_expr = {}
    for p in names:
        hours_expr[p] = {}
        for w in range(1, weeks + 1):
            for d in days:
                # Sum hours directly without creating new IntVar
                hours_expr[p][(w, d)] = sum(
                    assign[p][w][d][s] * SHIFTS[s].hours
                    for s in ["D", "N", "S"]
                )
    
    # Apply rolling window constraint
    # Windows that span week boundaries need special handling
    for p in names:
        for w in range(1, weeks + 1):
            # Windows starting Mon-Fri of this week
            for start_day_idx in range(5):  # Mon=0 to Fri=4
                window_hours = []
                
                # Collect 7 days starting from start_day_idx
                for offset in range(7):
                    day_idx = (start_day_idx + offset) % 7
                    if day_idx >= 5:  # Weekend (Sat=5, Sun=6)
                        continue  # 0 hours, skip
                    
                    # Calculate which week this falls in
                    week_offset = (start_day_idx + offset) // 7
                    target_week = w + week_offset
                    
                    if target_week > weeks:
                        break  # Beyond horizon
                    
                    target_day = days[day_idx]
                    window_hours.append(hours_expr[p][(target_week, target_day)])
                
                if window_hours:
                    model.Add(sum(window_hours) <= 48)
    
    # 9. Max consecutive work days
    max_days = getattr(config, "max_consecutive_days", 6)
    if max_days and max_days < 7 * 4: # Sanity check
        slog.step(f"Hard: Max {max_days} consecutive workdays (Mon-Fri)")
        for p in names:
             timeline_vars = []
             for w in range(1, weeks + 1):
                 # Mon-Fri
                 for d in days:
                     # Working if matches any shift (D, N, S)
                     # Since strict constraint ensures max 1 shift/day, sum is 0 or 1
                     working = model.NewBoolVar(f"working_{p}_{w}_{d}")
                     model.Add(sum(assign[p][w][d][s] for s in ["D", "N", "S"]) == working)
                     timeline_vars.append(working)
                 
                 # Weekend padding (Sat, Sun) - assumed 0 for week solver
                 # This resets consecutive count unless max_days allows bridging (e.g. if we worked weekend)
                 # But here we assume 0, so it effectively limits consecutive days within M-F blocks.
                 if w < weeks: 
                      timeline_vars.append(0) 
                      timeline_vars.append(0) 
            
             # Sliding window constraint
             window_size = max_days + 1
             for i in range(len(timeline_vars) - window_size + 1):
                  window = timeline_vars[i : i + window_size]
                  # Sum of any (max+1) days must be <= max
                  model.Add(sum(window) <= max_days)

    # 10. Individual preference: no_evening (no Soir shifts)
    slog.step("Constraint: No Soir preferences")
    for p in names:
        person = name_to_person[p]
        if person.no_evening:
            for w in range(1, weeks + 1):
                for d in days:
                    model.Add(assign[p][w][d]["S"] == 0)
    
    # 11. Forbid contractor pairs (contractors must be paired with regular staff)
    if config.forbid_contractor_pairs:
        contractors = [p.name for p in people if p.is_contractor]
        if len(contractors) >= 2:
            slog.step(f"Constraint: No contractor pairs ({len(contractors)} contractors)")
            # For pair shifts (D, N), if 2+ contractors work the same shift, that's a violation
            for w in range(1, weeks + 1):
                for d in days:
                    for s in ["D", "N"]:  # Only pair shifts
                        # Sum of contractors on this shift must be <= 1
                        contractor_count = sum(assign[p][w][d][s] for p in contractors)
                        model.Add(contractor_count <= 1)
    
    # ========== Soft Constraints (Objective) ==========

    slog.phase("Adding Soft Constraints")
    objective_terms = []
    
    # 0. Minimize unfilled slots (highest priority)
    # These will be reported to manager for contractor coverage
    slog.step(f"Soft: Penalizing {len(unfilled_vars)} potential unfilled slots")
    total_unfilled = model.NewIntVar(0, len(unfilled_vars) * 10, "total_unfilled")
    model.Add(total_unfilled == sum(uv[0] for uv in unfilled_vars))
    objective_terms.append((total_unfilled, 10000))  # High penalty but below constraint violation
    
    # Build cohorts based on fairness mode
    cohorts = {}
    if config.fairness_mode == FairnessMode.BY_TEAM:
        for p in names:
            team = name_to_person[p].team or "no_team"
            cohorts.setdefault(team, []).append(p)
    elif config.fairness_mode == FairnessMode.GLOBAL:
        cohorts["all"] = names.copy()
    else:
        # Default: BY_WORKDAYS
        for p in names:
            wd = name_to_person[p].workdays_per_week
            key = f"{wd}j"
            cohorts.setdefault(key, []).append(p)
    
    slog.step(f"Cohorts ({config.fairness_mode.value}): {[(k, len(v)) for k, v in cohorts.items()]}")
    
    # Calculate proportional targets
    total_workdays_capacity = sum(p.workdays_per_week for p in people)
    total_night_person_shifts = weeks * len(days) * 2  # 1 pair/day = 2 people
    total_soir_slots = sum(staffing[w].slots[d].get("S", 0) for w in range(1, weeks + 1) for d in days)
    
    # Night fairness: proportional to workdays ratio
    slog.step("Soft: Night fairness (proportional)")
    night_targets = {}
    for p in names:
        person = name_to_person[p]
        night_target = int(round((person.workdays_per_week / total_workdays_capacity) * total_night_person_shifts))
        night_targets[p] = night_target
        
        # Add soft bounds: minimize deviation from target
        deviation = model.NewIntVar(0, weeks * len(days), f"night_dev_{p}")
        model.Add(deviation >= night_counts[p] - night_target)
        model.Add(deviation >= night_target - night_counts[p])
        objective_terms.append((deviation, 100))
    
    # Minimize spread within cohorts
    for cid, members in cohorts.items():
        if len(members) > 1:
            cohort_night_vars = [night_counts[m] for m in members]
            max_n = model.NewIntVar(0, weeks * len(days), f"max_nights_{cid}")
            min_n = model.NewIntVar(0, weeks * len(days), f"min_nights_{cid}")
            model.AddMaxEquality(max_n, cohort_night_vars)
            model.AddMinEquality(min_n, cohort_night_vars)
            spread = model.NewIntVar(0, weeks * len(days), f"night_spread_{cid}")
            model.Add(spread == max_n - min_n)
            objective_terms.append((spread, 500))
    
    # Soir fairness
    slog.step("Soft: Soir fairness (proportional)")
    soir_counts = {}
    for p in names:
        person = name_to_person[p]
        soir_assignments = [assign[p][w][d]["S"] for w in range(1, weeks + 1) for d in days]
        soir_counts[p] = model.NewIntVar(0, weeks * len(days), f"soirs_{p}")
        model.Add(soir_counts[p] == sum(soir_assignments))
        
        soir_target = int(round((person.workdays_per_week / total_workdays_capacity) * total_soir_slots))
        deviation = model.NewIntVar(0, weeks * len(days), f"soir_dev_{p}")
        model.Add(deviation >= soir_counts[p] - soir_target)
        model.Add(deviation >= soir_target - soir_counts[p])
        objective_terms.append((deviation, 50))
    
    # Minimize spread within cohorts for Soir
    for cid, members in cohorts.items():
        if len(members) > 1:
            cohort_soir_vars = [soir_counts[m] for m in members]
            max_s = model.NewIntVar(0, weeks * len(days), f"max_soirs_{cid}")
            min_s = model.NewIntVar(0, weeks * len(days), f"min_soirs_{cid}")
            model.AddMaxEquality(max_s, cohort_soir_vars)
            model.AddMinEquality(min_s, cohort_soir_vars)
            spread = model.NewIntVar(0, weeks * len(days), f"soir_spread_{cid}")
            model.Add(spread == max_s - min_s)
            objective_terms.append((spread, 300))
    
    # Total workday deviation
    slog.step("Soft: Workday target deviation")
    total_deviation = model.NewIntVar(0, len(names) * weeks * len(days), "total_deviation")
    deviation_terms = []
    
    person_totals = {}  # Store for stats
    for p in names:
        person = name_to_person[p]
        edo_weeks = sum(1 for w in range(1, weeks + 1) if p in edo_plan.plan.get(w, set()))
        target = person.workdays_per_week * weeks - edo_weeks
        
        person_total = model.NewIntVar(0, weeks * len(days), f"total_{p}")
        all_shifts = [assign[p][w][d][s] for w in range(1, weeks + 1) for d in days for s in ["D", "N", "S"]]
        model.Add(person_total == sum(all_shifts))
        person_totals[p] = (person_total, target)
        
        # HARD constraint: Never exceed target (Respect targets > Fill slots)
        model.Add(person_total <= target)
        
        # Soft: minimize undershoot (prefer filling up to target)
        undershoot = model.NewIntVar(0, weeks * len(days), f"undershoot_{p}")
        model.Add(undershoot >= target - person_total)
        deviation_terms.append(undershoot)
    
    model.Add(total_deviation == sum(deviation_terms))
    objective_terms.append((total_deviation, 5))
    
    # Clopening penalty: Soir followed by Jour shift next day
    slog.step("Soft: Soir→Jour penalty")
    clopening_count = model.NewIntVar(0, len(names) * weeks * len(days), "clopenings")
    clopening_terms = []
    
    for p in names:
        for w in range(1, weeks + 1):
            for d_idx in range(len(days) - 1):
                d = days[d_idx]
                d_next = days[d_idx + 1]
                
                # If Soir today and Jour tomorrow, penalize
                clopening = model.NewBoolVar(f"clop_{p}_{w}_{d}")
                model.AddBoolAnd([assign[p][w][d]["S"], assign[p][w][d_next]["D"]]).OnlyEnforceIf(clopening)
                model.AddBoolOr([assign[p][w][d]["S"].Not(), assign[p][w][d_next]["D"].Not()]).OnlyEnforceIf(clopening.Not())
                clopening_terms.append(clopening)
    
    if clopening_terms:
        model.Add(clopening_count == sum(clopening_terms))
        objective_terms.append((clopening_count, 1))
    
    # ========== Solve ==========
    slog.phase("Solving")
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = config.time_limit_seconds
    solver.parameters.log_search_progress = False
    
    # Multi-threading logic
    import os
    if hasattr(config, "parallel_portfolio") and config.parallel_portfolio:
        num_workers = config.workers_per_solve if config.workers_per_solve > 0 else 1
    else:
        num_workers = os.cpu_count() or 8
         
    solver.parameters.num_search_workers = num_workers
    slog.step(f"Using {num_workers} parallel workers")
    
    # Optimization hints
    solver.parameters.linearization_level = 2
    solver.parameters.cp_model_presolve = True
    
    if objective_terms:
        model.Minimize(sum(var * weight for var, weight in objective_terms))
    
    status = solver.Solve(model)
    solve_time = time.time() - start_time
    
    status_name = {
        cp_model.OPTIMAL: "optimal",
        cp_model.FEASIBLE: "feasible",
        cp_model.INFEASIBLE: "infeasible",
        cp_model.MODEL_INVALID: "invalid",
        cp_model.UNKNOWN: "unknown",
    }.get(status, "unknown")
    
    logger.info(f"Solve complete: status={status_name}, time={solve_time:.2f}s")
    
    if status not in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
        return PairSchedule(
            assignments=[],
            weeks=weeks,
            people_count=len(people),
            status=status_name,
            solve_time_seconds=solve_time,
        )
    
    # ========== Extract Solution & Reconstruct Pairs ==========
    slog.phase("Extracting Solution")
    assignments = []
    
    for w in range(1, weeks + 1):
        for d in days:
            # Pair shifts: D and N
            for s in ["D", "N"]:
                assigned_people = [p for p in names if solver.Value(assign[p][w][d][s]) == 1]
                
                # Pair them up (arbitrary pairing)
                slot_idx = 0
                for i in range(0, len(assigned_people), 2):
                    if i + 1 < len(assigned_people):
                        assignments.append(PairAssignment(
                            week=w,
                            day=d,
                            shift=s,
                            slot_idx=slot_idx,
                            person_a=assigned_people[i],
                            person_b=assigned_people[i + 1],
                        ))
                    else:
                        # Odd number (shouldn't happen), log as solo
                        logger.warning(f"Odd number for pair shift {s} on W{w} {d}")
                        assignments.append(PairAssignment(
                            week=w,
                            day=d,
                            shift=s,
                            slot_idx=slot_idx,
                            person_a=assigned_people[i],
                            person_b="",
                        ))
                    slot_idx += 1
            
            # Solo shifts: S only (Admin removed)
            for s in ["S"]:
                assigned_people = [p for p in names if solver.Value(assign[p][w][d][s]) == 1]
                for slot_idx, person in enumerate(assigned_people):
                    assignments.append(PairAssignment(
                        week=w,
                        day=d,
                        shift=s,
                        slot_idx=slot_idx,
                        person_a=person,
                        person_b="",
                    ))
    
    # Sort assignments
    assignments.sort(key=lambda a: (a.week, days.index(a.day), a.shift, a.slot_idx))
    
    score = solver.ObjectiveValue() if objective_terms else 0.0
    
    logger.info(f"Extracted {len(assignments)} assignments, score={score}")
    
    # Stats
    stats = {
        "solve_time": solve_time,
    }
    
    return PairSchedule(
        assignments=assignments,
        weeks=weeks,
        people_count=len(people),
        status=status_name,
        score=score,
        solve_time_seconds=solve_time,
        stats=stats,
    )
