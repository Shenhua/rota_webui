"""Tests for strict constraints, specifically the 48h rolling window."""
import pytest
from rota.models.schedule import Schedule, Assignment
from rota.models.shift import ShiftType
from rota.solver.validation import ValidationResult, validate_schedule
from rota.models.person import Person
# from rota.solver.edo import EdoPlan # Removed to avoid import error


def test_rolling_48h_validation_simple():
    """
    Test 48h rolling window validation.
    Scenario: Person works 5 Days (10h each) in a row = 50h.
    Window size: 7 days.
    """
    # Create valid assignments for 5 consecutive days
    # Days 1-5: Day shift (10h) => 50h in 7 days window [1-7]
    assignments = []
    person_name = "Alice"
    
    # 5 consecutive days (Mon-Fri)
    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    for d in days:
        assignments.append(Assignment(person_name, 1, d, ShiftType.DAY))
        
    schedule = Schedule(assignments=assignments, weeks=1, people_count=1, status="feasible")
    
    # Dummy objects needed for validation
    people = [Person(name="Alice")]
    class MockEdoPlan:
        def __init__(self, plan): self.plan = plan
    edo_plan = MockEdoPlan({})
    staffing = {} # Not used for this check hopefully
    
    # We need to access the specific validation function or mock the full validation
    # For TDD, let's assume we'll add check_rolling_48h to validation module
    from rota.solver.validation import check_rolling_48h
    
    errors = check_rolling_48h(schedule)
    
    assert len(errors) == 1
    assert "Alice" in errors[0]
    assert "50h" in errors[0] # Expecting mention of 50h > 48h

def test_rolling_48h_validation_mixed_shifts():
    """
    Test mixed shifts: 2 Nights (12h) + 3 Days (10h) = 24 + 30 = 54h
    """
    assignments = []
    person_name = "Bob"
    
    # Mon, Tue: Night (12h)
    assignments.append(Assignment(person_name, 1, "Mon", ShiftType.NIGHT))
    assignments.append(Assignment(person_name, 1, "Tue", ShiftType.NIGHT))
    
    # Wed, Thu, Fri: Day (10h)
    assignments.append(Assignment(person_name, 1, "Wed", ShiftType.DAY))
    assignments.append(Assignment(person_name, 1, "Thu", ShiftType.DAY))
    assignments.append(Assignment(person_name, 1, "Fri", ShiftType.DAY))
    
    schedule = Schedule(assignments=assignments, weeks=1, people_count=1, status="feasible")
    
    from rota.solver.validation import check_rolling_48h
    errors = check_rolling_48h(schedule)
    
    assert len(errors) > 0
    assert "Bob" in errors[0]

def test_rolling_48h_valid_schedule():
    """
    Test a valid schedule: 4 Days (40h)
    """
    assignments = []
    person_name = "Charlie"
    
    assignments.append(Assignment(person_name, 1, "Mon", ShiftType.DAY))
    assignments.append(Assignment(person_name, 1, "Tue", ShiftType.DAY))
    assignments.append(Assignment(person_name, 1, "Wed", ShiftType.DAY))
    assignments.append(Assignment(person_name, 1, "Thu", ShiftType.DAY))
    
    schedule = Schedule(assignments=assignments, weeks=1, people_count=1, status="feasible")
    
    from rota.solver.validation import check_rolling_48h
    errors = check_rolling_48h(schedule)
    
    assert len(errors) == 0
