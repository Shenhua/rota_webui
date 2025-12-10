
from __future__ import annotations

import pandas as pd

DAYS7 = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
DAYS5 = ["Lun","Mar","Mer","Jeu","Ven"]

_DAY_MAP = {
    "lun":"Lun","lundi":"Lun","mon":"Lun","monday":"Lun",
    "mar":"Mar","mardi":"Mar","tue":"Mar","tuesday":"Mar",
    "mer":"Mer","mercredi":"Mer","wed":"Mer","wednesday":"Mer",
    "jeu":"Jeu","jeudi":"Jeu","thu":"Jeu","thursday":"Jeu",
    "ven":"Ven","vendredi":"Ven","fri":"Ven","friday":"Ven",
    "sam":"Sam","samedi":"Sam","sat":"Sam","saturday":"Sam",
    "dim":"Dim","dimanche":"Dim","sun":"Dim","sunday":"Dim",
}

_SHIFT_MAP = {
    "d":"J","jour":"J","day":"J","j":"J",
    "e":"S","soir":"S","evening":"S","s":"S",
    "n":"N","nuit":"N","night":"N",
    "a":"A","admin":"A","abs":"A",
    "off":"OFF","repos":"OFF","offday":"OFF","o":"OFF",
    "edo":"EDO"
}

def _norm_day(val: str) -> str:
    s = str(val).strip()
    key = s.lower()
    return _DAY_MAP.get(key, s)

def _norm_shift(val: str) -> str:
    s = str(val).strip()
    key = s.lower()
    return _SHIFT_MAP.get(key, s)

def normalize_assignments_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Return canonical columns: ['name','week','day','shift'].
    Supports 'long' (already has 'name') and simple 'wide' layouts.
    Includes OFF and EDO normalization.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["name","week","day","shift"])

    d = df.copy()
    # Standardize common column names (case/space tolerant)
    colmap = {c.lower().strip(): c for c in d.columns}
    def pick(*cands):
        for c in cands:
            if c in colmap:
                return colmap[c]
        return None

    c_name = pick("name","person","employee")
    c_week = pick("week","semaine")
    c_day  = pick("day","jour")
    c_shift= pick("shift","poste","service","team")

    if all(x is not None for x in [c_name,c_week,c_day,c_shift]):
        out = d[[c_name,c_week,c_day,c_shift]].rename(columns={c_name:"name",c_week:"week",c_day:"day",c_shift:"shift"})
    else:
        # Fallback: assume columns include week/day/shift and one person column
        base_cols = [c for c in [c_week,c_day,c_shift] if c is not None]
        if len(base_cols) >= 2:
            other_cols = [c for c in d.columns if c not in base_cols]
            if other_cols:
                # Melt on the first non-base column as 'name'
                tmp_val = "_val"
                long = d.melt(id_vars=base_cols, value_vars=[other_cols[0]], var_name="slot", value_name=tmp_val)
                long = long.dropna(subset=[tmp_val]).rename(columns={tmp_val:"name"})
                out = long.rename(columns={c_week:"week", c_day:"day", c_shift:"shift"})
            else:
                # Construct synthetic names from index
                d = d.copy()
                d["name"] = d.index.astype(str)
                out = d.rename(columns={c_week:"week", c_day:"day", c_shift:"shift"})[["name","week","day","shift"]]
        else:
            # Give up: return empty canonical frame
            return pd.DataFrame(columns=["name","week","day","shift"])

    # Normalize types/values
    out["week"] = out["week"].astype(int)
    out["day"] = out["day"].apply(_norm_day)
    out["shift"] = out["shift"].apply(_norm_shift)
    out["name"] = out["name"].astype(str).str.strip()
    return out[["name","week","day","shift"]]
