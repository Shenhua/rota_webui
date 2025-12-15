#!/usr/bin/env python3
"""
Debug script to test weekend solver with REAL team data from YAML file.
"""
import sys
sys.path.insert(0, '/Users/mperrier/rota_refactor/src')
sys.path.insert(0, '/Users/mperrier/rota_refactor')

from rota.io.csv_loader import load_team
from rota.solver.weekend import WeekendConfig, WeekendSolver

def test_with_real_team():
    """Test with the actual team Excel file."""
    print("=" * 60)
    print("WEEKEND SOLVER DEBUG - REAL TEAM DATA")
    print("=" * 60)
    
    # Load actual team data - try CSV/Excel
    team_file = "/Users/mperrier/rota_refactor/data/sample_people.csv"
    try:
        people = load_team(team_file)
        print(f"\n✅ Loaded {len(people)} people from {team_file}")
    except Exception as e:
        print(f"❌ Failed to load team: {e}")
        # Try csv
        team_file = "/Users/mperrier/rota_refactor/data/team.csv"
        try:
            people = load_team(team_file)
            print(f"\n✅ Loaded {len(people)} people from {team_file}")
        except Exception as e2:
            print(f"❌ Failed to load team from CSV: {e2}")
            return None
    
    # Check people attributes
    print("\n--- PEOPLE ATTRIBUTES ---")
    for i, p in enumerate(people[:5]):  # First 5 only
        print(f"  {i+1}. {p.name}:")
        print(f"      id={p.id}, workdays={p.workdays_per_week}")
        print(f"      available_weekends={getattr(p, 'available_weekends', 'MISSING')}")
    if len(people) > 5:
        print(f"  ... and {len(people)-5} more")
    
    # Check eligibility
    eligible = [p for p in people if getattr(p, 'available_weekends', True)]
    print(f"\n  Eligible: {len(eligible)} / {len(people)}")
    
    # Create config like Streamlit does
    config = WeekendConfig(
        num_weeks=12,  # Same as UI default
        staff_per_shift=2,
        max_weekends_per_month=2,
        forbid_consecutive_nights=True
    )
    
    print(f"\nConfig: num_weeks={config.num_weeks}, staff_per_shift={config.staff_per_shift}")
    
    # Run solver
    solver = WeekendSolver(config=config, people=people)
    
    print(f"\nSolver created:")
    print(f"  - self.people (eligible): {len(solver.people)}")
    print(f"  - Expected slots: {config.num_weeks} × 2 days × 2 shifts = {config.num_weeks * 4}")
    
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
        
    return result

if __name__ == "__main__":
    result = test_with_real_team()
    if result:
        print("\n" + "=" * 60)
        if result.status == "OPTIMAL" and len(result.assignments) == 0:
            print("DIAGNOSIS: Solver found OPTIMAL with 0 assignments.")
        elif result.status == "INFEASIBLE":
            print("DIAGNOSIS: Solver found INFEASIBLE.")
        elif len(result.assignments) > 0:
            print(f"SUCCESS: Solver created {len(result.assignments)} assignments!")
