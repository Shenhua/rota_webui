
from __future__ import annotations
from typing import Dict, List, Tuple
import pandas as pd

DAYS7 = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
SHIFTS_JSN = ["J","S","N"]                   # cibles du solveur
SHIFTS_ALL = ["J","S","N","A","OFF","EDO"]   # affichage complet

# --- Editeur (jours-type) ---
ALL_COLS = ["day","J","S","N","A","OFF","EDO"]

def default_targets_editor(days: List[str] | None = None) -> pd.DataFrame:
    days = days or DAYS7
    rows = [{"day": d, "J": 0, "S": 0, "N": 0, "A": 0, "OFF": 0, "EDO": 0} for d in days]
    return pd.DataFrame(rows, columns=ALL_COLS)

def yaml_to_editor(preset: dict, weeks: int, days: List[str]) -> pd.DataFrame:
    """Accepte:
    - {targets: {day: {J:1,S:2,N:0,...}}}
    - {weeks: {1: {day: {..}}, 2: {...}}}  -> réduit par max par jour/poste
    """
    vals = {d: {c:0 for c in ["J","S","N","A","OFF","EDO"]} for d in days}
    if not isinstance(preset, dict):
        return default_targets_editor(days)
    if "targets" in preset and isinstance(preset["targets"], dict):
        for d, m in preset["targets"].items():
            if d in vals and isinstance(m, dict):
                for k in vals[d].keys():
                    try: vals[d][k] = int(m.get(k, 0))
                    except Exception: pass
    elif "weeks" in preset and isinstance(preset["weeks"], dict):
        agg = {d: {k:0 for k in ["J","S","N","A","OFF","EDO"]} for d in days}
        for _, dmap in preset["weeks"].items():
            if not isinstance(dmap, dict): continue
            for d, m in dmap.items():
                if d in agg and isinstance(m, dict):
                    for k in agg[d].keys():
                        try:
                            agg[d][k] = max(int(agg[d][k]), int(m.get(k,0)))
                        except Exception:
                            pass
        vals = agg
    out = [{"day": d, **vals[d]} for d in days]
    return pd.DataFrame(out, columns=ALL_COLS)

def editor_to_nested(df: pd.DataFrame, weeks: int) -> Dict[int, Dict[str, Dict[str, int]]]:
    """Diffuse les minima par jour vers toutes les semaines; ne conserve que J/S/N pour le solveur."""
    if df is None or df.empty:
        return {}
    req_cols = {"day","J","S","N"}
    if not req_cols.issubset(set(df.columns)):
        cols = {str(c).strip().lower(): c for c in df.columns}
        day_col = cols.get("jour") or cols.get("day")
        if day_col and day_col != "day":
            df = df.rename(columns={day_col: "day"})
    nested: Dict[int, Dict[str, Dict[str, int]]] = {}
    for w in range(1, int(weeks)+1):
        nested[w] = {}
        for _, r in df.iterrows():
            d = str(r["day"])
            nested[w][d] = { s: int(r.get(s, 0)) for s in SHIFTS_JSN }
    return nested

# --- Comptes & couverture ---
def assignments_to_counts(assignments: pd.DataFrame, full: bool = False) -> pd.DataFrame:
    """Retourne colonnes: Semaine, Jour, Poste, Assignes.
    - full=False: uniquement J/S/N (pour couverture vs cibles)
    - full=True : toutes (J/S/N/A/OFF/EDO) pour l'affichage
    """
    if assignments is None or assignments.empty:
        return pd.DataFrame(columns=["Semaine","Jour","Poste","Assignes"])
    df = assignments.copy()
    allowed = SHIFTS_ALL if full else SHIFTS_JSN
    df = df[df["shift"].isin(allowed)]
    g = df.groupby(["week","day","shift"]).size().reset_index(name="Assignes")
    g = g.rename(columns={"week":"Semaine","day":"Jour","shift":"Poste"})
    return g

