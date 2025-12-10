"""
Validation and Scoring
======================
Validate schedule quality and compute weighted score matching legacy formula.
"""
from typing import Dict, List, Set, Tuple
from dataclasses import dataclass
from statistics import pstdev

from rota.models.person import Person
from rota.solver.pairs import PairSchedule, PairAssignment
from rota.solver.edo import EDOPlan, JOURS
from rota.models.schedule import Schedule
from rota.solver.staffing import SHIFT_HOURS
from rota.utils.logging_setup import get_logger

logger = get_logger("rota.solver.validation")


@dataclass
class Violation:
    """Single violation with details."""
    type: str  # "unfilled_slot", "duplicate", "night_followed_work", "clopening", "48h_exceeded"
    severity: str  # "critical", "warning", "info"
    week: int
    day: str
    message: str
    person: str = ""
    shift: str = ""
    count: int = 1  # Number of missing slots or violations


@dataclass
class ValidationResult:
    """Validation metrics for a schedule."""
    slots_vides: int = 0           # Unfilled slots (critical)
    doublons_jour: int = 0         # Same person twice on same day
    nuit_suivie_travail: int = 0   # Night followed by work next day
    soir_vers_jour: int = 0        # Evening followed by day shift next day
    ecarts_hebdo_jours: int = 0    # Weekly workday target deviations
    ecarts_horizon_personnes: int = 0  # Horizon total deviations
    rolling_48h_violations: int = 0 # Strict 48h rolling window violations

    
    # Detailed violations list
    violations: List = None
    
    def __post_init__(self):
        if self.violations is None:
            self.violations = []
    
    def add_violation(self, v: Violation):
        """Add a violation to the list."""
        self.violations.append(v)
    
    def as_dict(self) -> Dict[str, int]:
        return {
            "Slots_vides": self.slots_vides,
            "doublons_jour": self.doublons_jour,
            "Nuit_suivie_travail": self.nuit_suivie_travail,
            "Soir_vers_Jour": self.soir_vers_jour,
            "Ecarts_hebdo_jours": self.ecarts_hebdo_jours,
            "Ecarts_horizon_personnes": self.ecarts_horizon_personnes,
        }
    
    @property
    def has_critical_issues(self) -> bool:
        """Check if there are critical issues (unfilled slots or duplicates)."""
        return self.slots_vides > 0 or self.doublons_jour > 0
    
    def get_critical_violations(self) -> List[Violation]:
        """Get only critical violations."""
        return [v for v in self.violations if v.severity == "critical"]
    
    def get_warnings(self) -> List[Violation]:
        """Get only warning violations."""
        return [v for v in self.violations if v.severity == "warning"]


@dataclass 
class FairnessMetrics:
    """Fairness metrics per cohort."""
    night_std: float = 0.0  # Std dev of night assignments
    eve_std: float = 0.0    # Std dev of evening assignments
    
    # Per-cohort breakdowns
    night_std_by_cohort: Dict[str, float] = None
    eve_std_by_cohort: Dict[str, float] = None
    
    def __post_init__(self):
        if self.night_std_by_cohort is None:
            self.night_std_by_cohort = {}
        if self.eve_std_by_cohort is None:
            self.eve_std_by_cohort = {}


