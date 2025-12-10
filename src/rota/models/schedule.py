"""Schedule and assignment models."""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

from .shift import ShiftType, normalize_day


@dataclass
class Assignment:
    """A single shift assignment."""
    person_name: str
    week: int
    day: str
    shift: ShiftType
    
    def __post_init__(self):
        self.day = normalize_day(self.day)
        if isinstance(self.shift, str):
            self.shift = ShiftType.from_string(self.shift)


@dataclass
class Schedule:
    """Complete schedule result from the solver."""
    
    assignments: List[Assignment] = field(default_factory=list)
    weeks: int = 0
    people_count: int = 0
    
    # Solver metrics
    score: float = 0.0
    solve_time_seconds: float = 0.0
    status: str = "unknown"  # optimal, feasible, infeasible
    
    # Validation metrics
    violations: Dict[str, int] = field(default_factory=dict)
    fairness_metrics: Dict[str, float] = field(default_factory=dict)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert assignments to a DataFrame."""
        if not self.assignments:
            return pd.DataFrame(columns=["name", "week", "day", "shift"])
        
        rows = [
            {
                "name": a.person_name,
                "week": a.week,
                "day": a.day,
                "shift": a.shift.value if isinstance(a.shift, ShiftType) else a.shift,
            }
            for a in self.assignments
        ]
        return pd.DataFrame(rows)

    def to_matrix(self, days: Optional[List[str]] = None) -> pd.DataFrame:
        """Convert to person × (week, day) matrix format."""
        df = self.to_dataframe()
        if df.empty:
            return pd.DataFrame()
        
        if days:
            df = df[df["day"].isin(days)]
        
        piv = df.pivot_table(
            index="name",
            columns=["week", "day"],
            values="shift",
            aggfunc=lambda x: "/".join(sorted(set(str(v) for v in x))),
            fill_value=""
        )
        return piv

    def summary(self) -> Dict[str, Any]:
        """Get summary dictionary for display."""
        return {
            "weeks": self.weeks,
            "people": self.people_count,
            "score": round(self.score, 2),
            "status": self.status,
            "solve_time": round(self.solve_time_seconds, 2),
            "violations": self.violations,
            "fairness": self.fairness_metrics,
        }

    def get_person_stats(self) -> pd.DataFrame:
        """Get per-person statistics."""
        df = self.to_dataframe()
        if df.empty:
            return pd.DataFrame(columns=["name", "J", "S", "N", "A", "OFF", "EDO", "total_work"])
        
        stats = df.groupby("name")["shift"].value_counts().unstack(fill_value=0)
        for col in ["J", "S", "N", "A", "OFF", "EDO"]:
            if col not in stats.columns:
                stats[col] = 0
        
        stats["total_work"] = stats[["J", "S", "N"]].sum(axis=1)
        stats["rest_days"] = stats[["OFF", "EDO"]].sum(axis=1)
        return stats.reset_index()
