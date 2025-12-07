# streamlit_app.py (UI-only with safe CLI guard)
import io, json, zipfile, tempfile, os
from pathlib import Path
from typing import Optional, List, Dict, Tuple

import pandas as pd
import streamlit as st

import tempfile, os
def _persist_uploaded_csv(uploaded_file, default_name="assignments.csv"):
    """
    Persist Streamlit uploaded file-like object to a temp path and return the absolute path.
    If uploaded_file is None, returns None.
    """
    if uploaded_file is None:
        return None
    tmpdir = tempfile.mkdtemp(prefix="rota_ui_")
    out = os.path.join(tmpdir, default_name)
    uploaded_file.seek(0)
    with open(out, "wb") as f:
        f.write(uploaded_file.read())
    return out




from rota.ui.coverage import default_targets_editor, yaml_to_editor, editor_to_nested, assignments_to_counts, coverage_join, compute_coverage_summary, style_rag_and_extras

# Optional: align with upcoming pandas behavior to avoid fillna downcasting warnings
try:
    pd.set_option("future.no_silent_downcasting", True)
except Exception:
    pass

# Try to import engine (robust imports)
try:
    # Preferred: overlay solve (Option A)
    from rota.engine.targets_overlay import solve  # noqa: F401
except Exception:
    try:
        # Fallback: your legacy entrypoint if you import it elsewhere
        from rota.engine.solve import solve  # noqa: F401
    except Exception:
        # Last resort: direct legacy module
        from rota.legacy.legacy_v29 import solve  # noqa: F401

try:
    from rota.engine.config import SolveConfig  # provided by overlay (fallback) or your own
except Exception:
    SolveConfig = None

# ------------------ Helpers ------------------

_DAYS7 = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
_DAYS5 = ["Lun","Mar","Mer","Jeu","Ven"]

def days_for_calendar(mode: str) -> List[str]:
    return _DAYS7 if mode == "7 jours (Lun–Dim)" else _DAYS5

def normalize_assignments_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Robust normalizer that supports:
    - 'long' layout (already has a single 'name' column)
    - 'wide' layout (multiple person columns e.g. Pers_A, Pers_B)
    Returns a canonical schema: columns = ['name','week','day','shift'].
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=["name","week","day","shift"])

    df2 = df.copy()
    cols = {str(c).strip().lower(): c for c in df2.columns}

    def pick(candidates):
        for k in candidates:
            if k in cols:
                return cols[k]
        return None

    week_col  = pick(["semaine","week","wk"])     or "Semaine"
    day_col   = pick(["jour","day","weekday"])    or "Jour"
    shift_col = pick(["poste","shift","service","type","shift_name","assignment"]) or "Poste"

    # Standard rename for id vars if present
    ren = {}
    if week_col in df2.columns:  ren[week_col]  = "week"
    if day_col in df2.columns:   ren[day_col]   = "day"
    if shift_col in df2.columns: ren[shift_col] = "shift"
    if ren:
        df2 = df2.rename(columns=ren)

    has_name = "name" in df2.columns

    # Person columns for 'wide' layout
    person_cols = [
        c for c in df2.columns
        if c not in {"name", "week", "day", "shift"}
        and c.lower().startswith(("pers","person","nom","name"))
    ]

    if person_cols and not has_name:
        # WIDE → LONG (avoid value_name='name' collision)
        tmp_value = "__person_value__"
        long = df2.melt(
            id_vars=[v for v in ["week","day","shift"] if v in df2.columns],
            value_vars=person_cols,
            var_name="slot",
            value_name=tmp_value,
        )
        long = long.dropna(subset=[tmp_value])
        long = long.rename(columns={tmp_value: "name"})
    else:
        # Already LONG (or at least has a usable name-like column)
        if not has_name:
            # Promote a person-like column if any
            if person_cols:
                df2 = df2.rename(columns={person_cols[0]: "name"})
            else:
                df2["name"] = df2.index.astype(str)
        # Keep canonical subset, fill missing
        cols_keep = [c for c in ["name","week","day","shift"] if c in df2.columns]
        long = df2[cols_keep].copy()
        for miss in ["week","day","shift"]:
            if miss not in long.columns:
                long[miss] = "" if miss != "week" else 0

    # Types & normalization
    long["week"] = pd.to_numeric(long["week"], errors="coerce").fillna(0).astype(int)

    day_map = {
        "mon":"Lun","monday":"Lun","lun":"Lun","lundi":"Lun","1":"Lun","0":"Lun",
        "tue":"Mar","tuesday":"Mar","mar":"Mar","mardi":"Mar","2":"Mar",
        "wed":"Mer","wednesday":"Mer","mer":"Mer","mercredi":"Mer","3":"Mer",
        "thu":"Jeu","thursday":"Jeu","jeu":"Jeu","jeudi":"Jeu","4":"Jeu",
        "fri":"Ven","friday":"Ven","ven":"Ven","vendredi":"Ven","5":"Ven",
        "sat":"Sam","saturday":"Sam","sam":"Sam","samedi":"Sam","6":"Sam",
        "sun":"Dim","sunday":"Dim","dim":"Dim","dimanche":"Dim","7":"Dim",
    }
    long["day"] = long["day"].astype(str).str.strip()
    long["_day_key"] = long["day"].str.lower()
    long["day"] = long["_day_key"].map(day_map).fillna(long["day"])
    long.drop(columns=["_day_key"], inplace=True, errors="ignore")

    # Shifts: include OFF and EDO explicitly
    shift_map = {
        "d":"J","jour":"J","day":"J","j":"J",
        "e":"S","soir":"S","evening":"S","s":"S",
        "n":"N","nuit":"N","night":"N",
        "a":"A","admin":"A","abs":"A",
        "off":"OFF","repos":"OFF","offday":"OFF","o":"OFF",
        "edo":"EDO"
    }
    long["shift"] = long["shift"].astype(str).str.strip()
    long["_shift_key"] = long["shift"].str.lower()
    long["shift"] = long["_shift_key"].map(shift_map).fillna(long["shift"])
    long.drop(columns=["_shift_key"], inplace=True, errors="ignore")

    long["name"] = long["name"].astype(str).str.strip()
    return long[["name","week","day","shift"]]

