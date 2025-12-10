"""
Rota Optimizer — Streamlit Web UI
=================================
Pair-based scheduling with OR-Tools CP-SAT solver.
"""
import io
import os
import sys

import pandas as pd
import streamlit as st

# Add src to python path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from rota.io.csv_loader import load_team
from rota.io.pair_export import (
    export_merged_calendar,
    export_pairs_to_csv,
    export_pairs_to_excel,
    export_weekend_to_excel,
)
from rota.io.pdf_export import export_schedule_to_pdf
from rota.io.results_export import export_results
from rota.models.constraints import SolverConfig
from rota.models.person import Person
from rota.solver.edo import build_edo_plan
from rota.solver.optimizer import optimize
from rota.solver.staffing import JOURS, derive_staffing
from rota.solver.validation import calculate_fairness, validate_schedule
from rota.solver.weekend import WeekendConfig, WeekendSolver, validate_weekend_schedule
from rota.utils.logging_setup import init_logging

# Initialize logging at DEBUG for detailed verification
init_logging(level="DEBUG")

st.set_page_config(page_title="Rota Optimizer", page_icon="📅", layout="wide")

# Custom CSS for colored cells
st.markdown("""
<style>
.shift-J { background-color: #DDEEFF !important; color: #333; font-weight: bold; }
.shift-S { background-color: #FFE4CC !important; color: #333; font-weight: bold; }
.shift-N { background-color: #E6CCFF !important; color: #333; font-weight: bold; }
.shift-A { background-color: #DDDDDD !important; color: #333; font-weight: bold; }
.shift-OFF { background-color: #F5F5F5 !important; color: #999; }
.shift-EDO { background-color: #D8D8D8 !important; color: #666; font-style: italic; }
.kpi-card { padding: 1rem; border-radius: 8px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; margin: 0.5rem 0; }
.kpi-value { font-size: 2rem; font-weight: bold; }
.kpi-label { font-size: 0.9rem; opacity: 0.9; }
</style>
""", unsafe_allow_html=True)

st.title("📅 Rota Optimizer — Pair Scheduling")

# Sidebar configuration
st.sidebar.header("⚙️ Configuration")

# Initialize session state for persistent settings
if "config_weeks" not in st.session_state:
    st.session_state.config_weeks = 12
if "config_tries" not in st.session_state:
    st.session_state.config_tries = 2
if "config_seed" not in st.session_state:
    st.session_state.config_seed = 0
if "config_time_limit" not in st.session_state:
    st.session_state.config_time_limit = 60

# Global options
merge_calendars = st.sidebar.checkbox(
    "📅 Mode Fusionné (Semaine + WE)", value=False,
    help="Active l'optimisation conjointe et l'export fusionné"
)
st.session_state.merge_calendars = merge_calendars

weeks = st.sidebar.number_input("Semaines", min_value=1, max_value=24, value=st.session_state.config_weeks, key="config_weeks")
tries = st.sidebar.number_input("Essais (multi-seed)", min_value=1, max_value=50, value=st.session_state.config_tries, key="config_tries")
seed = st.sidebar.number_input("Seed (0=auto)", min_value=0, value=st.session_state.config_seed, key="config_seed")
time_limit = st.sidebar.number_input("Temps limite (sec)", min_value=10, max_value=600, value=st.session_state.config_time_limit, key="config_time_limit")

# Advanced panel (Week)
with st.sidebar.expander("🔧 Paramètres Avancés (Semaine)", expanded=False):
    st.subheader("Contraintes dures")
    forbid_night_to_day = st.checkbox("Repos après nuit", value=True, 
        help="Interdire de travailler le jour après une nuit")
    edo_enabled = st.checkbox("EDO activé", value=True,
        help="Activer les jours de repos (1 jour/2 semaines)")
    max_nights_sequence = st.number_input("Nuits consécutives max", min_value=1, max_value=5, value=3)
    max_consecutive_days = st.number_input("Jours consécutifs max", min_value=3, max_value=14, value=6, help="Maximum de jours travaillés sans interruption (sauf si week-end travaillé)")
    
    st.subheader("Effectifs Requis (Par Jour)")
    c1, c2, c3 = st.columns(3)
    with c1:
        req_pairs_D = st.number_input("Paires Jour", min_value=1, max_value=10, value=4, help="Nb de paires (x2 personnes)")
    with c2:
        req_solos_S = st.number_input("Pers. Soir", min_value=1, max_value=5, value=1, help="Nb de personnes (Solo)")
    with c3:
        req_pairs_N = st.number_input("Paires Nuit", min_value=1, max_value=5, value=1, help="Nb de paires (x2 personnes)")
    
    st.subheader("Poids objectif (soft)")
    st.caption("Plus le poids est élevé, plus la contrainte est prioritaire")
    weight_night_fairness = st.slider("σ Nuits", min_value=0, max_value=20, value=10)
    weight_eve_fairness = st.slider("σ Soirs", min_value=0, max_value=20, value=3)
    weight_deviation = st.slider("Écart cible", min_value=0, max_value=20, value=5)
    weight_clopening = st.slider("Soir→Jour", min_value=0, max_value=10, value=1,
        help="Pénalité pour enchaînement soir suivi d'un jour")
    
    st.subheader("Équité")
    fairness_mode = st.selectbox("Mode cohorte", ["by-wd", "by-team", "none"])

