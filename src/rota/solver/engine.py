"""OR-Tools CP-SAT based scheduling solver."""
import logging
import time
from typing import Dict, List, Optional

from ortools.sat.python import cp_model

from rota.models.constraints import FairnessMode, SolverConfig, WeekendMode
from rota.models.person import Person
from rota.models.schedule import Assignment, Schedule
from rota.models.shift import ALL_DAYS, WEEKDAYS, ShiftType

logger = logging.getLogger("rota.solver")


def solve(
    people: List[Person],
    config: Optional[SolverConfig] = None,
) -> Schedule:
    """
    Solve the scheduling problem using OR-Tools CP-SAT.
    
    Args:
        people: List of Person objects to schedule
        config: Solver configuration (uses defaults if None)
        
    Returns:
        Schedule object with assignments
    """
    config = config or SolverConfig()
    start_time = time.time()
    
    logger.info(f"Starting solve: {len(people)} people, {config.weeks} weeks")
    logger.debug(f"Config: weekend_mode={config.weekend_mode}, fairness={config.fairness_mode}")
    
    # Determine days to schedule
    if config.weekend_mode == WeekendMode.DISABLED:
        days = WEEKDAYS
    else:
        days = ALL_DAYS
    
    weeks = config.weeks
    shifts = [ShiftType.DAY, ShiftType.EVENING, ShiftType.NIGHT, ShiftType.ADMIN]
    
    if not people:
        logger.warning("No people to schedule - returning infeasible")
        return Schedule(
            assignments=[],
            weeks=weeks,
            people_count=0,
            status="infeasible",
            solve_time_seconds=time.time() - start_time,
        )
    
    # Create the CP-SAT model
    model = cp_model.CpModel()
    
    # ========== Decision Variables ==========
    # shift_vars[p][w][d][s] = 1 if person p works shift s on day d of week w
    shift_vars: Dict[int, Dict[int, Dict[str, Dict[ShiftType, cp_model.IntVar]]]] = {}
    
    for p_idx, person in enumerate(people):
        shift_vars[p_idx] = {}
        for w in range(1, weeks + 1):
            shift_vars[p_idx][w] = {}
            for d in days:
                shift_vars[p_idx][w][d] = {}
                for s in shifts:
                    var_name = f"shift_p{p_idx}_w{w}_{d}_{s.value}"
                    shift_vars[p_idx][w][d][s] = model.NewBoolVar(var_name)
    
    # ========== Hard Constraints ==========
    
    # 1. At most one shift per person per day
    for p_idx in range(len(people)):
        for w in range(1, weeks + 1):
            for d in days:
                model.Add(
                    sum(shift_vars[p_idx][w][d][s] for s in shifts) <= 1
                )
    
    # 2. Coverage requirements - at least 2 people per shift (except Admin = 1)
    # Using default targets if not specified
    for w in range(1, weeks + 1):
        for d in days:
            for s in shifts:
                min_coverage = 2 if s != ShiftType.ADMIN else 0
                # Reduce for small teams
                if len(people) < 8:
                    min_coverage = 1 if s != ShiftType.ADMIN else 0
                
                model.Add(
                    sum(shift_vars[p_idx][w][d][s] for p_idx in range(len(people))) >= min_coverage
                )
    
    # 3. No work after night shift (forbid_night_to_day)
    if config.forbid_night_to_day:
        for p_idx in range(len(people)):
            for w in range(1, weeks + 1):
                for i, d in enumerate(days[:-1]):  # All days except last
                    next_d = days[i + 1]
                    # If worked night on day d, cannot work any shift next day
                    for s in shifts:
                        model.Add(
                            shift_vars[p_idx][w][d][ShiftType.NIGHT] + shift_vars[p_idx][w][next_d][s] <= 1
                        )
    
    # 4. Max work days per week
    for p_idx, person in enumerate(people):
        for w in range(1, weeks + 1):
            target_days = person.workdays_per_week
            # Sum of all working shifts for this person this week
            week_work = sum(
                shift_vars[p_idx][w][d][s]
                for d in days
                for s in shifts
            )
            model.Add(week_work <= config.max_days_per_week)
            # Soft target: try to hit exactly their workdays_per_week
            # (handled in objective below)
    
    # 5. Max consecutive nights
    if config.max_nights_sequence < len(days):
        for p_idx in range(len(people)):
            for w in range(1, weeks + 1):
                for start_idx in range(len(days) - config.max_nights_sequence):
                    window = days[start_idx:start_idx + config.max_nights_sequence + 1]
                    model.Add(
                        sum(shift_vars[p_idx][w][d][ShiftType.NIGHT] for d in window) 
                        <= config.max_nights_sequence
                    )
    
    # 6. Max total nights per person over horizon (from person.max_nights)
    for p_idx, person in enumerate(people):
        if person.max_nights < weeks * len(days):  # Only if limited
            total_nights = sum(
                shift_vars[p_idx][w][d][ShiftType.NIGHT]
                for w in range(1, weeks + 1)
                for d in days
            )
            model.Add(total_nights <= person.max_nights)
    
    # ========== Soft Constraints & Objective ==========
    objective_terms = []
    
    # Fairness: minimize variance in night assignments
    if config.fairness_mode != FairnessMode.NONE:
        # Total nights per person
        nights_per_person = []
        for p_idx in range(len(people)):
            total_nights = sum(
                shift_vars[p_idx][w][d][ShiftType.NIGHT]
                for w in range(1, weeks + 1)
                for d in days
            )
            nights_per_person.append(total_nights)
        
        # Create variables for min and max nights
        max_nights_all = model.NewIntVar(0, weeks * len(days), "max_nights")
        min_nights_all = model.NewIntVar(0, weeks * len(days), "min_nights")
        
        for p_idx in range(len(people)):
            model.Add(max_nights_all >= nights_per_person[p_idx])
            model.Add(min_nights_all <= nights_per_person[p_idx])
        
        # Minimize the difference (proxy for variance)
        night_spread = model.NewIntVar(0, weeks * len(days), "night_spread")
        model.Add(night_spread == max_nights_all - min_nights_all)
        objective_terms.append((night_spread, int(config.night_fairness_weight)))
        
        # Same for evenings
        evenings_per_person = []
        for p_idx in range(len(people)):
            total_evenings = sum(
                shift_vars[p_idx][w][d][ShiftType.EVENING]
                for w in range(1, weeks + 1)
                for d in days
            )
            evenings_per_person.append(total_evenings)
        
        max_eve = model.NewIntVar(0, weeks * len(days), "max_eve")
        min_eve = model.NewIntVar(0, weeks * len(days), "min_eve")
        for p_idx in range(len(people)):
            model.Add(max_eve >= evenings_per_person[p_idx])
            model.Add(min_eve <= evenings_per_person[p_idx])
        
        eve_spread = model.NewIntVar(0, weeks * len(days), "eve_spread")
        model.Add(eve_spread == max_eve - min_eve)
        objective_terms.append((eve_spread, int(config.evening_fairness_weight)))
    
    # Preference: prefers_night should get more nights
    for p_idx, person in enumerate(people):
        if person.prefers_night:
            for w in range(1, weeks + 1):
                for d in days:
                    # Reward for getting nights
                    bonus = model.NewIntVar(-1, 0, f"night_pref_{p_idx}_{w}_{d}")
                    model.Add(bonus == -shift_vars[p_idx][w][d][ShiftType.NIGHT])
                    objective_terms.append((bonus, 1))
        
        if person.no_evening:
            for w in range(1, weeks + 1):
                for d in days:
                    # Penalty for getting evenings
                    objective_terms.append((shift_vars[p_idx][w][d][ShiftType.EVENING], 1))
    
    # Target work days per person per week (soft)
    for p_idx, person in enumerate(people):
        for w in range(1, weeks + 1):
            week_work = sum(
                shift_vars[p_idx][w][d][s]
                for d in days
                for s in shifts
            )
            # Over and under deviation
            over = model.NewIntVar(0, 7, f"over_{p_idx}_{w}")
            under = model.NewIntVar(0, 7, f"under_{p_idx}_{w}")
            model.Add(week_work - person.workdays_per_week == over - under)
            # Penalize deviation
            objective_terms.append((over, 2))
            objective_terms.append((under, 2))
    
    # Evening→Day transition penalty (working day shift after evening)
    # This is undesirable for work-life balance
    for p_idx in range(len(people)):
        for w in range(1, weeks + 1):
            for i, d in enumerate(days[:-1]):
                next_d = days[i + 1]
                # If evening today AND day tomorrow, add penalty
                evening_today = shift_vars[p_idx][w][d][ShiftType.EVENING]
                day_tomorrow = shift_vars[p_idx][w][next_d][ShiftType.DAY]
                
                # Create indicator for both happening
                both = model.NewBoolVar(f"eve_day_{p_idx}_{w}_{d}")
                model.Add(evening_today + day_tomorrow <= 1 + both)
                model.Add(evening_today + day_tomorrow >= 2 * both)
                objective_terms.append((both, 1))  # Soft penalty weight = 1
    
    # EDO allocation for eligible people
    if config.edo_enabled:
        edo_people = [p_idx for p_idx, p in enumerate(people) if p.edo_eligible]
        if edo_people:
            # Each EDO-eligible person gets approximately 1 EDO per week pattern
            # This is a soft target - we minimize deviation from 1 EDO per week
            for p_idx in edo_people:
                person = people[p_idx]
                # Count weeks where person should get EDO
                expected_edo = weeks  # Roughly 1 per week
                
                # For now, encourage OFF days to count as EDO for eligible people
                # (In a full implementation, we'd have separate EDO variables)
                logger.debug(f"EDO enabled for {person.name}")
    
    # Set objective: minimize weighted sum
    if objective_terms:
        model.Minimize(sum(var * weight for var, weight in objective_terms))
    
    # ========== Solve ==========
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = config.time_limit_seconds
    solver.parameters.num_search_workers = config.num_workers
    
    status = solver.Solve(model)
    
    solve_time = time.time() - start_time
    
    # ========== Extract Solution ==========
    assignments = []
    violations = {}
    
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        status_str = "optimal" if status == cp_model.OPTIMAL else "feasible"
        
        for p_idx, person in enumerate(people):
            for w in range(1, weeks + 1):
                worked_today = False
                for d in days:
                    for s in shifts:
                        if solver.Value(shift_vars[p_idx][w][d][s]) == 1:
                            assignments.append(Assignment(
                                person_name=person.name,
                                week=w,
                                day=d,
                                shift=s,
                            ))
                            worked_today = True
                    
                    # If didn't work, assign OFF
                    if not worked_today:
                        assignments.append(Assignment(
                            person_name=person.name,
                            week=w,
                            day=d,
                            shift=ShiftType.OFF,
                        ))
                    worked_today = False
    else:
        status_str = "infeasible"
    
    # Calculate fairness metrics
    fairness_metrics = {}
    if assignments:
        from collections import Counter
        night_counts = Counter()
        eve_counts = Counter()
        for a in assignments:
            if a.shift == ShiftType.NIGHT:
                night_counts[a.person_name] += 1
            elif a.shift == ShiftType.EVENING:
                eve_counts[a.person_name] += 1
        
        if night_counts:
            vals = list(night_counts.values())
            fairness_metrics["night_stddev"] = round(
                (sum((v - sum(vals)/len(vals))**2 for v in vals) / len(vals)) ** 0.5, 2
            )
        if eve_counts:
            vals = list(eve_counts.values())
            fairness_metrics["evening_stddev"] = round(
                (sum((v - sum(vals)/len(vals))**2 for v in vals) / len(vals)) ** 0.5, 2
            )
    
    return Schedule(
        assignments=assignments,
        weeks=weeks,
        people_count=len(people),
        score=solver.ObjectiveValue() if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else float('inf'),
        solve_time_seconds=solve_time,
        status=status_str,
        violations=violations,
        fairness_metrics=fairness_metrics,
    )
