"""
Integration tests for Weekend and Weekday solvers with realistic team configurations.
Tests multiple scenarios and validates results against expected behavior.
"""
import sys
sys.path.insert(0, 'src')

from rota.solver.weekend import WeekendSolver, WeekendConfig, validate_weekend_schedule
from rota.models.person import Person
from dataclasses import dataclass
from typing import List, Dict
import json


@dataclass
class TestScenario:
    """Defines a test scenario with expected outcomes."""
    name: str
    people: List[Person]
    num_weeks: int
    expected_status: str  # "OPTIMAL", "FEASIBLE", or "INFEASIBLE"
    min_coverage_pct: float  # Minimum expected coverage (0.0-1.0)
    notes: str = ""


def create_team(size: int, workdays: int = 5, weekend_eligible: bool = True) -> List[Person]:
    """Helper to create a team of agents."""
    people = []
    for i in range(size):
        p = Person(
            name=f"Agent_{i:02d}",
            workdays_per_week=workdays,
            available_weekends=weekend_eligible
        )
        p.id = i
        people.append(p)
    return people


def create_mixed_team() -> List[Person]:
    """Create a realistic mixed team with varied constraints."""
    people = []
    
    # Full-time agents (5 days, weekend eligible)
    for i in range(10):
        p = Person(name=f"FT_{i:02d}", workdays_per_week=5, available_weekends=True)
        p.id = i
        people.append(p)
    
    # Part-time agents (3 days, weekend eligible)
    for i in range(4):
        p = Person(name=f"PT_{i:02d}", workdays_per_week=3, available_weekends=True)
        p.id = 10 + i
        people.append(p)
    
    # No-weekend agents (5 days, NOT weekend eligible)
    for i in range(2):
        p = Person(name=f"NW_{i:02d}", workdays_per_week=5, available_weekends=False)
        p.id = 14 + i
        people.append(p)
    
    return people


def run_weekend_scenario(scenario: TestScenario) -> Dict:
    """Run a weekend solver scenario and return results."""
    config = WeekendConfig(
        num_weeks=scenario.num_weeks,
        staff_per_shift=2,
        max_weekends_per_month=2,
        forbid_consecutive_nights=True,
        time_limit_seconds=15
    )
    
    solver = WeekendSolver(config, scenario.people)
    result = solver.solve()
    
    # Calculate coverage
    total_slots = scenario.num_weeks * 2 * 2 * 2  # weeks * days * shifts * staff_per_shift
    actual_assignments = len(result.assignments)
    coverage = actual_assignments / total_slots if total_slots > 0 else 0
    
    # Validate schedule
    validation = validate_weekend_schedule(result, scenario.people, scenario.num_weeks)
    
    return {
        "scenario": scenario.name,
        "status": result.status,
        "expected_status": scenario.expected_status,
        "status_ok": result.status == scenario.expected_status or (
            scenario.expected_status in ["OPTIMAL", "FEASIBLE"] and result.status in ["OPTIMAL", "FEASIBLE"]
        ),
        "assignments": actual_assignments,
        "total_slots": total_slots,
        "coverage_pct": round(coverage * 100, 1),
        "min_coverage_pct": scenario.min_coverage_pct * 100,
        "coverage_ok": coverage >= scenario.min_coverage_pct,
        "unused_agents": len(validation.unused_agents),
        "consecutive_3plus": len(validation.consecutive_3_plus),
        "solve_time": round(result.solve_time, 2),
        "notes": scenario.notes
    }


def print_result(result: Dict):
    """Pretty print a test result."""
    status_icon = "✅" if result["status_ok"] and result["coverage_ok"] else "❌"
    print(f"\n{status_icon} **{result['scenario']}**")
    print(f"   Status: {result['status']} (expected: {result['expected_status']}) {'✓' if result['status_ok'] else '✗'}")
    print(f"   Coverage: {result['coverage_pct']}% ({result['assignments']}/{result['total_slots']} slots) {'✓' if result['coverage_ok'] else '✗'}")
    print(f"   Unused Agents: {result['unused_agents']}")
    print(f"   3+ Consecutive Weekends: {result['consecutive_3plus']}")
    print(f"   Solve Time: {result['solve_time']}s")
    if result['notes']:
        print(f"   Notes: {result['notes']}")


def main():
    print("=" * 60)
    print("ROTA INTEGRATION TESTS")
    print("=" * 60)
    
    # Define test scenarios
    scenarios = [
        TestScenario(
            name="Scenario 1: Ideal Team (16 agents, 12 weeks)",
            people=create_team(16, workdays=5),
            num_weeks=12,
            expected_status="OPTIMAL",
            min_coverage_pct=1.0,
            notes="Standard team, should achieve 100% coverage."
        ),
        TestScenario(
            name="Scenario 2: Small Team (8 agents, 8 weeks)",
            people=create_team(8, workdays=5),
            num_weeks=8,
            expected_status="OPTIMAL",
            min_coverage_pct=1.0,
            notes="Smaller team, fewer weeks. Should still achieve full coverage."
        ),
        TestScenario(
            name="Scenario 3: Understaffed (4 agents, 12 weeks)",
            people=create_team(4, workdays=5),
            num_weeks=12,
            expected_status="OPTIMAL",  # Soft constraints allow partial
            min_coverage_pct=0.5,  # At least 50% coverage expected
            notes="Too few agents. Solver should produce partial schedule with deficits."
        ),
        TestScenario(
            name="Scenario 4: Mixed Team (16 agents, various constraints)",
            people=create_mixed_team(),
            num_weeks=12,
            expected_status="OPTIMAL",
            min_coverage_pct=1.0,
            notes="Mixed full-time, part-time, no-weekend agents."
        ),
        TestScenario(
            name="Scenario 5: Part-Time Only (12 agents, 3 days/week)",
            people=create_team(12, workdays=3),
            num_weeks=8,
            expected_status="OPTIMAL",
            min_coverage_pct=1.0,
            notes="All part-time agents. Should still cover weekends."
        ),
        TestScenario(
            name="Scenario 6: Single Weekend (16 agents, 1 week)",
            people=create_team(16, workdays=5),
            num_weeks=1,
            expected_status="OPTIMAL",
            min_coverage_pct=1.0,
            notes="Edge case: minimum duration."
        ),
        TestScenario(
            name="Scenario 7: Very Long Horizon (16 agents, 24 weeks)",
            people=create_team(16, workdays=5),
            num_weeks=24,
            expected_status="OPTIMAL",
            min_coverage_pct=1.0,
            notes="Stress test: 6 months of scheduling."
        ),
    ]
    
    # Run all scenarios
    results = []
    for scenario in scenarios:
        print(f"\nRunning: {scenario.name}...")
        result = run_weekend_scenario(scenario)
        results.append(result)
        print_result(result)
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for r in results if r["status_ok"] and r["coverage_ok"])
    total = len(results)
    
    print(f"\nTests Passed: {passed}/{total}")
    
    if passed == total:
        print("\n✅ ALL TESTS PASSED")
    else:
        print("\n❌ SOME TESTS FAILED")
        for r in results:
            if not (r["status_ok"] and r["coverage_ok"]):
                print(f"   - {r['scenario']}")
    
    # Export results to JSON
    with open("tests/integration_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to tests/integration_results.json")
    
    return 0 if passed == total else 1


if __name__ == "__main__":
    exit(main())