# Advanced panel (Weekend)
with st.sidebar.expander("🔧 Paramètres Avancés (Week-end)", expanded=False):
    st.caption("Samedi & Dimanche")
    
    max_weekends_month = st.number_input(
        "Max week-ends/mois", min_value=1, max_value=4, value=2,
        help="Nombre maximum de week-ends travaillés par mois"
    )
    forbid_consecutive_nights = st.checkbox(
        "Interdire 2 nuits de suite (WE)", value=True,
        help="Si coché, empêche de faire Samedi Nuit ET Dimanche Nuit"
    )
    
    st.subheader("Poids objectif")
    weight_w_fairness = st.slider("σ Fairness", min_value=0, max_value=20, value=10, help="Équité charge globale")
    weight_w_split = st.slider("Pénalité Split", min_value=0, max_value=20, value=5, help="Éviter de travailler Samedi ET Dimanche (sauf 24h)")
    weight_w_24h = st.slider("Équité 24h", min_value=0, max_value=20, value=5, help="Répartir équitablement les shifts 24h")
    weight_w_consecutive = st.slider("Pénalité 3 WE consécutifs", min_value=0, max_value=500, value=50, step=10, help="Pénalité forte pour travailler 3 week-ends de suite")

# File upload
uploaded_file = st.file_uploader("📂 Charger équipe (CSV)", type=["csv"])

