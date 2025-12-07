"""Consolidated normalization utilities for data handling."""
from typing import List, Optional
import pandas as pd

from rota.models.shift import ShiftType, normalize_day as _normalize_day, DAY_ALIASES


def normalize_day(val: str) -> str:
    """Normalize day string to canonical format (Lun, Mar, etc.)."""
    return _normalize_day(val)


def normalize_shift(val: str) -> str:
    """Normalize shift string to canonical format (J, S, N, A, OFF, EDO)."""
    return ShiftType.from_string(val).value


def normalize_assignments(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize assignment DataFrame to canonical format.
    
    Returns DataFrame with columns: ['name', 'week', 'day', 'shift']
    Handles various input formats (wide/long, different column names).
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["name", "week", "day", "shift"])
    
    d = df.copy()
    
    # Standardize column names (case/space tolerant)
    colmap = {c.lower().strip(): c for c in d.columns}
    
    def pick(*candidates):
        for c in candidates:
            if c in colmap:
                return colmap[c]
        return None
    
    c_name = pick("name", "person", "employee", "nom", "pers_a")
    c_week = pick("week", "semaine")
    c_day = pick("day", "jour")
    c_shift = pick("shift", "poste", "service")
    
    # If all columns found, use them directly
    if all(x is not None for x in [c_name, c_week, c_day, c_shift]):
        out = d[[c_name, c_week, c_day, c_shift]].rename(columns={
            c_name: "name", c_week: "week", c_day: "day", c_shift: "shift"
        })
    else:
        # Try to detect wide format (person columns)
        # Look for columns that might be person names (not week/day/shift)
        base_cols = {c_week, c_day, c_shift} - {None}
        other_cols = [c for c in d.columns if c not in base_cols]
        
        if len(base_cols) >= 2 and other_cols:
            # Use first other column as name source
            tmp_val = "_val"
            long = d.melt(
                id_vars=list(base_cols),
                value_vars=[other_cols[0]],
                var_name="slot",
                value_name=tmp_val
            )
            long = long.dropna(subset=[tmp_val]).rename(columns={tmp_val: "name"})
            rename_map = {}
            if c_week: rename_map[c_week] = "week"
            if c_day: rename_map[c_day] = "day"
            if c_shift: rename_map[c_shift] = "shift"
            out = long.rename(columns=rename_map)
        else:
            # Give up: return empty canonical frame
            return pd.DataFrame(columns=["name", "week", "day", "shift"])
    
    # Ensure required columns exist
    for col in ["name", "week", "day", "shift"]:
        if col not in out.columns:
            if col == "week":
                out[col] = 1
            else:
                out[col] = ""
    
    # Normalize types and values
    out["week"] = pd.to_numeric(out["week"], errors="coerce").fillna(1).astype(int)
    out["day"] = out["day"].apply(lambda x: normalize_day(str(x)))
    out["shift"] = out["shift"].apply(lambda x: normalize_shift(str(x)))
    out["name"] = out["name"].astype(str).str.strip()
    
    return out[["name", "week", "day", "shift"]]


def apply_edo_policy(df: pd.DataFrame, allow_edo: bool = True) -> pd.DataFrame:
    """If EDO disabled, reclassify EDO → OFF."""
    if df is None or df.empty or allow_edo:
        return df
    out = df.copy()
    if "shift" in out.columns:
        out.loc[out["shift"] == "EDO", "shift"] = "OFF"
    return out
