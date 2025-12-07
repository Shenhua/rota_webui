
# src/rota/engine/targets.py
from typing import Dict, Any, List, Optional
import pandas as pd

SHIFT_ALIAS = {
    "j":"J","jour":"J","day":"J",
    "s":"S","soir":"S","evening":"S",
    "n":"N","nuit":"N","night":"N",
    "a":"A","admin":"A","abs":"A",
    "off":"OFF","repos":"OFF","o":"OFF","offday":"OFF",
    "edo":"EDO",
}

DAY_ALIAS = {
    "lun":"Lun","lundi":"Lun","mon":"Lun","monday":"Lun",
    "mar":"Mar","mardi":"Mar","tue":"Mar","tuesday":"Mar",
    "mer":"Mer","mercredi":"Mer","wed":"Mer","wednesday":"Mer",
    "jeu":"Jeu","jeudi":"Jeu","thu":"Jeu","thursday":"Jeu",
    "ven":"Ven","vendredi":"Ven","fri":"Ven","friday":"Ven",
    "sam":"Sam","samedi":"Sam","sat":"Sam","saturday":"Sam",
    "dim":"Dim","dimanche":"Dim","sun":"Dim","sunday":"Dim",
}

def _norm_shift(s: str) -> str:
    k = str(s).strip().lower()
    return SHIFT_ALIAS.get(k, str(s).strip())

def _norm_day(s: str) -> str:
    k = str(s).strip().lower()
    return DAY_ALIAS.get(k, str(s).strip())

def normalize_targets_payload(payload: Dict[str, Any] | None) -> pd.DataFrame:
    """Accepts different shapes (list-of-rows or nested dict) and returns canonical targets df."""
    if not payload:
        return pd.DataFrame(columns=["week","day","shift","required"])
    if isinstance(payload, dict) and "list" in payload and isinstance(payload["list"], list):
        rows = []
        for r in payload["list"]:
            if not isinstance(r, dict): 
                continue
            try:
                w = int(r.get("week", 1))
            except Exception:
                continue
            day = _norm_day(r.get("day","")) 
            sh = _norm_shift(r.get("shift","")) 
            req = int(r.get("required", 0))
            rows.append({"week": w, "day": day, "shift": sh, "required": req})
        return pd.DataFrame(rows, columns=["week","day","shift","required"])
    # Nested mapping: {week: {day: {shift: required}}}
    if isinstance(payload, dict):
        rows = []
        for wk, dmap in payload.items():
            try:
                w = int(wk)
            except Exception:
                continue
            if not isinstance(dmap, dict):
                continue
            for day, smap in dmap.items():
                if not isinstance(smap, dict):
                    continue
                for sh, req in smap.items():
                    rows.append({"week": w, "day": _norm_day(day), "shift": _norm_shift(sh), "required": int(req)})
        return pd.DataFrame(rows, columns=["week","day","shift","required"])
    return pd.DataFrame(columns=["week","day","shift","required"])

def apply_edo_policy(df: pd.DataFrame, allow_edo: bool) -> pd.DataFrame:
    if df is None or df.empty or allow_edo:
        return df
    d = df.copy()
    if "shift" in d.columns:
        d.loc[d["shift"]=="EDO", "shift"] = "OFF"
    return d

def coverage_from_assignments(assignments: pd.DataFrame, targets: pd.DataFrame, days: Optional[List[str]] = None) -> pd.DataFrame:
    if assignments is None or assignments.empty or targets is None or targets.empty:
        return pd.DataFrame()
    # Lazy import to avoid cycles
    from rota.ui.utils import normalize_assignments_columns
    a = normalize_assignments_columns(assignments)
    if days is not None:
        a = a[a["day"].isin(days)]
    counts = a.groupby(["week","day","shift"]).size().reset_index(name="assigned")
    merged = targets.merge(counts, on=["week","day","shift"], how="left").fillna({"assigned": 0})
    merged["gap"] = merged["assigned"].astype(int) - merged["required"].astype(int)
    return merged

def targets_penalty(coverage_df: pd.DataFrame, weights_by_shift: Dict[str, float], weight: float = 1.0) -> float:
    if coverage_df is None or coverage_df.empty:
        return 0.0
    pen = 0.0
    for _, r in coverage_df.iterrows():
        gap = int(r.get("gap", 0))
        if gap < 0:
            sh = str(r.get("shift","")) .upper()
            w = float(weights_by_shift.get(sh, 1.0))
            pen += (-gap) * w
    return pen * float(weight)