if True:
    try:
        if uploaded_file:
            df = pd.read_csv(uploaded_file)
            people = load_team(df)
            st.success(f"✅ {len(people)} personnes chargées")
        else:
            people = [Person(name=f"P4_{i+1}", workdays_per_week=4, edo_eligible=True) for i in range(12)] + \
                     [Person(name=f"P3_{i+1}", workdays_per_week=3, edo_eligible=False) for i in range(4)]
            st.info("ℹ️ Mode démo: Équipe par défaut chargée (16 personnes).")
        
        # Show team
        with st.expander("👥 Équipe", expanded=False):
            team_data = []
            for p in people:
                team_data.append({
                    "Nom": p.name,
                    "Jours/sem": p.workdays_per_week,
                    "EDO": "✓" if p.edo_eligible else "",
                    "EDO fixe": p.edo_fixed_day or "",
                    "Préfère nuit": "✓" if p.prefers_night else "",
                    "Pas soir": "✓" if p.no_evening else "",
                    "Max nuits": p.max_nights if p.max_nights < 1000 else "",
                })
            st.dataframe(pd.DataFrame(team_data), use_container_width=True)
        
        if "schedule" not in st.session_state:
            st.session_state.schedule = None

        if "w_result" not in st.session_state:
            st.session_state.w_result = None
            st.session_state.validation = None
            st.session_state.fairness = None
            st.session_state.best_seed = None
            st.session_state.best_score = None

        # Triggers
        trigger_week = False
        trigger_weekend = False
        run_stress = False
        
        if merge_calendars:
            if st.button("🚀 Générer Planning Complet (Semaine + Week-end)", type="primary", use_container_width=True):
                trigger_week = True
                trigger_weekend = True
        
        # Tabs
        tabs_labels = ["📅 Planning Semaine", "🏖️ Planning Week-end"]
        if merge_calendars:
            tabs_labels.append("🌐 Planning Global")
        tabs_labels.append("📥 Téléchargements")
        
        tabs = st.tabs(tabs_labels)
        tab_week = tabs[0]
        tab_weekend = tabs[1]
        
        tab_merged = None
        if merge_calendars:
            tab_merged = tabs[2]
            tab_downloads = tabs[3]
        else:
            tab_downloads = tabs[2]

        with tab_week:
            if not merge_calendars:
                col_btn1, col_btn2 = st.columns([2, 1])
                with col_btn1:
                    if st.button("🚀 Générer Planning Semaine", type="primary", use_container_width=True):
                        trigger_week = True
                with col_btn2:
                    if st.button("⚠️ Stress Test", help="Test impossible demand to verify defect logging", use_container_width=True):
                        trigger_week = True
                        run_stress = True

            if trigger_week:
                with st.spinner("Optimisation Semaine en cours..." if not run_stress else "🔥 Stress Test en cours..."):
                    config = SolverConfig(
                        weeks=weeks,
                        time_limit_seconds=time_limit,
                        forbid_night_to_day=forbid_night_to_day,
                        max_nights_sequence=max_nights_sequence,
                        max_consecutive_days=max_consecutive_days,
                    )
                    
                    # Custom staffing from UI
                    custom_staffing = {"D": req_pairs_D, "S": req_solos_S, "N": req_pairs_N}
                    
                    # For stress test, demand way more than capacity
                    if run_stress:
                        custom_staffing = {"D": 6, "S": 2, "N": 2} # ~50% more than normal
                    
                    actual_seed = seed if seed > 0 else None
                    schedule, best_seed, best_score = optimize(
                        people, config, tries=tries, seed=actual_seed, cohort_mode=fairness_mode,
                        custom_staffing=custom_staffing
                    )
                    
                    # Accept feasible or optimal
                    if schedule.status in ["optimal", "feasible"]:
                        # Calculate all artifacts
                        edo_plan = build_edo_plan(people, weeks)
                        staffing = derive_staffing(people, weeks, edo_plan.plan, custom_staffing=custom_staffing)
                        validation = validate_schedule(schedule, people, edo_plan, staffing)
                        fairness = calculate_fairness(schedule, people, fairness_mode)
                        
                        # Save to session state
                        st.session_state.schedule = schedule
                        st.session_state.validation = validation
                        st.session_state.fairness = fairness
                        st.session_state.best_seed = best_seed
                        st.session_state.best_score = best_score
                        st.session_state.edo_plan = edo_plan
                        st.session_state.staffing = staffing
                    # The else block for schedule status is now handled in the display section below.

            # DISPLAY RESULTS FROM SESSION STATE
            if st.session_state.schedule:
                schedule = st.session_state.schedule
                
                if schedule.status in ["optimal", "feasible"]:
                    validation = st.session_state.validation
                    fairness = st.session_state.fairness
                    best_seed = st.session_state.best_seed
                    best_score = st.session_state.best_score
                    edo_plan = st.session_state.edo_plan
                    staffing = st.session_state.get("staffing", None)  # Retrieve for display
                    
                    # Export results for analysis
                    results_config = {
                        "weeks": weeks,
                        "time_limit_seconds": time_limit,
                        "tries": tries,
                        "seed": best_seed,
                        "forbid_night_to_day": forbid_night_to_day,
                        "edo_enabled": edo_enabled,
                        "max_nights_sequence": max_nights_sequence,
                        "fairness_mode": fairness_mode,
                    }
                    results_weights = {
                        "night_fairness": weight_night_fairness,
                        "eve_fairness": weight_eve_fairness,
                        "deviation": weight_deviation,
                        "clopening": weight_clopening,
                    }
                    results_path = export_results(
                        schedule, people, edo_plan, validation, fairness,
                        results_config, results_weights
                    )
                    
                    st.info(f"📁 Résultats exportés: `{results_path}`")

                    
                    # === SCENARIO DIAGNOSIS (Executive Summary) ===
                    st.subheader("📋 État du Planning")
                    
                    # Calculate Global Metrics
                    # Deficit: Unfilled slots
                    deficit_slots = validation.slots_vides
                    
                    # Surplus: Total actual shifts vs total capacity (target)
                    total_worked = 0
                    total_capacity = 0
                    for p in people:
                         # Capacity
                         edo_w = sum(1 for w in range(1, weeks+1) if p.name in edo_plan.plan.get(w, set()))
                         total_capacity += (p.workdays_per_week * weeks - edo_w)
                         # Worked
                         total_worked += schedule.count_shifts(p.name, 'D') + \
                                         schedule.count_shifts(p.name, 'S') + \
                                         schedule.count_shifts(p.name, 'N') + \
                                         schedule.count_shifts(p.name, 'A')
                    
                    surplus_slots = total_capacity - total_worked
                    
                    if deficit_slots > 0:
                        # SCENARIO 2: DEFICIT
                        st.error(f"❌ **Déficit de Personnel détecté : {deficit_slots} quarts non pourvus.**")
                        st.markdown("Le nombre d'agents est insuffisant pour couvrir la demande. Veuillez initier des recrutements externes pour les créneaux ci-dessous.")
                        
                        # Identify specific missing slots
                        # We need to reconstruct this by checking staffing vs assignments
                        missing_data = []
                        
                        if staffing is None:
                            st.warning("⚠️ Détails du déficit non disponibles. Veuillez relancer le solveur.")
                        else:
                            # Include both unfilled_slot and incomplete_pair
                            gap_types = {"unfilled_slot", "incomplete_pair"}
                            for v in validation.violations:
                                if v.type in gap_types:
                                    count = getattr(v, "count", 1)
                                    # For incomplete_pair: 1 person missing
                                    people_needed = 1 if v.type == "incomplete_pair" else (count * 2 if v.shift in ["D", "N"] else count)
                                    shift_name = {"D": "Jour", "S": "Soir", "N": "Nuit"}.get(v.shift, v.shift)
                                    
                                    missing_data.append({
                                        "Semaine": v.week, 
                                        "Jour": v.day, 
                                        "Quart": shift_name,
                                        "Type": "Paire incomplète" if v.type == "incomplete_pair" else "Slot vide",
                                        "Pers. à recruter": people_needed,
                                        "Message": v.message
                                    })
                        
                        with st.expander("🚨 Détail des Besoins Externes (Contractors)", expanded=True):
                            if missing_data:
                                df_missing = pd.DataFrame(missing_data)
                                total_people = df_missing["Pers. à recruter"].sum()
                                st.markdown(f"**Total à recruter: {total_people} personnes**")
                                st.dataframe(df_missing, use_container_width=True)
                            else:
                                st.info("Aucun détail disponible.")
                            
                    elif surplus_slots > 5: # Threshold for significant surplus
                        # SCENARIO 1: SURPLUS
                        st.success(f"✅ **Surplus de Capacité : L'équipe est sous-utilisée de {surplus_slots} créneaux.**")
                        st.markdown("Tous les besoins sont couverts et l'équipe a encore de la disponibilité. Envisagez d'augmenter la charge ou d'accorder plus de congés/formations.")
                        
                    else:
                        # SCENARIO 3: BALANCED / TIGHT
                        st.warning("⚠️ **Planning Tendu / Équilibré**")
                        st.markdown("""
                        L'équipe couvre exactement la charge (« Juste-à-temps »). 
                        - Tous les postes sont pourvus.
                        - Tout le monde travaille proche de sa cible.
                        - **Attention :** Vérifiez les métriques d'équité (écarts-types) pour voir si des compromis ont été faits.
                        """)

                    # === DASHBOARD (Tableau de bord) ===
                    st.header("📊 Tableau de bord")
                    
                    # Calculate capacity utilization
                    total_capacity = sum(p.workdays_per_week for p in people) * weeks
                    total_worked = sum(1 for a in schedule.assignments for _ in [a.person_a, a.person_b] if _)
                    capacity_utilization = (total_worked / total_capacity * 100) if total_capacity > 0 else 0
                    
                    # Calculate unfilled slots in person-shifts (unified)
                    unfilled_person_shifts = 0
                    if staffing:
                        for w in range(1, weeks + 1):
                            for d in JOURS:
                                for s_code in ["D", "N", "S"]:
                                    req_slots = staffing[w].slots[d].get(s_code, 0)
                                    assigned = len([a for a in schedule.assignments if a.week == w and a.day == d and a.shift == s_code])
                                    if s_code in ["D", "N"]:  # Pairs: each slot = 2 people
                                        unfilled_person_shifts += (req_slots - assigned) * 2
                                    else:  # Solo: each slot = 1 person
                                        unfilled_person_shifts += (req_slots - assigned)
                    
                    # Total constraint violations
                    total_violations = (
                        validation.rolling_48h_violations + 
                        validation.nuit_suivie_travail + 
                        validation.soir_vers_jour +
                        max(0, unfilled_person_shifts)
                    )
                    
                    # Primary KPIs
                    col1, col2, col3, col4, col5 = st.columns(5)
                    with col1:
                        st.metric("📊 Score", f"{best_score:.0f}")
                    with col2:
                        util_icon = "🟢" if capacity_utilization >= 90 else ("🟡" if capacity_utilization >= 70 else "🔴")
                        st.metric(f"{util_icon} Utilisation", f"{capacity_utilization:.1f}%")
                    with col3:
                        deficit_icon = "✅" if unfilled_person_shifts == 0 else "❌"
                        st.metric(f"{deficit_icon} Gaps", f"{unfilled_person_shifts} pers.")
                    with col4:
                        viol_icon = "✅" if total_violations == 0 else "⚠️"
                        st.metric(f"{viol_icon} Violations", total_violations)
                    with col5:
                        st.metric("⏱️ Temps", f"{schedule.solve_time_seconds:.1f}s")
                    
                    # Secondary metrics (detailed)
                    with st.expander("📈 Détails des métriques", expanded=False):
                        col1, col2, col3, col4, col5 = st.columns(5)
                        with col1:
                            st.metric("Violations 48h", validation.rolling_48h_violations,
                                    delta="CRITIQUE" if validation.rolling_48h_violations > 0 else None,
                                    delta_color="inverse")
                        with col2:
                            st.metric("Nuit→Travail", validation.nuit_suivie_travail, 
                                    delta="violations" if validation.nuit_suivie_travail > 0 else None,
                                    delta_color="inverse")
                        with col3:
                            st.metric("Soir→Jour", validation.soir_vers_jour)
                        with col4:
                            st.metric("σ Nuits", f"{fairness.night_std:.2f}")
                        with col5:
                            st.metric("σ Soirs", f"{fairness.eve_std:.2f}")
                        
                        st.caption(f"🌱 Seed gagnant: {best_seed}")
                        
                        # Violation breakdown by type
                        if validation.violations:
                            st.divider()
                            st.write("**Détail des violations:**")
                            viol_types = {}
                            for v in validation.violations:
                                viol_types[v.type] = viol_types.get(v.type, 0) + 1
                            
                            cols = st.columns(len(viol_types))
                            for i, (vtype, count) in enumerate(viol_types.items()):
                                type_labels = {
                                    "unfilled_slot": "🔴 Slots vides",
                                    "night_followed_work": "🟠 Nuit→Travail",
                                    "clopening": "🟡 Soir→Jour",
                                    "48h_exceeded": "🔴 48h dépassé",
                                    "duplicate": "⚠️ Doublon"
                                }
                                label = type_labels.get(vtype, vtype)
                                with cols[i]:
                                    st.metric(label, count)

                    
                    st.divider()
                            
                    # Tabs
                    t1, t2, t3, t4, t5, t6 = st.tabs(["📊 Matrice", "📅 Calendrier", "📈 Analytics", "👥 ParPoste", "📋 Synthèse", "📥 Export"])
                    
                    with t1:
                        st.subheader("Matrice des affectations")
                        st.caption("🔵 Jour | 🟠 Soir | 🟣 Nuit | ⬜ Admin | ⚪ OFF")
                        
                        # Build matrix with colors
                        names = sorted([p.name for p in people])
                        
                        # Build works_on dict
                        works_on = {}
                        for a in schedule.assignments:
                            code = {"D": "J", "E": "S", "N": "N", "A": "A"}.get(a.shift, a.shift)
                            if a.person_a:
                                works_on[(a.person_a, a.week, a.day)] = code
                            if a.person_b:
                                works_on[(a.person_b, a.week, a.day)] = code
                        
                        # Fill OFF/EDO
                        for name in names:
                            for w in range(1, weeks+1):
                                has_edo = name in edo_plan.plan.get(w, set())
                                edo_assigned = False
                                for d in JOURS:
                                    key = (name, w, d)
                                    if key not in works_on:
                                        if has_edo and not edo_assigned:
                                            works_on[key] = "EDO"
                                            edo_assigned = True
                                        else:
                                            works_on[key] = "OFF"
                        
                        # Build styled dataframe
                        cols = [f"S{w}_{d}" for w in range(1, weeks+1) for d in JOURS]
                        matrix_data = []
                        for name in names:
                            row = {"Nom": name}
                            for w in range(1, weeks+1):
                                for d in JOURS:
                                    col = f"S{w}_{d}"
                                    row[col] = works_on.get((name, w, d), "OFF")
                            matrix_data.append(row)
                        
                        df_matrix = pd.DataFrame(matrix_data)
                        df_matrix = df_matrix.set_index("Nom")
                        
                        # Color function
                        def color_shift(val):
                            colors = {
                                "J": "background-color: #DDEEFF; color: #333; font-weight: bold;",
                                "S": "background-color: #FFE4CC; color: #333; font-weight: bold;",
                                "N": "background-color: #E6CCFF; color: #333; font-weight: bold;",
                                "A": "background-color: #DDDDDD; color: #333; font-weight: bold;",
                                "OFF": "background-color: #F8F8F8; color: #BBB;",
                                "EDO": "background-color: #D8D8D8; color: #666; font-style: italic;",
                            }
                            return colors.get(val, "")
                        
                        styled = df_matrix.style.map(color_shift)
                        st.dataframe(styled, use_container_width=True, height=450)
                    
                    with t2:
                        # ============ CALENDAR TAB - Coverage Heatmap with Gaps ============
                        st.subheader("📅 Calendrier de Couverture")
                        st.caption("🟢 Couvert | 🟡 Partiel | 🔴 Manque")
                        
                        # Calculate coverage per day per week
                        coverage_data = []
                        for w in range(1, weeks + 1):
                            row = {"Semaine": f"S{w}"}
                            for d in JOURS:
                                # Count assignments for this day
                                day_assignments = [a for a in schedule.assignments if a.week == w and a.day == d]
                                
                                # Required slots (from staffing if available)
                                req_d = req_pairs_D * 2  # D pairs = 2 people each
                                req_s = req_solos_S      # S is solo
                                req_n = req_pairs_N * 2  # N pairs = 2 people each
                                total_required = req_d + req_s + req_n
                                
                                # Actual filled
                                filled = sum(
                                    (1 if a.person_a else 0) + (1 if a.person_b else 0)
                                    for a in day_assignments
                                )
                                
                                pct = (filled / total_required * 100) if total_required > 0 else 100
                                if pct >= 100:
                                    row[d] = "✅"
                                elif pct >= 80:
                                    row[d] = f"⚠️ {int(pct)}%"
                                else:
                                    row[d] = f"❌ {int(pct)}%"
                            coverage_data.append(row)
                        
                        df_coverage = pd.DataFrame(coverage_data)
                        
                        # Color function for coverage
                        def color_coverage(val):
                            if "✅" in str(val):
                                return "background-color: #D4EDDA; color: #155724;"
                            elif "⚠️" in str(val):
                                return "background-color: #FFF3CD; color: #856404;"
                            elif "❌" in str(val):
                                return "background-color: #F8D7DA; color: #721C24; font-weight: bold;"
                            return ""
                        
                        styled_cov = df_coverage.style.map(color_coverage, subset=JOURS)
                        st.dataframe(styled_cov, use_container_width=True, hide_index=True)
                        
                        # Show gap details if any
                        if validation and validation.slots_vides > 0:
                            st.error(f"🚨 **{validation.slots_vides} créneaux non pourvus**")
                            with st.expander("Voir détails des manques", expanded=True):
                                gaps = [v for v in validation.violations if v.type in {"unfilled_slot", "incomplete_pair"}]
                                for v in gaps[:20]:  # Show first 20
                                    st.write(f"• **S{v.week} {v.day}** - {v.shift}: {v.message}")
                                if len(gaps) > 20:
                                    st.write(f"... et {len(gaps) - 20} autres")
                    
                    with t3:
                        # ============ ANALYTICS TAB - Charts ============
                        st.subheader("📈 Analyse et Graphiques")
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            # Workload distribution pie chart
                            st.write("**Répartition des quarts**")
                            shift_counts = {"Jour": 0, "Soir": 0, "Nuit": 0}
                            for a in schedule.assignments:
                                if a.shift == "D":
                                    shift_counts["Jour"] += (1 if a.person_a else 0) + (1 if a.person_b else 0)
                                elif a.shift == "S":
                                    shift_counts["Soir"] += 1 if a.person_a else 0
                                elif a.shift == "N":
                                    shift_counts["Nuit"] += (1 if a.person_a else 0) + (1 if a.person_b else 0)
                            
                            import plotly.express as px
                            fig_pie = px.pie(
                                values=list(shift_counts.values()),
                                names=list(shift_counts.keys()),
                                color_discrete_sequence=["#DDEEFF", "#FFE4CC", "#E6CCFF"]
                            )
                            fig_pie.update_layout(margin=dict(l=20, r=20, t=30, b=20), height=300)
                            st.plotly_chart(fig_pie, use_container_width=True)
                        
                        with col2:
                            # Weekly coverage line chart
                            st.write("**Couverture par semaine**")
                            weekly_data = []
                            for w in range(1, weeks + 1):
                                week_assignments = [a for a in schedule.assignments if a.week == w]
                                filled = sum(
                                    (1 if a.person_a else 0) + (1 if a.person_b else 0)
                                    for a in week_assignments
                                )
                                required = 5 * (req_pairs_D * 2 + req_solos_S + req_pairs_N * 2)  # 5 days
                                pct = (filled / required * 100) if required > 0 else 100
                                weekly_data.append({"Semaine": w, "Couverture %": pct})
                            
                            df_weekly = pd.DataFrame(weekly_data)
                            st.line_chart(df_weekly.set_index("Semaine"))
                        
                        # Fairness bar chart
                        st.write("**Équité par cohorte (σ)**")
                        if fairness:
                            cohort_data = []
                            for cohort in fairness.night_std_by_cohort:
                                cohort_data.append({
                                    "Cohorte": cohort,
                                    "σ Nuits": fairness.night_std_by_cohort.get(cohort, 0),
                                    "σ Soirs": fairness.eve_std_by_cohort.get(cohort, 0)
                                })
                            df_fairness = pd.DataFrame(cohort_data)
                            st.bar_chart(df_fairness.set_index("Cohorte"))
                        else:
                            st.info("Données d'équité non disponibles")
                    
                    with t4:
                        st.subheader("Affectations par poste (paires)")
                        for w in range(1, min(weeks+1, 5)):
                            st.write(f"**Semaine {w}**")
                            pairs_data = []
                            for d in JOURS:
                                row = {"Jour": d}
                                for shift_name, shift_code in [("Jour", "D"), ("Soir", "S"), ("Nuit", "N"), ("Admin", "A")]:
                                    pairs = [a for a in schedule.assignments 
                                            if a.week == w and a.day == d and a.shift == shift_code]
                                    if shift_code == "A":
                                        row[shift_name] = ", ".join(a.person_a for a in pairs if a.person_a)
                                    else:
                                        row[shift_name] = "; ".join(f"{a.person_a}/{a.person_b}" for a in pairs)
                                pairs_data.append(row)
                            st.dataframe(pd.DataFrame(pairs_data), use_container_width=True, hide_index=True)
                    
                    with t5:
                        st.subheader("Statistiques par personne")
                        
                        stats_data = []
                        name_to_person = {p.name: p for p in people}
                        for p in people:
                            name = p.name
                            j = schedule.count_shifts(name, 'D')
                            s = schedule.count_shifts(name, 'S')
                            n = schedule.count_shifts(name, 'N')
                            a = schedule.count_shifts(name, 'A')
                            total = j + s + n + a
                            
                            edo_weeks = sum(1 for w in range(1, weeks+1) if name in edo_plan.plan.get(w, set()))
                            target = p.workdays_per_week * weeks - edo_weeks
                            delta = total - target
                            stats_data.append({
                                "Nom": name, 
                                "Jours": j, "Soirs": s, "Nuits": n, "Admin": a,
                                "Total": total, "Cible": target, "Δ": delta, "EDO": edo_weeks
                            })
                        
                        df_stats = pd.DataFrame(stats_data)
                        
                        # Color delta column
                        def color_delta(val):
                            if val > 0:
                                return "background-color: #FFE4E4; color: #D00;"
                            elif val < 0:
                                return "background-color: #E4E4FF; color: #00D;"
                            return ""
                        
                        styled_stats = df_stats.style.map(color_delta, subset=["Δ"])
                        st.dataframe(styled_stats, use_container_width=True, hide_index=True)
                        
                        # Fairness by cohort
                        st.subheader("Équité par cohorte")
                        cohort_data = []
                        for cid, std_n in fairness.night_std_by_cohort.items():
                            std_e = fairness.eve_std_by_cohort.get(cid, 0.0)
                            cohort_data.append({"Cohorte": cid, "σ Nuits": f"{std_n:.2f}", "σ Soirs": f"{std_e:.2f}"})
                        st.dataframe(pd.DataFrame(cohort_data), use_container_width=True, hide_index=True)
                    
                    with t6:
                        st.subheader("Téléchargements")
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            csv_buffer = io.StringIO()
                            export_pairs_to_csv(schedule, csv_buffer)
                            st.download_button(
                                "📥 Télécharger CSV",
                                csv_buffer.getvalue(),
                                "planning.csv",
                                "text/csv"
                            )
                        
                        with col2:
                            xlsx_buffer = io.BytesIO()
                            
                            # Check for merged export
                            should_merge = (
                                st.session_state.get("merge_calendars", False) and 
                                st.session_state.get("w_result") and 
                                st.session_state.w_result.status in ["OPTIMAL", "FEASIBLE"]
                            )
                            
                            if should_merge:
                                export_merged_calendar(
                                    schedule, st.session_state.w_result, people, edo_plan, xlsx_buffer,
                                    validation=validation, fairness=fairness,
                                    staffing=staffing,
                                    config={"weeks": weeks, "tries": tries, "seed": best_seed}
                                )
                                filename = "planning_complet.xlsx"
                            else:
                                export_pairs_to_excel(
                                    schedule, people, edo_plan, xlsx_buffer,
                                    validation=validation, fairness=fairness,
                                    config={"weeks": weeks, "tries": tries, "seed": best_seed},
                                    staffing=staffing  # For Gaps sheet
                                )
                                filename = "planning_semaine.xlsx"

                            st.download_button(
                                f"📥 Télécharger Excel ({'Complet' if should_merge else 'Semaine'})",
                                xlsx_buffer.getvalue(),
                                filename,
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        
                        # PDF Export
                        st.divider()
                        st.subheader("📄 Export PDF")
                        
                        pdf_buffer = io.BytesIO()
                        weekend_for_pdf = st.session_state.get("w_result") if should_merge else None
                        export_schedule_to_pdf(
                            schedule, people, edo_plan, pdf_buffer,
                            validation=validation, fairness=fairness,
                            weekend_result=weekend_for_pdf,
                            config={"weeks": weeks, "tries": tries, "seed": best_seed, "edo_enabled": edo_enabled}
                        )
                        
                        st.download_button(
                            "📄 Télécharger PDF (Rapport)",
                            pdf_buffer.getvalue(),
                            "planning_rapport.pdf",
                            "application/pdf"
                        )
                else:
                    st.error(f"❌ Pas de solution trouvée: {schedule.status}")

        with tab_weekend:
            st.header("Planning Week-end")
            st.caption("Samedi & Dimanche | 24h max/pers | 2 Jours + 2 Nuits par jour")
            
            # Show eligible people
            eligible = [p for p in people if p.available_weekends]
            st.write(f"👥 **Effectif éligible:** {len(eligible)} / {len(people)}")
            with st.expander("Voir liste éligible"):
                st.write(", ".join(p.name for p in eligible))

            if not merge_calendars:
                 if st.button("🚀 Générer Planning Week-end", key="btn_weekend", type="primary"):
                     trigger_weekend = True

# Advanced panel (Weekend) - lines 96+ handled separately, this is the logic wiring block
# Wait, I need to update the global/weekend logic block. 

# ... inside tab_weekend ...
            if trigger_weekend:
                with st.spinner("Optimisation week-end..."):
                    
                    # Extract Fri workers from Week Schedule if available
                    friday_workers = {}
                    if st.session_state.schedule and st.session_state.schedule.status in ["OPTIMAL", "FEASIBLE"]:
                        sch = st.session_state.schedule
                        for w in range(1, weeks + 1):
                            # Get Fri Night assignments
                            pairs = [a for a in sch.assignments 
                                    if a.week == w and a.day == "Ven" and a.shift == "N"]
                            names_list = []
                            for a in pairs:
                                if a.person_a: names_list.append(a.person_a)
                                if a.person_b: names_list.append(a.person_b)
                            friday_workers[w] = names_list
                    
                    w_config = WeekendConfig(
                        num_weeks=weeks,
                        staff_per_shift=2,
                        time_limit_seconds=time_limit,
                        max_weekends_per_month=max_weekends_month,
                        weight_fairness=weight_w_fairness,
                        weight_split_weekend=weight_w_split,
                        weight_24h_balance=weight_w_24h,
                        weight_consecutive_weekends=weight_w_consecutive,
                        forbid_consecutive_nights=forbid_consecutive_nights
                    )
                    w_solver = WeekendSolver(w_config, people, friday_night_workers=friday_workers)
                    result = w_solver.solve()
                    st.session_state.w_result = result
                    
                    if result.status not in ["OPTIMAL", "FEASIBLE"]:
                        st.error(f"❌ Echec: {result.status} - {result.message}")

            # DISPLAY WEEKEND RESULTS FROM SESSION STATE
            if st.session_state.w_result and st.session_state.w_result.status in ["OPTIMAL", "FEASIBLE"]:
                result = st.session_state.w_result
                st.success(f"✅ Solution trouvée ({result.status}) en {result.solve_time:.2f}s")
                
                # Process assignments
                w_map = {}  # (person, week, day) -> list of shifts
                for a in result.assignments:
                    key = (a.person.name, a.week, a.day)
                    if key not in w_map:
                        w_map[key] = []
                    w_map[key].append(a.shift)
                
                # Prepare DF with French day names
                w_data = []
                eligible_names = sorted([p.name for p in eligible])
                
                for name in eligible_names:
                    row = {"Nom": name}
                    total_shifts = 0
                    shifts_24h = 0
                    hours_12h = 0
                    
                    for w in range(1, weeks + 1):
                        for d in ["Sam", "Dim"]:  # French day names
                            shifts = w_map.get((name, w, d), [])
                            shifts.sort()
                            val = "+".join(shifts)
                            row[f"S{w}_{d}"] = val if val else ""
                            
                            shift_count = len(shifts)
                            total_shifts += shift_count
                            if shift_count == 2:  # D+N = 24h
                                shifts_24h += 1
                            elif shift_count == 1:
                                hours_12h += 1
                    
                    row["Total"] = total_shifts
                    row["24h"] = shifts_24h
                    row["12h"] = hours_12h
                    w_data.append(row)
                    
                df_w = pd.DataFrame(w_data)
                df_w = df_w.set_index("Nom")

                # --- TABS ---
                wt1, wt2, wt3, wt4 = st.tabs(["📊 Matrice", "👥 Par Poste", "📈 Synthèse", "📥 Export"])

                with wt1:
                    st.caption("Vue matricielle")
                    def color_weekend(val):
                        if val == "D+N":
                            return "background-color: #FFCCAA; font-weight: bold; color: black;"  # 24h
                        if val == "D":
                            return "background-color: #DDEEFF; font-weight: bold; color: black;"
                        if val == "N":
                            return "background-color: #E6CCFF; font-weight: bold; color: black;"
                        return ""
                    
                    st.dataframe(df_w.style.map(color_weekend), use_container_width=True, height=500)
                
                with wt2:
                    st.caption("Planning par poste (Qui fait quoi ?)")
                    staff_data = []
                    for w in range(1, weeks + 1):
                        for d in ["Sam", "Dim"]:
                            row = {"Semaine": f"S{w}", "Jour": d}
                            for s_code in ["D", "N"]:
                                assigned_pl = []
                                for p_name in eligible_names:
                                    shifts = w_map.get((p_name, w, d), [])
                                    if s_code in shifts:
                                        assigned_pl.append(p_name)
                                row[f"Poste {s_code}"] = ", ".join(assigned_pl)
                                row[f"Nb {s_code}"] = len(assigned_pl)
                            staff_data.append(row)
                    
                    st.dataframe(pd.DataFrame(staff_data), use_container_width=True)

                with wt3:
                    st.caption("Synthèse des charges (Total indicateurs)")
                    
                    # Calculate metrics
                    w_validation = validate_weekend_schedule(result, people, weeks)
                    
                    # KPIs
                    k1, k2, k3 = st.columns(3)
                    with k1:
                        st.metric("Total Shifts", sum(a.hours/12 for a in result.assignments)) # Approx shift count
                    with k2:
                        unused_count = len(w_validation.unused_agents)
                        st.metric("Agents Inutilisés", unused_count, delta=f"{unused_count}" if unused_count > 0 else None, delta_color="inverse")
                    with k3:
                        cons_count = len(w_validation.consecutive_3_plus)
                        st.metric("3+ Week-ends", cons_count, delta="Alerte" if cons_count > 0 else "OK", delta_color="inverse")

                    if w_validation.unused_agents:
                        st.warning(f"⚠️ Agents sans aucun shift week-end: {', '.join(w_validation.unused_agents)}")
                        
                    if w_validation.consecutive_3_plus:
                        st.error("🚨 Agents travaillant 3 week-ends de suite ou plus:")
                        for name, start_w in w_validation.consecutive_3_plus:
                            st.write(f"- **{name}**: Début série semaine {start_w}")
                    
                    stats_df = df_w[["Total", "24h", "12h"]].copy()
                    st.dataframe(stats_df.style.background_gradient(cmap="Blues"), use_container_width=True)

                with wt4:
                    st.info("Pour le planning fusionné (Semaine + WE), utilisez le bouton Export Global dans l'onglet Semaine si le mode fusionné est activé.")
                    xlsx_buffer = io.BytesIO()
                    export_weekend_to_excel(result, people, xlsx_buffer, weeks)
                    st.download_button(
                        "📥 Télécharger Excel (Week-end seul)",
                        xlsx_buffer.getvalue(),
                        "planning_weekend.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )

            if tab_merged:
                with tab_merged:
                    if st.session_state.schedule and st.session_state.w_result and \
                       st.session_state.schedule.status in ["optimal", "feasible", "OPTIMAL", "FEASIBLE"] and \
                       st.session_state.w_result.status in ["OPTIMAL", "FEASIBLE"]:
                        
                        st.subheader("Planning Global (Semaine + Week-end)")
                        
                        # Prepare data
                        week_map = {}
                        # Fill week
                        for a in st.session_state.schedule.assignments:
                             week_map.setdefault((a.person_a, a.week), {})[a.day] = a.shift
                             if a.person_b:
                                 week_map.setdefault((a.person_b, a.week), {})[a.day] = a.shift
                        
                        # Fill weekend
                        for a in st.session_state.w_result.assignments:
                             week_map.setdefault((a.person.name, a.week), {})[a.day] = a.shift
                        
                        # Build DF (Wide Format)
                        merge_lines = []
                        all_days = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
                        known_people = sorted(list(set(k[0] for k in week_map.keys())))
                        
                        for p_name in known_people:
                            row = {"Nom": p_name}
                            for w in range(1, weeks + 1):
                                shifts = week_map.get((p_name, w), {})
                                for d in all_days:
                                    val = shifts.get(d, "")
                                    row[f"S{w}_{d.lower()}"] = val # using lowercase for compact header? OR keep Day name
                                    # Actually users prefer "S1 Lun" etc.
                                    # Or simpler: Just column headers
                            merge_lines.append(row)
                        
                        # Rename columns for display? "S1_Lun" is fine.
                        df_merge = pd.DataFrame(merge_lines)
                        if not df_merge.empty:
                            df_merge = df_merge.set_index("Nom")
                        
                        def color_merge(val):
                            if val == "N": return "background-color: #E6CCFF; color: black; font-weight: bold;"
                            if val in ["D", "J"]: return "background-color: #DDEEFF; color: black; font-weight: bold;"
                            if val == "S": return "background-color: #FFDDAA; color: black; font-weight: bold;"
                            if val == "D+N": return "background-color: #FFCCAA; font-weight: bold; color: black;"
                            if val == "A": return "background-color: #EEFFDD; color: black;"
                            return ""
                        
                        st.dataframe(df_merge.style.map(color_merge), use_container_width=True, height=600)
                        
                    else:
                        st.info("ℹ️ Veuillez générer les deux plannings (Semaine et Week-end) pour visualiser la fusion.")

            # DOWNLOADS TAB
            if tab_downloads:
                with tab_downloads:
                    st.header("Exports")
                    if st.session_state.schedule and st.session_state.schedule.status in ["optimal", "feasible", "OPTIMAL", "FEASIBLE"]:
                        
                        merged_avail = merge_calendars and st.session_state.w_result and st.session_state.w_result.status in ["OPTIMAL", "FEASIBLE"]
                        
                        if merged_avail:
                            st.subheader("Planning complet")
                            buffer_m = io.BytesIO()
                            export_merged_calendar(
                                st.session_state.schedule, st.session_state.w_result, people,
                                st.session_state.edo_plan, buffer_m,
                                validation=st.session_state.validation,
                                fairness=st.session_state.fairness,
                                staffing=st.session_state.get("staffing"),
                                config={"weeks": weeks}
                            )
                            st.download_button(
                                "📥 Télécharger Planning Complet (XLSX)",
                                buffer_m.getvalue(),
                                "planning_complet.xlsx",
                                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )
                        
                        st.subheader("Planning Semaine seul")
                        buffer_w = io.BytesIO()
                        export_pairs_to_excel(
                            st.session_state.schedule, people, st.session_state.edo_plan, buffer_w,
                            validation=st.session_state.validation, fairness=st.session_state.fairness,
                            staffing=st.session_state.get("staffing"),
                            config={"weeks": weeks}
                        )
                        st.download_button(
                            "📥 Télécharger Planning Semaine (XLSX)",
                            buffer_w.getvalue(),
                            "planning_semaine.xlsx",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    else:
                        st.warning("Aucun planning généré. Lancez l'optimisation.")

    except Exception as e:
        st.error(f"Erreur: {e}")
        raise
else:
    st.info("👆 Chargez un fichier CSV d'équipe pour commencer")
    
    with st.expander("📋 Format CSV attendu"):
        st.code("""name,workdays_per_week,weeks_pattern,prefers_night,no_evening,max_nights,edo_eligible,edo_fixed_day,team,available_weekends,max_weekends_per_month
Alice Martin,4,1,0,0,,1,,,1,2
Bob Dupont,4,1,0,0,,1,,,1,2
Claire Bernard,3,1,0,0,,0,,,0,0""")