def coverage_join(nested_targets: Dict[int, Dict[str, Dict[str, int]]], counts_df: pd.DataFrame, include_extras: bool = False) -> pd.DataFrame:
    """Table: Semaine, Jour, Poste, Requis, Assignes, Ecart.
    - include_extras=True: inclut A/OFF/EDO avec Requis=0 (affichage uniquement).
    """
    rows = []
    # Cibles J/S/N
    for w, d_map in (nested_targets or {}).items():
        for d, s_map in d_map.items():
            for s, req in s_map.items():
                rows.append({"Semaine": int(w), "Jour": d, "Poste": s, "Requis": int(req)})
    # Extras pour affichage
    if include_extras:
        # Ajoute A/OFF/EDO lignes Requis=0 afin qu'elles apparaissent dans la jointure
        days = set(counts_df["Jour"]) if not counts_df.empty else set()
        weeks = set(counts_df["Semaine"]) if not counts_df.empty else set()
        for w in weeks or {1}:
            for d in days or set(DAYS7):
                for s in ["A","OFF","EDO"]:
                    rows.append({"Semaine": int(w), "Jour": d, "Poste": s, "Requis": 0})
    targ = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Semaine","Jour","Poste","Requis"])
    df = targ.merge(counts_df, how="left", on=["Semaine","Jour","Poste"]).fillna({"Assignes":0})
    df["Assignes"] = df["Assignes"].astype(int)
    df["Ecart"] = df["Assignes"] - df["Requis"]
    return df.sort_values(["Semaine","Jour","Poste"])

def compute_coverage_summary(cov: pd.DataFrame) -> Dict[str, int | float]:
    """Résumé simple sur J/S/N uniquement (là où Requis>0)."""
    if cov is None or cov.empty:
        return {"cells":0,"ok":0,"warn":0,"bad":0,"deficit_total":0}
    focus = cov[(cov["Poste"].isin(SHIFTS_JSN)) & (cov["Requis"] > 0)].copy()
    if focus.empty:
        return {"cells":0,"ok":0,"warn":0,"bad":0,"deficit_total":0}
    ok = int((focus["Ecart"] >= 0).sum())
    warn = int((focus["Ecart"] == -1).sum())
    bad = int((focus["Ecart"] <= -2).sum())
    cells = int(len(focus))
    deficit = int((focus["Requis"] - focus["Assignes"]).clip(lower=0).sum())
    return {"cells":cells,"ok":ok,"warn":warn,"bad":bad,"deficit_total":deficit}

# --- Styling helpers ---
COLOR_OK = "#e6f4ea"     # green-ish
COLOR_WARN = "#fff4e5"   # orange-ish
COLOR_BAD = "#fdecea"    # red-ish
COLOR_A = "#ede7f6"      # light violet
COLOR_OFF = "#f2f2f2"    # light grey
COLOR_EDO = "#e3f2fd"    # light blue

def style_rag_and_extras(df: pd.DataFrame, show_extras: bool = True):
    """Retourne un Styler: RAG sur Ecart pour J/S/N; teinte spécifique pour A/OFF/EDO."""
    def _bg_rag(val):
        try:
            v = int(val)
        except Exception:
            return ""
        if v >= 0: return f"background-color: {COLOR_OK}"
        if v == -1: return f"background-color: {COLOR_WARN}"
        return f"background-color: {COLOR_BAD}"

    styler = df.style
    # RAG sur Ecart (J/S/N uniquement)
    mask_jsn = df["Poste"].isin(SHIFTS_JSN)
    styler = styler.applymap(lambda v: _bg_rag(v), subset=pd.IndexSlice[mask_jsn, ["Ecart"]])

    if show_extras:
        # Teintes sur la colonne Poste (et Assignes) pour A/OFF/EDO
        def _bg_extras(col_name: str):
            colors = []
            for s in df["Poste"].astype(str):
                if s == "A": colors.append(f"background-color: {COLOR_A}")
                elif s == "OFF": colors.append(f"background-color: {COLOR_OFF}")
                elif s == "EDO": colors.append(f"background-color: {COLOR_EDO}")
                else: colors.append("" )
            return colors
        for col in ["Poste", "Assignes"]:
            if col in df.columns:
                styler = styler.apply(lambda _: _bg_extras(col), axis=0, subset=[col])
    return styler

# --- Back-compat aliases (imported by older UI code) ---
def editor_to_targets(df, weeks):
    # alias to the canonical function used by the engine
    return editor_to_nested(df, weeks)

def yaml_to_editor_targets(preset: dict, weeks: int, days: List[str]):
    # Some callers import this; forward to yaml_to_editor
    return yaml_to_editor(preset, weeks, days)

def yaml_to_editors(*args, **kwargs):
    # Very old alias observed in some branches
    return yaml_to_editor(*args, **kwargs)
