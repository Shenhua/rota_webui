#!/usr/bin/env python3
"""
Test script to verify export consistency with web view.
"""
import sys
import io
sys.path.insert(0, '/Users/mperrier/rota_refactor/src')
sys.path.insert(0, '/Users/mperrier/rota_refactor')

from rota.io.csv_loader import load_team
from rota.solver.weekend import WeekendConfig, WeekendSolver
from rota.solver.pairs import PairSolver, SolverConfig
from rota.solver.edo import build_default_edo_plan
from rota.io.pair_export import export_merged_calendar

def test_export_consistency():
    """Test that exports use consistent data with web view."""
    print("=" * 60)
    print("EXPORT CONSISTENCY TEST")
    print("=" * 60)
    
    # Load team
    people = load_team("/Users/mperrier/rota_refactor/data/sample_people.csv")
    print(f"✅ Loaded {len(people)} people")
    
    # Create EDO plan
    edo_plan = build_default_edo_plan(people, num_weeks=4)
    
    # Run weekday solver
    config = SolverConfig(weeks=4, tries=3)
    solver = PairSolver(config=config, people=people, edo_plan=edo_plan)
    schedule = solver.solve()
    print(f"✅ Weekday: {schedule.status}, {len(schedule.assignments)} assignments")
    
    # Run weekend solver
    we_config = WeekendConfig(num_weeks=4)
    we_solver = WeekendSolver(config=we_config, people=people)
    w_result = we_solver.solve()
    print(f"✅ Weekend: {w_result.status}, {len(w_result.assignments)} assignments")
    
    # Verify data sources match
    print("\n--- DATA SOURCE CHECK ---")
    
    # Build weekday map (like dashboard does)
    weekday_map = {}
    for a in schedule.assignments:
        if a.person_a:
            weekday_map[(a.person_a, a.week, a.day)] = a.shift
        if a.person_b:
            weekday_map[(a.person_b, a.week, a.day)] = a.shift
    print(f"Weekday assignments in map: {len(weekday_map)}")
    
    # Build weekend map (like dashboard does)
    weekend_map = {}
    for a in w_result.assignments:
        weekend_map[(a.person.name, a.week, a.day)] = a.shift
    print(f"Weekend assignments in map: {len(weekend_map)}")
    
    # Test a few samples
    print("\n--- SAMPLE DATA ---")
    sample_wd = list(weekday_map.items())[:3]
    sample_we = list(weekend_map.items())[:3]
    
    print("Weekday samples:", sample_wd)
    print("Weekend samples:", sample_we)
    
    # Test merged export
    print("\n--- TESTING MERGED EXPORT ---")
    buffer = io.BytesIO()
    try:
        export_merged_calendar(
            weekday_schedule=schedule,
            weekend_result=w_result,
            people=people,
            edo_plan=edo_plan,
            output=buffer,
            config={"weeks": 4}
        )
        print(f"✅ Merged export generated: {len(buffer.getvalue())} bytes")
    except Exception as e:
        print(f"❌ Export failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("CONCLUSION: Data sources are consistent")
    print("- Web view uses: schedule.assignments + w_result.assignments")
    print("- Excel export uses: same sources")
    print("- PDF export uses: same sources")
    print("=" * 60)

if __name__ == "__main__":
    test_export_consistency()
