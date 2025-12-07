from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict
import pandas as pd

@dataclass
class SolveSummary:
    weeks: int
    people: int
    score: float | int = 0
    seed: int | None = None
    tries: int | None = None
    fairness_mode: str | None = None

@dataclass
class SolveMetrics:
    data: Dict[str, Any]

@dataclass
class SolveResult:
    assignments: pd.DataFrame
    summary: Dict[str, Any]
    metrics_json: Dict[str, Any]