def apply_edo_policy(df: pd.DataFrame, allow_edo: bool) -> pd.DataFrame:
    """If EDO disabled, reclassify EDO → OFF so displays/counts/coverage stay coherent."""
    if df is None or df.empty:
        return df
    if allow_edo:
        return df
    df2 = df.copy()
    if "shift" in df2.columns:
        df2.loc[df2["shift"] == "EDO", "shift"] = "OFF"
    return df2

def build_display_matrix(assignments_df: pd.DataFrame, weeks: int, people_order=None, days: Optional[List[str]] = None) -> pd.DataFrame:
    """Recreate a full matrix name × (week, day) for given days list (5j or 7j)."""
    if assignments_df is None or assignments_df.empty:
        return pd.DataFrame()
    a = normalize_assignments_columns(assignments_df)
    if days is None:
        days = _DAYS7
    a = a[a["day"].isin(days)]
    piv = a.pivot_table(
        index="name", columns=["week","day"], values="shift",
        aggfunc=lambda x: "/".join(sorted(set(map(str, x)))),
        fill_value=""
    )
    desired = [(w, d) for w in range(1, int(weeks)+1) for d in days]
    for wd in desired:
        if wd not in piv.columns:
            piv[wd] = ""
    piv = piv.reindex(columns=pd.MultiIndex.from_tuples(desired))
    if people_order is not None:
        known = [n for n in people_order if n in piv.index]
        rest = [n for n in piv.index if n not in known]
        piv = piv.reindex(index=known + rest)
    return piv

def build_counts_from_assignments(assignments_df: pd.DataFrame, weeks: int, days: Optional[List[str]] = None) -> pd.DataFrame:
    """Counts by (week, day) for given days list (5j or 7j)."""
    if assignments_df is None or assignments_df.empty:
        return pd.DataFrame()
    a = normalize_assignments_columns(assignments_df)
    if days is None:
        days = _DAYS7
    a = a[a["day"].isin(days)]
    gb = a.groupby(["week","day","shift"]).size().reset_index(name="count")
    piv = gb.pivot_table(index=["week","day"], columns="shift", values="count", fill_value=0)
    desired_index = pd.MultiIndex.from_tuples([(w, d) for w in range(1, int(weeks)+1) for d in days],
                                              names=["week","day"])
    piv = piv.reindex(index=desired_index, fill_value=0)
    return piv

def rename_weeks_multiindex(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex) and df.columns.nlevels >= 2:
        df.columns = pd.MultiIndex.from_arrays(
            [[f"Semaine {w}" for w in df.columns.get_level_values(0)],
             df.columns.get_level_values(1)]
        )
    return df

def _team_palette(teams):
    base = ["#E3F2FD","#E8F5E9","#FFF3E0","#F3E5F5","#E0F2F1","#FCE4EC","#EDE7F6","#FFFDE7","#E1F5FE","#E0F7FA"]
    uniq = [t for t in sorted(set(teams)) if t]
    return {t: base[i % len(base)] for i, t in enumerate(uniq)}

def _hex_to_rgb(h): h = h.lstrip("#"); return (int(h[0:2],16), int(h[2:4],16), int(h[4:6],16))
def _rgb_to_hex(rgb): return "#{:02x}{:02x}{:02x}".format(*rgb)
def _blend_hex(c1, c2, a=0.35):
    r1,g1,b1 = _hex_to_rgb(c1); r2,g2,b2 = _hex_to_rgb(c2)
    return _rgb_to_hex((int((1-a)*r1+a*r2), int((1-a)*g1+a*g2), int((1-a)*b1+a*b2)))

def _soft_shift_color(v: str, theme: str) -> str:
    if theme == "Daltonien":
        palette = {"J": "#DCEAF7", "S": "#F8E5CC", "N": "#E8DDF0", "A": "#E9ECEF", "OFF":"#EEEEEE", "EDO":"#D7EBF2", "": "#FFFFFF"}
    else:
        palette = {"J": "#FFF8E1", "S": "#FDECEC", "N": "#EAF2FD", "A": "#F5F6F7", "OFF":"#F1F1F1", "EDO":"#E7F3F8", "": "#FFFFFF"}
    return palette.get(v, "#FFFFFF")