def validate_schedule(
    schedule: PairSchedule,
    people: List[Person],
    edo_plan: EDOPlan,
    staffing: Dict,  # From derive_staffing
    days: List[str] = JOURS,
) -> ValidationResult:
    """
    Validate a schedule and count violations.
    
    Args:
        schedule: The schedule to validate
        people: List of Person objects
        edo_plan: EDO allocation plan
        staffing: Staffing requirements from derive_staffing
        days: Days of the week
        
    Returns:
        ValidationResult with all metrics
    """
    weeks = schedule.weeks
    name_to_person = {p.name: p for p in people}
    names = [p.name for p in people]
    
    result = ValidationResult()
    
    # Build lookup for who works when
    works_on = {}  # {(name, week, day): shift}
    for a in schedule.assignments:
        if a.person_a:
            works_on[(a.person_a, a.week, a.day)] = a.shift
        if a.person_b:
            works_on[(a.person_b, a.week, a.day)] = a.shift
    
    # 1. Check for unfilled slots
    for w in range(1, weeks + 1):
        ws = staffing.get(w)
        if not ws:
            continue
        for d in days:
            # Check shifts D, N, and S
            for s in ["D", "N", "S"]:
                expected = ws.slots[d].get(s, 0)
                actual = sum(1 for a in schedule.assignments 
                            if a.week == w and a.day == d and a.shift == s)
                if actual < expected:
                    missing = expected - actual
                    result.slots_vides += missing
                    result.add_violation(Violation(
                        type="unfilled_slot",
                        severity="critical",
                        week=w, day=d, shift=s,
                        message=f"Semaine {w} {d}: {missing} créneaux {s} non remplis",
                        count=missing
                    ))
                    
                # Check pairs are complete (both slots filled)
                for a in schedule.assignments:
                    if a.week == w and a.day == d and a.shift == s:
                        if not a.person_a or not a.person_b:
                            result.slots_vides += 1
                            result.add_violation(Violation(
                                type="incomplete_pair",
                                severity="critical",
                                week=w, day=d, shift=s,
                                message=f"Semaine {w} {d} {s}: paire incomplète"
                            ))
            
            # Solo shifts (S, A)
            for s in ["S", "A"]:
                expected = ws.slots[d].get(s, 0)
                actual = sum(1 for a in schedule.assignments 
                            if a.week == w and a.day == d and a.shift == s)
                if actual < expected:
                    missing = expected - actual
                    result.slots_vides += missing
                    result.add_violation(Violation(
                        type="unfilled_slot",
                        severity="critical",
                        week=w, day=d, shift=s,
                        message=f"Semaine {w} {d}: {missing} créneaux {s} non remplis"
                    ))
    
    # 2. Check for duplicates (same person twice on same day)
    for w in range(1, weeks + 1):
        for d in days:
            day_people = []
            for a in schedule.get_day_assignments(w, d):
                if a.person_a:
                    day_people.append(a.person_a)
                if a.person_b:
                    day_people.append(a.person_b)
            
            # Count duplicates
            seen = set()
            for name in day_people:
                if name in seen:
                    result.doublons_jour += 1
                    result.add_violation(Violation(
                        type="duplicate",
                        severity="critical",
                        week=w, day=d, person=name,
                        message=f"Semaine {w} {d}: {name} assigné 2 fois"
                    ))
                seen.add(name)
    
    # 3. Night followed by work next day
    for name in names:
        for w in range(1, weeks + 1):
            for i, d in enumerate(days[:-1]):
                next_d = days[i + 1]
                if works_on.get((name, w, d)) == "N" and (name, w, next_d) in works_on:
                    result.nuit_suivie_travail += 1
                    result.add_violation(Violation(
                        type="night_followed_work",
                        severity="warning",
                        week=w, day=d, person=name,
                        message=f"Semaine {w}: {name} travaille après nuit {d}"
                    ))
    
    # 4. Soir followed by Jour shift (clopening)
    for name in names:
        for w in range(1, weeks + 1):
            for i, d in enumerate(days[:-1]):
                next_d = days[i + 1]
                if works_on.get((name, w, d)) == "S" and works_on.get((name, w, next_d)) == "D":
                    result.soir_vers_jour += 1
                    result.add_violation(Violation(
                        type="clopening",
                        severity="warning",
                        week=w, day=d, person=name,
                        message=f"Semaine {w}: {name} Soir→Jour {d}→{next_d}"
                    ))
    
    # 5. 48h/week validation - check each person's weekly hours
    from rota.solver.staffing import SHIFT_HOURS
    hours_exceeded = 0
    for name in names:
        for w in range(1, weeks + 1):
            week_hours = 0
            for d in days:
                shift = works_on.get((name, w, d))
                if shift and shift in SHIFT_HOURS:
                    week_hours += SHIFT_HOURS[shift]
            
            if week_hours > 48:
                hours_exceeded += 1
                result.add_violation(Violation(
                    type="48h_exceeded",
                    severity="warning",
                    week=w, day="", person=name,
                    message=f"Semaine {w}: {name} travaille {week_hours}h (>48h)"
                ))

    # 5b. Strict 48h rolling window
    rolling_errors = check_rolling_48h(schedule)
    for err in rolling_errors:
        # Parse basic info from error string to create Violation
        # "Name: Totalh ..."
        parts = err.split(":")
        p_name = parts[0] if len(parts) > 0 else ""
        result.add_violation(Violation(
            type="48h_rolling",
            severity="critical", # Strict violation
            week=0, day="", person=p_name,
            message=err
        ))
        result.rolling_48h_violations += 1

        # We assume this contributes to some metric, maybe ecarts?
        # For now just adding violation is good for UI.

    
    # 6. Weekly workday deviations
    for name in names:
        person = name_to_person[name]
        for w in range(1, weeks + 1):
            # Target for this week
            has_edo = name in edo_plan.plan.get(w, set())
            target = person.workdays_per_week - (1 if has_edo else 0)
            
            # Actual
            actual = sum(1 for d in days if (name, w, d) in works_on)
            
            if actual != target:
                result.ecarts_hebdo_jours += 1
    
    # 6. Horizon total deviations
    for name in names:
        person = name_to_person[name]
        
        # Total target over horizon
        total_target = sum(
            person.workdays_per_week - (1 if name in edo_plan.plan.get(w, set()) else 0)
            for w in range(1, weeks + 1)
        )
        
        # Actual total
        actual_total = sum(1 for a in schedule.assignments 
                          if a.person_a == name or a.person_b == name)
        
        if actual_total != total_target:
            result.ecarts_horizon_personnes += 1
    
    logger.info(f"Validation: slots_vides={result.slots_vides}, doublons={result.doublons_jour}, "
                f"nuit2work={result.nuit_suivie_travail}, soir2jour={result.soir_vers_jour}")
    
    return result


