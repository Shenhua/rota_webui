"""
Domain Package
==============
Re-exports business domain entities from models package.
This provides a cleaner namespace while maintaining backward compatibility.

Example usage:
    from rota.domain import Person, Schedule, Shift
    
Note: All original imports from rota.models.* still work.
"""
from rota.models.person import Person
from rota.models.schedule import Schedule, Assignment
from rota.models.shift import Shift, ShiftType
from rota.models.constraints import SolverConfig, FairnessMode
from rota.models.rules import SHIFTS, ShiftRules

__all__ = [
    # Entities
    "Person",
    "Schedule",
    "Assignment",
    "Shift",
    "ShiftType",
    
    # Configuration
    "SolverConfig",
    "FairnessMode",
    
    # Business rules
    "SHIFTS",
    "ShiftRules",
]
