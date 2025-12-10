import pytest
from rota.models.person import Person
from rota.solver.weekend import WeekendSolver, WeekendConfig

def test_weekend_solver_basics():
    people = [
        Person(name=f"P{i}", id=i, available_weekends=True, max_weekends_per_month=4) 
        for i in range(10)
    ]
    
    config = WeekendConfig(num_weeks=2, staff_per_shift=2)
    solver = WeekendSolver(config, people)
    result = solver.solve()
    
    assert result.status in ["OPTIMAL", "FEASIBLE"]
    assert len(result.assignments) > 0
    
    # Check coverage - French day names
    assert sum(1 for a in result.assignments if a.week==1 and a.day=="Sam" and a.shift=="D") == 2
    assert sum(1 for a in result.assignments if a.week==1 and a.day=="Sam" and a.shift=="N") == 2

def test_max_24h_per_weekend():
    people = [Person(name=f"P{i}", id=i, available_weekends=True) for i in range(4)]
    config = WeekendConfig(num_weeks=1, staff_per_shift=2)
    solver = WeekendSolver(config, people)
    result = solver.solve()
    
    assert result.status in ["OPTIMAL", "FEASIBLE"]
    
    # Check each person has <= 2 shifts (max 24h)
    for p in people:
        shifts = [a for a in result.assignments if a.person.name == p.name]
        assert len(shifts) <= 2
        assert len(shifts) == 2  # Tight constraint with 4 people

def test_weekend_eligibility():
    p1 = Person(name="Eligible", id=1, available_weekends=True)
    p2 = Person(name="NotEligible", id=2, available_weekends=False)
    dummies = [Person(name=f"D{i}", id=10+i, available_weekends=True) for i in range(1)]
    
    people = [p1, p2] + dummies
    config = WeekendConfig(num_weeks=1, staff_per_shift=1)
    solver = WeekendSolver(config, people)
    result = solver.solve()
    
    assigned_names = set(a.person.name for a in result.assignments)
    assert "Eligible" in assigned_names

def test_repo_apres_nuit_weekend():
    """If working Sam Night, cannot work Dim Day."""
    people = [Person(name=f"P{i}", id=i, available_weekends=True) for i in range(4)]
    
    config = WeekendConfig(num_weeks=1, staff_per_shift=2)
    solver = WeekendSolver(config, people)
    result = solver.solve()
    
    assert result.status in ["OPTIMAL", "FEASIBLE"]
    
    for p in people:
        shifts = [a for a in result.assignments if a.person.name == p.name]
        has_sam_n = any(a.day == "Sam" and a.shift == "N" for a in shifts)
        has_dim_d = any(a.day == "Dim" and a.shift == "D" for a in shifts)
        if has_sam_n:
            assert not has_dim_d, f"Person {p.name} works Sam N and Dim D"

def test_12h_24h_tracking():
    """Test that 12h/24h shift types are correctly tracked."""
    people = [Person(name=f"P{i}", id=i, available_weekends=True) for i in range(4)]
    config = WeekendConfig(num_weeks=1, staff_per_shift=2)
    solver = WeekendSolver(config, people)
    result = solver.solve()
    
    assert result.status in ["OPTIMAL", "FEASIBLE"]
    
    # With 4 people and 8 slots, everyone should work 24h
    for p in people:
        shift_type = result.get_person_shift_type(p.name, 1)
        assert shift_type == "24h"