def style_matrix_team_row(df: pd.DataFrame, team_by_name: dict, team_tint_pct: int, theme: str):
    teams = [team_by_name.get(idx, "") for idx in df.index]
    dft = df.copy()
    dft.insert(0, "Équipe", teams)
    team_color = _team_palette(teams)
    a = max(0, min(60, int(team_tint_pct))) / 100.0  # 0–0.6

    styles = pd.DataFrame("", index=dft.index, columns=dft.columns)

    for i, name in enumerate(dft.index):
        t = teams[i]
        row_tint = team_color.get(t, "#FFFFFF") if t else "#FFFFFF"
        styles.iat[i, 0] = f"background-color: {row_tint}; font-weight:600;"
        for j, col in enumerate(dft.columns[1:], start=1):
            val = dft.iat[i, j]
            s = "" if pd.isna(val) else str(val).strip()
            shift_bg = _soft_shift_color(s, theme)
            bg = _blend_hex(row_tint, shift_bg, a=a) if s else row_tint
            css = [f"background-color: {bg};"]
            if isinstance(dft.columns, pd.MultiIndex):
                if isinstance(col, tuple) and len(col) >= 2:
                    day = col[1]
                    if day in ("Sam","Dim"):
                        css.append("border-top: 1px dashed #e5e7eb; border-bottom: 1px dashed #e5e7eb;")
                    if day == "Lun":
                        css.append("border-left: 2px solid #9ca3af;")
            else:
                if col == "Lun":
                    css.append("border-left: 2px solid #9ca3af;")
            styles.iat[i, j] = "".join(css)
    return dft.style.apply(lambda _: styles, axis=None)

def style_counts(df: pd.DataFrame):
    try:
        import matplotlib  # noqa: F401
        return df.style.background_gradient(cmap="Blues", axis=None)
    except Exception:
        dfn = df.copy()
        import numpy as np
        vals = pd.to_numeric(dfn.stack(), errors='coerce')
        vmin, vmax = np.nanmin(vals), np.nanmax(vals)
        rng = (vmax - vmin) if pd.notna(vmax) and pd.notna(vmin) and vmax != vmin else 1.0
        styles = pd.DataFrame("", index=dfn.index, columns=dfn.columns)
        def _interp(c1, c2, t):
            c1 = int(c1,16); c2 = int(c2,16)
            r1,g1,b1=(c1>>16)&255,(c1>>8)&255,c1&255
            r2,g2,b2=(c2>>16)&255,(c2>>8)&255,c2&255
            r=int(r1+(r2-r1)*t); g=int(g1+(g2-g1)*t); b=int(b1+(b2-b1)*t)
            return f"#{r:02x}{g:02x}{b:02x}"
        for i in range(dfn.shape[0]):
            for j, col in enumerate(dfn.columns):
                v = dfn.iat[i, j]; css=[]
                if isinstance(v, (int,float)):
                    t = (v - vmin)/rng if rng else 0.0
                    css.append(f"background-color: {_interp(int('eaf2fd',16), int('c7ddfb',16), max(0,min(1,float(t))))};")
                if isinstance(dfn.columns, pd.MultiIndex):
                    if isinstance(col, tuple) and len(col) >= 2 and col[1] == "Lun":
                        css.append("border-left: 2px solid #9ca3af;")
                else:
                    if col == "Lun":
                        css.append("border-left: 2px solid #9ca3af;")
                styles.iat[i, j] = "".join(css)
        return dfn.style.apply(lambda _: styles, axis=None)

def _arrow_safe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in df.columns:
        if df[c].dtype == "object":
            try:
                df[c] = df[c].astype("string")
            except Exception:
                pass
    return df

def default_targets_editor(days: List[str]) -> pd.DataFrame:
    # Defaults: 5j → Lun–Ven have J=3,S=2,N=1; weekends 0. 7j → all 0 by default.
    base = []
    for d in days:
        if d in ["Lun","Mar","Mer","Jeu","Ven"]:
            base.append({"day": d, "J": 3, "S": 2, "N": 1, "A": 0, "OFF": 0, "EDO": 0})
        else:
            base.append({"day": d, "J": 0, "S": 0, "N": 0, "A": 0, "OFF": 0, "EDO": 0})
    return pd.DataFrame(base, columns=["day","J","S","N","A","OFF","EDO"])

def editor_to_targets(df_editor: pd.DataFrame, weeks: int, days: List[str]) -> pd.DataFrame:
    if df_editor is None or df_editor.empty:
        return pd.DataFrame(columns=["week","day","shift","required"])
    cols_needed = {"day","J","S","N","A","OFF","EDO"}
    if not cols_needed.issubset(set(df_editor.columns)):
        return pd.DataFrame(columns=["week","day","shift","required"])
    rows = []
    for _, r in df_editor.iterrows():
        day = str(r["day"]).strip()
        if day not in days:
            continue
        for sh in ["J","S","N","A","OFF","EDO"]:
            try:
                req = int(pd.to_numeric(r.get(sh, 0), errors="coerce").fillna(0))
            except Exception:
                req = int(r.get(sh, 0) or 0)
            for w in range(1, int(weeks)+1):
                rows.append({"week": w, "day": day, "shift": sh, "required": req})
    return pd.DataFrame(rows, columns=["week","day","shift","required"])

