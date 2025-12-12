"""
Business Rules and Constants
============================
Central source of truth for shift types, staffing defaults, and UI colors.
"""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class ShiftTypeConfig:
    code: str
    label: str
    color_bg: str
    color_text: str
    hours: int
    is_solo: bool

# Shift Definitions
SHIFTS = {
    "D": ShiftTypeConfig("D", "Jour", "#DDEEFF", "#333333", 10, False),
    "J": ShiftTypeConfig("J", "Jour", "#DDEEFF", "#333333", 10, False),  # Alias for D
    "N": ShiftTypeConfig("N", "Nuit", "#E6CCFF", "#333333", 12, False),
    "S": ShiftTypeConfig("S", "Soir", "#FFE4CC", "#333333", 10, True),
    "A": ShiftTypeConfig("A", "Admin", "#DDDDDD", "#333333", 8, True),
}

# Ordered list for UI
SHIFT_ORDER = ["D", "S", "N", "A"]

@dataclass
class RulesConfig:
    """Business rules constants."""
    
    # Staffing
    min_team_size_for_full_coverage: int = 8
    default_staffing: Dict[str, int] = field(default_factory=lambda: {
        "D": 4, 
        "S": 1, 
        "N": 1,
    })
    
    # Defaults
    default_weeks: int = 12
    default_tries: int = 2
    
    # Constraint Defaults
    default_max_consecutive_days: int = 6
    default_max_nights_sequence: int = 3
    
    # UI
    css_classes: Dict[str, str] = field(default_factory=lambda: {
        "D": "shift-J", # Mapping legacy CSS names
        "S": "shift-S",
        "N": "shift-N",
        "A": "shift-A"
    })

RULES = RulesConfig()
