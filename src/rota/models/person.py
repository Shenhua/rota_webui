"""Person model for team members."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Person:
    """Represents a team member with their scheduling constraints."""
    
    name: str
    workdays_per_week: int = 5
    weeks_pattern: int = 1  # Pattern cycle length
    
    # Shift preferences
    prefers_night: bool = False
    no_evening: bool = False
    max_nights: int = 99  # Over entire horizon
    
    # EDO (Earned Day Off)
    edo_eligible: bool = False
    edo_fixed_day: Optional[str] = None  # Preferred EDO day (Lun, Mar, etc.)
    
    # Team assignment
    team: str = ""
    
    # Weekend availability
    available_weekends: bool = True
    max_weekends_per_month: int = 2
    
    # External contractor status
    is_contractor: bool = False  # External contractors need tutoring (paired with regular)
    
    # Computed at runtime
    id: int = field(default=0, compare=False)

    def __post_init__(self):
        """Validate and normalize fields."""
        self.name = str(self.name).strip()
        if self.workdays_per_week < 1:
            self.workdays_per_week = 1
        if self.workdays_per_week > 7:
            self.workdays_per_week = 7
        if self.weeks_pattern < 1:
            self.weeks_pattern = 1
        if self.max_nights < 0:
            self.max_nights = 99
        if self.edo_fixed_day:
            self.edo_fixed_day = self.edo_fixed_day.strip()
            if self.edo_fixed_day not in ("Lun", "Mar", "Mer", "Jeu", "Ven"):
                self.edo_fixed_day = None

    @property
    def cohort_id(self) -> str:
        """Cohort identifier for fairness grouping."""
        if self.team:
            return self.team
        return f"{self.workdays_per_week}j"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "workdays_per_week": self.workdays_per_week,
            "weeks_pattern": self.weeks_pattern,
            "prefers_night": self.prefers_night,
            "no_evening": self.no_evening,
            "max_nights": self.max_nights,
            "edo_eligible": self.edo_eligible,
            "edo_fixed_day": self.edo_fixed_day,
            "team": self.team,
            "available_weekends": self.available_weekends,
            "max_weekends_per_month": self.max_weekends_per_month,
            "is_contractor": self.is_contractor,
        }


    @classmethod
    def from_dict(cls, d: dict) -> "Person":
        """Create from dictionary."""
        return cls(
            name=d.get("name", ""),
            workdays_per_week=int(d.get("workdays_per_week", 5)),
            weeks_pattern=int(d.get("weeks_pattern", 1)),
            prefers_night=bool(d.get("prefers_night", False)),
            no_evening=bool(d.get("no_evening", False)),
            max_nights=int(d.get("max_nights", 99)),
            edo_eligible=bool(d.get("edo_eligible", False)),
            edo_fixed_day=d.get("edo_fixed_day"),
            team=str(d.get("team", "")),
            available_weekends=bool(d.get("available_weekends", True)),
            max_weekends_per_month=int(d.get("max_weekends_per_month", 2)),
            is_contractor=bool(d.get("is_contractor", False)),
        )
