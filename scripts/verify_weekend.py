"""
Verify Weekend Solver Constraints
================================
This script tests the weekend solver against hard constraints and fairness.

Scenarios:
1. Normal Load: Standard team, ensuring valid schedule.
2. Stress Test: Reduced workforce, ensuring coverage still met or infeasibility reported correctly.
3. Constraint Check: Verify 24h limit and rest rules (Sat N -> Sun D forbidden).
"""

import sys
import os
from pathlib import Path
from typing import List

# Add src to python path
sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from rota.models.person import Person
from rota.solver.weekend import WeekendSolver, WeekendConfig, WeekendResult
from rota.utils.logging_setup import init_logging, get_logger
import logging

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("verify_weekend")

def create_team(size: int = 10, eligible_ratio: float = 1.0) -> List[Person]:
    """Create a test team."""
    people = []
    for i in range(size):
        is_eligible = i < (size * eligible_ratio)
        people.append(Person(
            name=f"P{i}", 
            id=i, 
            available_weekends=is_eligible,
            max_weekends_per_month=4 # Allow high availability for testing
        ))
    return people

def verify_constraints(result: WeekendResult, config: WeekendConfig) -> List[str]:
    """Check constraints on the result."""
    violations = []
    
    if result.status not in ["OPTIMAL", "FEASIBLE"]:
        return [f"Solver failed with status {result.status}"]
        
    shifts = result.assignments
    
    # 1. Coverage
    for w in range(1, config.num_weeks + 1):
        for d in ["Sat", "Sun"]:
            for s in ["D", "N"]:
                count = sum(1 for a in shifts if a.week == w and a.day == d and a.shift == s)
                if count != config.staff_per_shift:
                    violations.append(f"Coverage fail W{w} {d} {s}: got {count}, needed {config.staff_per_shift}")

    # 2. Max 24h per weekend (2 shifts max per person per weekend)
    # AND 3. Rest: Sat N -> Sun D forbidden
    
    # Group by person per week
    person_week_shifts = {} # (person, week) -> list of (day, shift)
    for a in shifts:
        key = (a.person.name, a.week)
        if key not in person_week_shifts:
            person_week_shifts[key] = []
        person_week_shifts[key].append((a.day, a.shift))
        
    for (name, w), p_shifts in person_week_shifts.items():
        # Check max 2 shifts
        if len(p_shifts) > 2:
            violations.append(f"Max 24h fail: {name} W{w} has {len(p_shifts)} shifts")
            
        # Check Sat N -> Sun D
        has_sat_n = ("Sat", "N") in p_shifts
        has_sun_d = ("Sun", "D") in p_shifts
        if has_sat_n and has_sun_d:
            violations.append(f"Rest fail: {name} W{w} works Sat Night AND Sun Day")

    return violations

def run_test(name: str, team_size: int, weeks: int = 2):
    """Run a single test scenario."""
    logger.info(f"=== Running Test: {name} ===")
    
    people = create_team(size=team_size)
    config = WeekendConfig(
        num_weeks=weeks, 
        staff_per_shift=2, # Needs 4 people per day -> 8 slots/weekend
        time_limit_seconds=5
    )
    
    # Needs: 8 slots * weeks. 
    # Capacity: team_size * 2 slots/weekend (max).
    # If team_size=4 => capacity 8 slots. Should pass narrowly.
    
    solver = WeekendSolver(config, people)
    result = solver.solve()
    
    logger.info(f"Status: {result.status}, Time: {result.solve_time:.2f}s")
    
    violations = verify_constraints(result, config)
    if violations:
        logger.error(f"❌ VIOLATIONS FOUND ({len(violations)}):")
        for v in violations:
            logger.error(f"  - {v}")
    else:
        logger.info("✅ No constraint violations found.")
        
    # Fairness stats
    if result.assignments:
        counts = {}
        for a in result.assignments:
            counts[a.person.name] = counts.get(a.person.name, 0) + 1
        values = list(counts.values())
        if values:
            min_s, max_s = min(values), max(values)
            logger.info(f"Fairness Spread: {min_s} - {max_s} shifts (Δ={max_s - min_s})")
    
    return len(violations) == 0

if __name__ == "__main__":
    init_logging()
    
    success = True
    
    # Test 1: Comfortable margins
    # Needs 8 slots/weekend. 10 people = 20 slots cap. Easy.
    if not run_test("Normal Load (10 people)", team_size=10):
        success = False
        
    # Test 2: Tight verification
    # Needs 8 slots/weekend. 4 people = 8 slots cap. MUST use everyone max potential.
    if not run_test("Tight Load (4 people)", team_size=4):
        success = False
        
    # Test 3: Infeasible
    # Needs 8 slots/weekend. 3 people = 6 slots cap. MUST fail.
    logger.info("=== Running Test: Infeasible (3 people) ===")
    people = create_team(3)
    config = WeekendConfig(num_weeks=1, staff_per_shift=2)
    solver = WeekendSolver(config, people)
    result = solver.solve()
    if result.status == "INFEASIBLE":
        logger.info("✅ Correctly identified INFEASIBLE")
    else:
        logger.error(f"❌ Expected INFEASIBLE, got {result.status}")
        success = False
        
    sys.exit(0 if success else 1)