def calculate_fairness(
    schedule: PairSchedule,
    people: List[Person],
    cohort_mode: str = "by-wd",  # "by-wd", "by-team", "none"
) -> FairnessMetrics:
    """
    Calculate fairness metrics for night and evening distribution.
    
    Args:
        schedule: The schedule
        people: List of Person objects
        cohort_mode: How to group people for fairness
        
    Returns:
        FairnessMetrics with std dev values
    """
    # Build cohorts
    if cohort_mode == "by-wd":
        cohorts = {}
        for p in people:
            key = f"{p.workdays_per_week}j"
            cohorts.setdefault(key, []).append(p.name)
    elif cohort_mode == "by-team":
        cohorts = {}
        for p in people:
            key = p.team if p.team else f"{p.workdays_per_week}j"
            cohorts.setdefault(key, []).append(p.name)
    else:
        # All in one cohort
        cohorts = {"all": [p.name for p in people]}
    
    # Count shifts per person
    night_counts = {p.name: 0 for p in people}
    eve_counts = {p.name: 0 for p in people}
    
    for a in schedule.assignments:
        if a.shift == "N":
            if a.person_a:
                night_counts[a.person_a] += 1
            if a.person_b:
                night_counts[a.person_b] += 1
        elif a.shift == "E":
            if a.person_a:
                eve_counts[a.person_a] += 1
            if a.person_b:
                eve_counts[a.person_b] += 1
    
    # Calculate std dev per cohort
    night_std_by_cohort = {}
    eve_std_by_cohort = {}
    
    for cid, members in cohorts.items():
        if len(members) > 1:
            night_vals = [night_counts[n] for n in members]
            eve_vals = [eve_counts[n] for n in members]
            night_std_by_cohort[cid] = pstdev(night_vals)
            eve_std_by_cohort[cid] = pstdev(eve_vals)
        else:
            night_std_by_cohort[cid] = 0.0
            eve_std_by_cohort[cid] = 0.0
    
    # Sum across cohorts
    total_night_std = sum(night_std_by_cohort.values())
    total_eve_std = sum(eve_std_by_cohort.values())
    
    return FairnessMetrics(
        night_std=total_night_std,
        eve_std=total_eve_std,
        night_std_by_cohort=night_std_by_cohort,
        eve_std_by_cohort=eve_std_by_cohort,
    )