def yaml_to_editor(yaml_dict: dict, weeks: int, days: List[str]) -> pd.DataFrame:
    if not yaml_dict:
        return default_targets_editor(days)
    data = None
    for k in ["targets","objectifs"]:
        if isinstance(yaml_dict, dict) and k in yaml_dict and isinstance(yaml_dict[k], dict):
            data = yaml_dict[k]
            break
    if data is None and isinstance(yaml_dict, dict):
        data = yaml_dict
    norm = []
    for wk, v in (data or {}).items():
        if isinstance(v, dict) and (isinstance(wk, int) or str(wk).isdigit()):
            w = int(wk)
            for d, sub in v.items():
                if not isinstance(sub, dict): continue
                day = str(d).strip()
                for sh, req in sub.items():
                    norm.append({"week": w, "day": day, "shift": str(sh).upper(), "required": int(req)})
        elif isinstance(v, dict) and isinstance(wk, str) and wk.lower() in {"targets","objectifs","days","jours"}:
            for d, sub in v.items():
                day = str(d).strip()
                for sh, req in (sub or {}).items():
                    for w in range(1, int(weeks)+1):
                        norm.append({"week": w, "day": day, "shift": str(sh).upper(), "required": int(req)})
    df = pd.DataFrame(norm, columns=["week","day","shift","required"])
    if df.empty:
        return default_targets_editor(days)
    pivot = df.groupby(["day","shift"])["required"].max().unstack(fill_value=0)
    for col in ["J","S","N","A","OFF","EDO"]:
        if col not in pivot.columns: pivot[col] = 0
    pivot = pivot.reset_index()
    order = {d:i for i,d in enumerate(days)}
    pivot["__o__"] = pivot["day"].map(order)
    pivot = pivot.sort_values("__o__").drop(columns="__o__", errors="ignore")
    return pivot[["day","J","S","N","A","OFF","EDO"]]

def build_targets_payload(targets_df: pd.DataFrame) -> Dict:
    payload = {
        "list": targets_df.to_dict(orient="records"),
        "nested": {},
    }
    nested: Dict[int, Dict[str, Dict[str, int]]] = {}
    for _, r in targets_df.iterrows():
        w = int(r["week"]); d = str(r["day"]); s = str(r["shift"]); req = int(r["required"])
        nested.setdefault(w, {}).setdefault(d, {})[s] = req
    payload["nested"] = nested
    return payload

def _set_cfg(cfg, name, value):
    try:
        if hasattr(cfg, name):
            setattr(cfg, name, value)
    except Exception:
        pass

# ------------------ UI ------------------

# ---- helpers for targets editor ----
def _get_targets_df_from_session():
    try:
        if 'targets_editor_df' in st.session_state:
            return st.session_state['targets_editor_df']
        for k in list(st.session_state.keys()):
            if str(k).startswith('targets_editor'):
                return st.session_state[k]
    except Exception:
        pass
    return None

st.set_page_config(page_title="Rota Optimizer — UI", layout="wide")
st.title("Rota Optimizer — UI (solve())")


# =========================
# 📊 Couverture vs Besoins de service (patch)

st.caption("v4.10B — UI-only; CLI désactivée par défaut. Besoins éditables, presets YAML, toggle 'Imposer au solveur', EDO activables, 5j/7j.")


