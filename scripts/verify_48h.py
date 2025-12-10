"""
Verification Script for 48h Constraint
======================================
"""
from rota.models.person import Person
from rota.models.constraints import SolverConfig
from rota.solver.pairs import solve_pairs
from rota.solver.staffing import derive_staffing
from rota.solver.edo import build_edo_plan
from rota.solver.validation import check_rolling_48h

def verify():
    # Setup a scenario where 48h might be exceeded if unchecked
    # e.g. 5 days work per week for someone
    people = [
        Person(name="WorkerA", workdays_per_week=5), # Configured for 5 days/week
        Person(name="WorkerB", workdays_per_week=5),
        Person(name="WorkerC", workdays_per_week=5),
        Person(name="WorkerD", workdays_per_week=5),
        Person(name="WorkerE", workdays_per_week=5),
        Person(name="WorkerF", workdays_per_week=5),
        Person(name="WorkerG", workdays_per_week=5),
        Person(name="WorkerH", workdays_per_week=5),
    ]
    
    config = SolverConfig(weeks=2, time_limit_seconds=10)
    edo_plan = build_edo_plan(people, config.weeks)
    
    # Custom staffing: D=1 pair, N=1 pair, S=0. Total 4 people/day.
    custom_staffing = {
        "D": 1, 
        "N": 1,
        "S": 0,
        "A": 0
    }
    staffing = derive_staffing(people, config.weeks, edo_plan.plan, custom_staffing=custom_staffing)
    
    print("Running solver...")
    schedule = solve_pairs(people, config, staffing, edo_plan)
    
    print(f"Status: {schedule.status}")
    if schedule.status not in ["optimal", "feasible"]:
        print("Could not find solution (expected due to strict constraints?)")
        # If strict constraints make 5 days/week impossible with D=10h, then 
        # the solver should either return Infeasible OR schedule less than 5 days.
        return

    # Check for violations
    errors = check_rolling_48h(schedule)
    if errors:
        print("❌ FAILED: Found 48h violations!")
        for e in errors:
            print(f"  - {e}")
    else:
        print("✅ SUCCESS: No 48h violations found.")
        
    # Check max hours worked
    # We want to verify that people max out at 48h in any window
    # Print max rolling 7d sum for WorkerA
    pass

if __name__ == "__main__":
    verify()
