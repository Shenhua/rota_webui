#!/usr/bin/env python3
"""
Standalone test script to debug weekend solver.
Run this outside of Streamlit to isolate the issue.
"""
import sys
sys.path.insert(0, '/Users/mperrier/rota_refactor/src')
sys.path.insert(0, '/Users/mperrier/rota_refactor')

from rota.models.person import Person
from rota.solver.weekend import WeekendConfig, WeekendSolver

def create_test_people(count=5):
    """Create simple test people."""
    people = []
    for i in range(count):
        p = Person(
            id=i+1,
            name=f"Person_{i+1}",
            workdays_per_week=5,
            available_weekends=True
        )
        people.append(p)
    return people

def test_minimal_solver():
    """Test with absolute minimal configuration."""
    print("=" * 60)
    print("WEEKEND SOLVER DEBUG TEST")
    print("=" * 60)
    
    # Create minimal config
    config = WeekendConfig(
        num_weeks=4,  # Just 4 weeks
        staff_per_shift=2,
        time_limit_seconds=30,
        max_weekends_per_month=2
    )
    
    # Create simple people
    people = create_test_people(5)
    
    print(f"\nConfig: num_weeks={config.num_weeks}, staff_per_shift={config.staff_per_shift}")
    print(f"People: {len(people)} (all available_weekends=True)")
    
    # Run solver
    solver = WeekendSolver(config=config, people=people)
    
    print(f"\nSolver initialized:")
    print(f"  - self.people: {len(solver.people)} eligible")
    print(f"  - self.days: {solver.days}")
    print(f"  - self.shifts: {solver.shifts}")
    print(f"  - Expected variables: {len(solver.people)} × {config.num_weeks} × 2 × 2 = {len(solver.people) * config.num_weeks * 4}")
    
    result = solver.solve()
    
    print(f"\n--- RESULT ---")
    print(f"Status: {result.status}")
    print(f"Assignments: {len(result.assignments)}")
    print(f"Solve Time: {result.solve_time:.3f}s")
    print(f"Message: {result.message}")
    
    if result.assignments:
        print(f"\nFirst 10 assignments:")
        for a in result.assignments[:10]:
            print(f"  - Week {a.week}, {a.day}, Shift {a.shift}: {a.person.name}")
    else:
        print("\n⚠️ NO ASSIGNMENTS!")
        
        # Check solver internals
        print("\n--- DEBUGGING ---")
        if hasattr(solver, 'vars'):
            print(f"Variables created: {len(solver.vars)}")
        if hasattr(solver, 'total_deficits'):
            print(f"Deficit vars: {len(solver.total_deficits)}")
            
    return result

if __name__ == "__main__":
    result = test_minimal_solver()
    print("\n" + "=" * 60)
    if result.status == "OPTIMAL" and len(result.assignments) == 0:
        print("DIAGNOSIS: Solver found OPTIMAL with 0 assignments.")
        print("This means the objective function is NOT penalizing empty solution.")
    elif result.status == "INFEASIBLE":
        print("DIAGNOSIS: Solver found INFEASIBLE.")
        print("This means hard constraints are conflicting.")
    elif len(result.assignments) > 0:
        print(f"SUCCESS: Solver created {len(result.assignments)} assignments!")