with st.sidebar:
    # Données d'entrée
    st.subheader("📥 Données d'entrée")

    # Uploader CSV équipe (optionnel — l'UI reste la source principale)
    csv_file = st.file_uploader(
        "Équipe (CSV)",
        type=["csv"],
        accept_multiple_files=False,
        help="Doit contenir au minimum la colonne 'name'. Optionnel: 'team'.",
        key="team_csv"
    )
    if csv_file is not None:
        try:
            df_csv = pd.read_csv(csv_file)
            st.session_state["csv_preview"] = df_csv.copy()
            st.caption(f"{len(df_csv)} lignes détectées.")
            with st.expander("Aperçu CSV", expanded=False):
                st.dataframe(df_csv.head(50), width='stretch', height=240)
        except Exception as e:
            st.error(f"Lecture CSV échouée: {e}")

    yaml_file = st.file_uploader(
        "Configuration (YAML, optionnel)",
        type=["yml","yaml"],
        help="Paramètres, besoins presets (targets), règles custom.",
        key="cfg_yaml"
    )
    yaml_snapshot = None
    if yaml_file is not None:
        try:
            import yaml
            yaml_snapshot = yaml.safe_load(yaml_file) or {}
            with st.expander("Aperçu YAML", expanded=False):
                st.json(yaml_snapshot)
        except Exception as e:
            st.warning(f"YAML illisible: {e}")

    st.markdown("---")

    # Affichage
    with st.expander("🧾 Affichage", expanded=True):
        cal_mode = st.radio("Calendrier", ["5 jours (Lun–Ven)", "7 jours (Lun–Dim)"], index=0,
                            help="Adapte la matrice et les comptes au format 5j (Excel) ou 7j.")
    # Apparence
    with st.expander("🎨 Apparence", expanded=True):
        team_tint = st.slider("Intensité teinte d'équipe", min_value=0, max_value=60, value=35, step=5,
                              help="Pourcentage de mélange entre la couleur d'équipe et la couleur du shift.")
        shift_theme = st.selectbox("Thème des couleurs de shifts", ["Pastel","Daltonien"], index=0,
                                   help="Daltonien = palette adaptée (bleu/orange/violet/gris).")

    st.markdown("---")

    # Besoins de service (editable)
    with st.expander("📊 Besoins de service (minima par jour/poste)", expanded=True):
        st.caption("Fixe les **minima** de personnes par *jour* et *poste* (J/S/N/A/OFF/EDO). "
                   "Sert à **mesurer** la couverture (🟢/🟠/🔴) et, si choisi, à **contraindre** le solveur.")
        days = days_for_calendar(cal_mode)
        key_editor = f"targets_editor_{cal_mode}"
        if key_editor not in st.session_state:
            st.session_state[key_editor] = default_targets_editor(days)
        # If calendar mode changed, refresh structure
        df_ed = st.session_state[key_editor]
        if set(df_ed["day"].tolist()) != set(days):
            st.session_state[key_editor] = default_targets_editor(days)
            df_ed = st.session_state[key_editor]

        st.caption("Éditer directement les minima. Valeurs appliquées à **toutes** les semaines de l’horizon sélectionné.")
        df_ed = st.data_editor(
            df_ed,
            width='stretch',
            height=260,
            num_rows="fixed",
            column_order=["day","J","S","N","A","OFF","EDO"],
            hide_index=True,
            key="targets_editor_widget"
        )
        st.session_state[key_editor] = df_ed

        impose_targets = st.checkbox("Imposer ces besoins au solveur", key='impose_targets', value=False, help="Si coché, les minima seront transmis au solveur comme contraintes / objectifs.")
        deficit_tol = st.number_input("Seuil déficit (tolérance)", min_value=0, max_value=99, value=0,
                                      help="Déficit autorisé avant passage au rouge (affichage).")

        with st.expander("Avancé — Presets (YAML/YML)", expanded=False):
            st.caption("Charge un preset depuis un fichier YAML/YML. Si plusieurs semaines sont définies, "
                       "l'éditeur reprend la **valeur max par jour/poste** (broadcast).")
            preset_file = st.file_uploader("Preset YAML/YML", type=["yaml","yml"], key="preset_yaml_upl")
            btn_apply = st.button("Remplacer par ce preset")
            if preset_file is not None and btn_apply:
                try:
                    import yaml
                    preset_yaml = yaml.safe_load(preset_file) or {}
                    st.session_state[key_editor] = yaml_to_editor(preset_yaml, weeks=4, days=days)
                    st.success("Preset chargé dans l'éditeur.")
                except Exception as e:
                    st.error(f"Preset illisible: {e}")
            # Download current editor as YAML for reuse
            try:
                import yaml
                ed_now = st.session_state[key_editor]
                preset_dict = {"targets": {r["day"]: {k:int(r[k]) for k in ["J","S","N","A","OFF","EDO"]} for _, r in ed_now.iterrows()}}
                yaml_bytes = yaml.safe_dump(preset_dict, allow_unicode=True).encode("utf-8")
                st.download_button("💾 Exporter l'éditeur en preset YAML", data=yaml_bytes,
                                   file_name="besoins_preset.yaml", mime="text/yaml")
            except Exception:
                pass

    st.markdown("---")

    # Contraintes & équité
    with st.expander("⚖️ Contraintes & équité", expanded=False):
        fairness_label = st.selectbox(
            "Équité",
            ["Aucune", "Cohortes par jours/semaine", "Équité sur nuits", "Équité sur week-ends"],
            index=1,
            help="Répartition plus homogène selon la règle choisie."
        )
        forbid_n2j = st.checkbox("Interdire Nuit → Jour (lendemain)", value=True)
        forbid_s2j = st.checkbox("Limiter Soir → Jour (lendemain)", value=False)
        balance_weekends = st.checkbox("Équilibrer les week-ends", value=True)
        hard_constraints = st.checkbox("Respect strict des contraintes", value=True)

    # Contraintes avancées
    with st.expander("🧠 Contraintes avancées", expanded=False):
        allow_edo = st.checkbox("Activer les EDO", value=True, help="Si désactivé: les EDO seront reclassés en OFF dans l'affichage/compteurs/couverture.")
        max_nights_seq = st.number_input("Nuits consécutives — maximum", min_value=1, max_value=7, value=3)
        min_rest_after_n = st.number_input("Repos minimal après Nuit (jours)", min_value=0, max_value=7, value=1)
        max_evenings_seq = st.number_input("Soirs consécutifs — maximum", min_value=1, max_value=7, value=3)
        max_days_per_week = st.number_input("Jours travaillés par semaine — maximum", min_value=1, max_value=7, value=5)
        allow_admin_shift = st.checkbox("Autoriser 'Admin' (A)", value=True)

    # Solveur
    st.subheader("⚙️ Solveur")
    weeks = st.number_input("Semaines (horizon)", min_value=1, max_value=24, value=4, step=1,
                            help="Nombre de semaines à planifier.")
    tries = st.number_input("Essais (restarts)", min_value=1, max_value=2000, value=20, step=1,
                            help="Nombre d'essais indépendants pour trouver un meilleur score.")
    seed_str = st.text_input("Seed (optionnel)", value="", help="Laisser vide pour un résultat non déterministe.")
    run = st.button("Lancer la résolution")

# ------------------ Results ------------------