def score_solution(
    validation: ValidationResult,
    fairness: FairnessMetrics,
    w_night: float = 10.0,
    w_eve: float = 3.0,
    w_dev: float = 2.0,
    w_clopen: float = 1.0,  # Soir->Jour
    w_nighthafter: float = 3.0, # Night -> Work
    w_unfilled: float = 10.0,
) -> float:
    """
    Calculate weighted score (lower is better).
    """
    score = (
        w_unfilled * validation.slots_vides +
        5 * validation.doublons_jour +
        w_nighthafter * validation.nuit_suivie_travail +
        w_clopen * validation.soir_vers_jour +
        0 * validation.rolling_48h_violations + 
        w_dev * validation.ecarts_hebdo_jours +
        w_dev * validation.ecarts_horizon_personnes +
        w_night * fairness.night_std +
        w_eve * fairness.eve_std
    )
    
    logger.info(f"Score: {score:.2f} (V={validation.slots_vides}, D={validation.doublons_jour}, "
                f"σN={fairness.night_std:.2f}, σE={fairness.eve_std:.2f})")
    return score

def check_rolling_48h(schedule: Schedule) -> List[str]:
    """
    Check strict 48h rolling window constraint.
    
    Rule: Max 48h over any 7 sliding days.
    Weekend hours are EXCLUDED from this count (as per specs).
    
    Args:
        schedule: The schedule to check
        
    Returns:
        List of error messages
    """
    errors = []
    weeks = schedule.weeks
    # We only care about weekday assignments for this rule
    # SHIFT_HOURS: D=10, E=10, N=12
    
    # Build timeline per person: [hours_day1, hours_day2, ...]
    # Timeline should include Sat/Sun as 0 hours to ensure "7 days" window is correct physically
    
    # Calendar mapping:
    # Each week has 7 days physically. Mon..Fri are work days. Sat/Sun are 0.
    # Total days = weeks * 7
    
    person_hours = {} # name -> list of hours per day (index 0 to 7*weeks-1)
    
    # Initialize with 0
    # Actually we can't easily init all persons if we don't have the list of all people easily.
    # But schedule.assignments has names.
    all_names = set()
    for a in schedule.assignments:
        if hasattr(a, 'person_a') and a.person_a: all_names.add(a.person_a)
        if hasattr(a, 'person_b') and a.person_b: all_names.add(a.person_b)
        if hasattr(a, 'person_name') and a.person_name: all_names.add(a.person_name)
        
    for name in all_names:
        person_hours[name] = [0] * (weeks * 7)
        
    # Fill hours
    # Map day str to index 0-4 (Mon-Fri)
    day_map = {"Lun": 0, "Mar": 1, "Mer": 2, "Jeu": 3, "Ven": 4}
    
    for a in schedule.assignments:
        if a.day not in day_map:
            continue
            
        w_idx = a.week - 1
        d_idx = day_map[a.day]
        global_idx = w_idx * 7 + d_idx
        
        # Handle ShiftType enum or string
        s_val = a.shift
        if hasattr(s_val, 'value'):
            s_val = s_val.value
            
        hours = SHIFT_HOURS.get(s_val, 0)
        
        persons_in_shift = []
        if hasattr(a, 'person_a') and a.person_a: persons_in_shift.append(a.person_a)
        if hasattr(a, 'person_b') and a.person_b: persons_in_shift.append(a.person_b)
        if hasattr(a, 'person_name') and a.person_name: persons_in_shift.append(a.person_name)
        
        for p in persons_in_shift:
             person_hours[p][global_idx] += hours

            
    # Check sliding window
    for name, timeline in person_hours.items():
        # Sliding window of size 7
        for i in range(len(timeline) - 6):
            window = timeline[i : i+7]
            total = sum(window)
            if total > 48:
                # Format a readable error
                start_day = i % 7
                start_week = (i // 7) + 1
                end_day = (i + 6) % 7
                end_week = ((i + 6) // 7) + 1
                
                # Check if it is purely within one week (Mon-Fri work) to simplify message
                msg = f"{name}: {total}h sur 7j glissants (S{start_week}J{start_day+1} -> S{end_week}J{end_day+1})"
                errors.append(msg)
                
    return errors
