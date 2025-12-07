
# src/rota/engine/config.py
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

@dataclass
class SolveConfig:
    # Core
    weeks: int = 4
    tries: int = 20
    seed: Optional[int] = None

    # Fairness & constraints (common)
    fairness_mode: str = "none"
    forbid_night_to_day: bool = True
    limit_evening_to_day: bool = False
    min_rest_after_night: int = 1
    max_evenings_seq: int = 3
    max_days_per_week: int = 5

    # Per-person typical fields (for legacy mapping)
    max_nights: int = 6
    prefers_night: bool = False
    no_evening: bool = False
    edo_eligible: bool = False
    edo_fixed_day: Optional[str] = None

    # Global policy
    allow_edo: bool = True

    # Service needs / coverage targets
    # The Streamlit app may fill any of these; overlay will normalize them.
    coverage_targets: Optional[Dict[str, Any]] = None
    targets: Optional[Dict[str, Any]] = None
    service_needs: Optional[Dict[str, Any]] = None
    impose_targets: bool = False  # if True, try to optimize considering target penalty
    targets_weight: float = 1.0   # global weight for deficits
    targets_weights_by_shift: Dict[str, float] = field(default_factory=lambda: {"J":1.0,"S":1.0,"N":1.5,"A":0.5,"OFF":0.0,"EDO":0.0})
    alpha: float = 1.0  # composite score weight for targets penalty

    # Misc passthrough
    extras: Dict[str, Any] = field(default_factory=dict)