if run:
    if solve is None:
        st.error("Le moteur `rota.engine.solve` est introuvable dans cet environnement.")
        st.stop()

    # Persist CSV to a temp path if needed by engine
    csv_path = None
    if "csv_preview" in st.session_state:
        df_src = st.session_state["csv_preview"]
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
        df_src.to_csv(tmp.name, index=False)
        csv_path = tmp.name
    else:
        st.error("Veuillez charger un CSV d'équipe avant de lancer.")
        st.stop()

    # Build config object best-effort
    cfg = None
    if SolveConfig is not None:
        try:
            cfg = SolveConfig()
        except Exception:
            cfg = None
    # Fill common fields if present
    if cfg is not None:
        def _set(name, value): 
            try:
                if hasattr(cfg, name): setattr(cfg, name, value)
            except Exception: pass
        _set("weeks", int(weeks)); _set("tries", int(tries))
        _set("forbid_night_to_day", bool(forbid_n2j))
        _set("limit_evening_to_day", bool(forbid_s2j))
        _set("balance_weekends", bool(balance_weekends))
        _set("hard_constraints", bool(hard_constraints))
        _set("max_nights_seq", int(max_nights_seq))
        _set("min_rest_after_night", int(min_rest_after_n))
        _set("max_evenings_seq", int(max_evenings_seq))
        _set("max_days_per_week", int(max_days_per_week))
        _set("allow_admin_shift", bool(allow_admin_shift))
        _set("allow_edo", bool(allow_edo))  # if the engine supports it
        fairness_map = {
            "Aucune": "none",
            "Cohortes par jours/semaine": "cohorts_days_per_week",
            "Équité sur nuits": "fair_nights",
            "Équité sur week-ends": "fair_weekends",
        }
        _set("fairness_mode", fairness_map.get(fairness_label, "none"))

        # Inject coverage targets from editor (broadcast to all weeks)
        try:
            _k = [k for k in st.session_state.keys() if k.startswith("targets_editor_")]
            if _k:
                _df_ed = st.session_state[_k[-1]]
                nested_cov = editor_to_nested(_df_ed, weeks=int(weeks))
                _set("coverage_targets", nested_cov)
                if 'impose_targets' in locals():
                    _set("impose_targets", bool(impose_targets))
        except Exception:
            pass

    # Solve
    with st.spinner("Résolution en cours..."):
        try:
            if cfg is not None:
                res = solve((locals().get("csv_path_from_sidebar") or locals().get("csv_path")), cfg)
            else:
                try:
                    res = solve(csv_path)  # fallback signature
                except TypeError:
                    res = solve(csv_path, {"weeks": int(weeks), "tries": int(tries)})
        except Exception as e:
            st.exception(e)
            st.stop()

    # Build views from normalized assignments
    _assign_raw = getattr(res, "assignments", pd.DataFrame())
    _assign_std = normalize_assignments_columns(_assign_raw)
    _assign_std = apply_edo_policy(_assign_std, allow_edo)

    _df_src = st.session_state.get("csv_preview")
    _order = list(_df_src["name"]) if (_df_src is not None and "name" in _df_src.columns) else None
    team_by_name = dict(zip(_df_src["name"], _df_src["team"])) if (_df_src is not None and "team" in _df_src.columns) else {}

    days = days_for_calendar(cal_mode)
    mat = build_display_matrix(_assign_std, int(weeks), _order, days=days)
    mat = rename_weeks_multiindex(mat)

    counts = build_counts_from_assignments(_assign_std, int(weeks), days=days)
    counts = rename_weeks_multiindex(counts)

    # Header metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Semaines", int(getattr(res, "summary", {}).get("weeks", weeks)))
    c2.metric("Personnes", int(getattr(res, "summary", {}).get("people", len(mat.index) if not mat.empty else 0)))
    c3.metric("Vacants", int(getattr(res, "summary", {}).get("vacancies", 0)))
    c4.metric("Score", float(getattr(res, "summary", {}).get("score", 0.0)))

    # Matrice
    st.markdown("### Matrice (personne × jour)")
    if mat.empty:
        st.warning("La matrice est vide après normalisation. Vérifiez le mapping des colonnes personnes et jours.")
        st.json({
            "stats": {
                "rows": int(_assign_std.shape[0]),
                "weeks_unique": sorted(_assign_std["week"].unique().tolist()) if "week" in _assign_std else [],
                "days_unique": sorted(_assign_std["day"].unique().tolist()) if "day" in _assign_std else [],
                "shifts_unique": sorted(_assign_std["shift"].unique().tolist()) if "shift" in _assign_std else [],
            }
        })
    else:
        st.dataframe(
            style_matrix_team_row(mat, team_by_name, team_tint, shift_theme),
            width='stretch', height=440
        )
        st.caption("Légende : J = Jour, S = Soir, N = Nuit, A = Admin, OFF = repos, EDO = jour de repos gagné. Teinte par équipe sur toute la ligne.")

    # Comptes
    st.markdown("### Comptes par shift")
    if counts.empty:
        st.info("Aucun compte calculable (assignments vides).")
    else:
        st.dataframe(style_counts(counts), width='stretch', height=280)

    # Couverture vs Besoins (à partir de l'éditeur)
    st.markdown("### Couverture vs Besoins de service")
    df_editor_now = st.session_state.get(f"targets_editor_{cal_mode}", default_targets_editor(days))
    targets_df = editor_to_targets(df_editor_now, int(weeks), days)
    if not allow_edo and "EDO" in targets_df["shift"].unique():
        st.warning("Des besoins EDO sont définis mais les EDO sont désactivés : ils seront comptés comme OFF.")
        targets_df.loc[targets_df["shift"]=="EDO","shift"] = "OFF"

    def compute_coverage(assign_std: pd.DataFrame, targets: pd.DataFrame, days: List[str]) -> Tuple[pd.DataFrame, pd.DataFrame]:
        if assign_std is None or assign_std.empty or targets is None or targets.empty:
            return pd.DataFrame(), pd.DataFrame()
        a = assign_std.copy()
        a = a[a["day"].isin(days)]
        counts = a.groupby(["week","day","shift"]).size().reset_index(name="assigned")
        merged = targets.merge(counts, on=["week","day","shift"], how="left").fillna({"assigned": 0})
        merged["gap"] = merged["assigned"].astype(int) - merged["required"].astype(int)
        key = merged[merged["gap"] < 0][["week","day","shift"]]
        if key.empty:
            return merged, pd.DataFrame()
        a_key = a.merge(key.drop_duplicates(), on=["week","day","shift"], how="inner")
        details = a_key.groupby(["week","day","shift"])["name"].apply(lambda s: ", ".join(sorted(set(map(str, s))))).reset_index()
        return merged, details

    def coverage_style(df: pd.DataFrame, deficit_tolerance: int):
        styles = pd.DataFrame("", index=df.index, columns=df.columns)
        for i in range(df.shape[0]):
            gap = int(df.at[df.index[i], "gap"])
            if gap >= 0:
                css_bg = "#E8F5E9"
            elif -gap <= deficit_tolerance:
                css_bg = "#FFF3E0"
            else:
                css_bg = "#FFEBEE"
            for j, col in enumerate(df.columns):
                if col in {"required","assigned","gap"}:
                    styles.iat[i, j] = f"background-color: {css_bg};"
        return df.style.apply(lambda _: styles, axis=None)

    coverage, deficits = compute_coverage(_assign_std, targets_df, days)
    if coverage.empty:
        st.info("Aucun besoin saisi (ou données insuffisantes) — la couverture ne peut pas être calculée.")
    else:
        st.dataframe(
            coverage_style(coverage[["week","day","shift","required","assigned","gap"]].sort_values(["week","day","shift"]), int(deficit_tol)),
            width='stretch', height=320
        )
        with st.expander("Déficits — lignes concernées", expanded=False):
            if deficits is None or deficits.empty:
                st.caption("Aucun déficit.")
            else:
                view = coverage.merge(deficits, on=["week","day","shift"], how="left")
                view = view[view["gap"] < 0][["week","day","shift","required","assigned","gap","name"]].rename(columns={"name":"personnes"})
                st.dataframe(view.sort_values(["week","day","shift"]), width='stretch', height=280)

    # Panneau administrateur
    st.markdown("### 🔧 Panneau administrateur")
    try:
        per_person = _assign_std.groupby("name")["shift"].value_counts().unstack(fill_value=0).reset_index()
        for c in ["J","S","N","A","OFF","EDO"]:
            if c not in per_person.columns: per_person[c] = 0
        per_person["Total travaillés"] = per_person[["J","S","N"]].sum(axis=1)
        per_person["Repos (OFF+EDO)"] = per_person[["OFF","EDO"]].sum(axis=1)
        st.markdown("**Affectations par personne**")
        st.dataframe(_arrow_safe(per_person), width='stretch', height=320)
    except Exception as e:
        st.caption(f"Résumé par personne indisponible: {e}")

    try:
        if _df_src is not None and "team" in _df_src.columns:
            a = _assign_std.merge(_df_src[["name","team"]], on="name", how="left")
            nights_by_team = a[a["shift"]=="N"].groupby("team").size().reset_index(name="Nuits")
            st.markdown("**Nuits par équipe**")
            st.dataframe(_arrow_safe(nights_by_team), width='stretch', height=200)
    except Exception as e:
        st.caption(f"Nuits par équipe indisponible: {e}")

    st.markdown("**Métadonnées de la résolution**")
    meta_rows = [
        {"Clé":"Weeks","Valeur": int(getattr(res, "summary", {}).get("weeks", weeks))},
        {"Clé":"People","Valeur": int(getattr(res, "summary", {}).get("people", len(mat.index) if not mat.empty else 0))},
        {"Clé":"Seed","Valeur": getattr(res, "summary", {}).get("seed")},
        {"Clé":"Tries","Valeur": int(tries)},
        {"Clé":"Calendrier","Valeur": cal_mode},
        {"Clé":"Équité","Valeur": fairness_label},
        {"Clé":"EDO activés","Valeur": "Oui" if allow_edo else "Non"},
        {"Clé":"Besoins imposés","Valeur": "Oui" if impose_targets else "Non"},
    ]
    meta_df = pd.DataFrame(meta_rows)
    meta_df["Valeur"] = meta_df["Valeur"].astype("string")
    st.dataframe(meta_df, width='stretch', height=220)

    # Debug export
    st.markdown("### 🧰 Debug")
    sidebar_cfg = {
        "weeks": int(weeks),
        "tries": int(tries),
        "seed": (int(seed_str) if str(seed_str).strip().isdigit() else None),
        "cal_mode": cal_mode,
        "team_tint": int(team_tint),
        "shift_theme": shift_theme,
        "fairness_label": fairness_label,
        "deficit_tolerance": int(deficit_tol),
        "allow_edo": bool(allow_edo),
        "impose_targets": bool(impose_targets),
        "max_nights_seq": int(max_nights_seq),
        "min_rest_after_n": int(min_rest_after_n),
        "max_evenings_seq": int(max_evenings_seq),
        "max_days_per_week": int(max_days_per_week),
        "allow_admin_shift": bool(allow_admin_shift),
    }
    try:
        debug_zip = io.BytesIO()
        def _write_zip(z):
            z.writestr("debug/summary.json", json.dumps(getattr(res, "summary", {}), ensure_ascii=False, indent=2))
            z.writestr("debug/metrics.json", json.dumps(getattr(res, "metrics_json", {}), ensure_ascii=False, indent=2))
            z.writestr("debug/sidebar_config.json", json.dumps(sidebar_cfg, ensure_ascii=False, indent=2))
            try:
                z.writestr("debug/assignments_raw.csv", _assign_raw.to_csv(index=False))
                z.writestr("debug/assignments_normalized.csv", _assign_std.to_csv(index=False))
                z.writestr("debug/matrix.csv", mat.to_csv())
                z.writestr("debug/counts.csv", counts.to_csv())
                z.writestr("debug/targets_from_editor.csv", targets_df.to_csv(index=False))
            except Exception:
                pass
            z.writestr("README.txt", "Rota UI debug bundle incl. editable service needs and EDO policy.")
        try:
            with zipfile.ZipFile(debug_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
                _write_zip(z)
        except RuntimeError:
            with zipfile.ZipFile(debug_zip, "w", compression=zipfile.ZIP_STORED) as z:
                _write_zip(z)
        st.download_button("📦 Exporter le bundle debug (.zip)", data=debug_zip.getvalue(),
                           file_name="rota_debug_bundle.zip", mime="application/zip")
    except Exception as e:
        st.error(f"Export debug impossible: {e}")

    # Prepare targets back to solver for NEXT runs (best-effort only)
    if impose_targets and SolveConfig is not None and cfg is not None:
        payload = build_targets_payload(targets_df)
        for field in ["coverage_targets", "targets", "service_needs"]:
            _set_cfg(cfg, field, payload)
        for field in ["enforce_targets", "impose_targets"]:
            _set_cfg(cfg, field, True)
        st.caption("ℹ️ Les besoins ont été préparés pour le solveur (prochain lancement).")

# ------------------ CLI (disabled by default) ------------------
if __name__ == "__main__":
    # Do NOT run argparse by default to avoid conflicts with Streamlit.
    if os.environ.get("ROTA_CLI", "0") == "1":
        import argparse
        parser = argparse.ArgumentParser(description="CLI pour lancer le solveur (mode non-UI)")
        parser.add_argument("--pattern-csv", required=True, help="Chemin vers le CSV d'équipe")
        parser.add_argument("--weeks", type=int, default=4)
        args = parser.parse_args()
        # Utilise la même API que l'UI (overlay)
        try:
            from rota.engine.targets_overlay import solve as _solve
        except Exception:
            try:
                from rota.engine.solve import solve as _solve
            except Exception:
                from legacy.legacy_v29 import main as _solve  # dernier recours
        res = _solve(args.pattern_csv) if _solve.__code__.co_argcount >= 1 else _solve()
        print("Summary:", getattr(res, "summary", {}))



# -------------------- Couverture vs objectifs --------------------
try:
    nested = editor_to_nested(st.session_state.get("targets_editor_df", None))
except Exception as e:
    nested = {}
if 'res' in locals() and hasattr(res, 'assignments'):
    counts = assignments_to_counts(res.assignments, full=bool(show_extras) if 'show_extras' in locals() else False)
    cov = coverage_join(nested, counts, include_extras=bool(show_extras) if 'show_extras' in locals() else False) if nested else None
    with st.expander("Couverture vs Besoins de service (déprécié — masqué)", expanded=False):
        st.markdown("## 📊 Couverture vs Besoins de service")
        _res = st.session_state.get("last_result") if "last_result" in st.session_state else locals().get("res", None)
        _show_extras = st.session_state.get("show_extras", True)

        try:
            _nested = editor_to_nested(_get_targets_df_from_session(), weeks=int(weeks))
        except Exception:
            _nested = {}

        if _res is not None and hasattr(_res, "assignments"):
            try:
                _counts = assignments_to_counts(_res.assignments, full=bool(_show_extras))
            except Exception as _e:
                st.error(f"Erreur calcul comptes: {_e}")
                _counts = pd.DataFrame(columns=["Semaine","Jour","Poste","Assignes"])
        else:
            _counts = pd.DataFrame(columns=["Semaine","Jour","Poste","Assignes"])

        try:
            _cov = coverage_join(_nested, _counts, include_extras=bool(_show_extras))
        except Exception as _e:
            st.error(f"Erreur jointure couverture: {_e}")
            _cov = pd.DataFrame()

        if _cov is None or _cov.empty:
            st.warning("Aucune cible ou aucune affectation. Modifiez l'éditeur de besoins et/ou lancez le solveur.")
        else:
            _sum = compute_coverage_summary(_cov)
            if _sum.get('cells', 0) > 0:
                ok, warn, bad = _sum['ok'], _sum['warn'], _sum['bad']
                cells = _sum['cells']
                deficit = _sum['deficit_total']
                c_ok = int(round(100*ok/cells))
                c_warn = int(round(100*warn/cells))
                c_bad = int(round(100*bad/cells))
                st.markdown(
                    f"**Résumé couverture (J/S/N)** : "
                    f"🟢 {ok} ({c_ok}%)  |  🟠 {warn} ({c_warn}%)  |  🔴 {bad} ({c_bad}%) — "
                    f"**Déficit total**: {deficit}"
                )
            st.dataframe(
                    style_rag_and_extras(_cov, show_extras=bool(_show_extras)),
                    width='stretch',
                    height=360
                )
                