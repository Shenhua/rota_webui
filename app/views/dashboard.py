"""
Dashboard View
==============
Displays results, KPIs, matrices, and charts.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from app.state.session import SessionStateManager
from rota.solver.staffing import JOURS

def render_dashboard(state: SessionStateManager):
    """Render the main dashboard."""
    if not state.schedule or state.schedule.status not in ["optimal", "feasible"]:
        if state.schedule and state.schedule.status:
             st.error(f"❌ Pas de solution trouvée: {state.schedule.status}")
        else:
             st.info("👋 Veuillez lancer une optimisation pour voir les résultats.")
        return

    # === KPIs ===
    _render_kpis(state)

    # === TABS ===
    t1, t2, t3, t4, t5 = st.tabs(["📊 Matrice", "📅 Calendrier", "📈 Analytics", "👥 ParPoste", "📋 Synthèse"])
    
    with t1:
        _render_matrix(state)
    with t2:
        _render_coverage(state)
    with t3:
        _render_charts(state)
    with t4:
        _render_by_shift(state)
    with t5:
        _render_stats(state)

def _render_kpis(state):
    schedule = state.schedule
    validation = state.validation
    
    # Simple top-level KPIs
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Score", f"{state.best_score:.0f}")
    with col2:
        st.metric("Violations", validation.rolling_48h_violations + validation.nuit_suivie_travail)
    with col3:
        st.metric("Gaps", validation.slots_vides)
    with col4:
        st.metric("Temps", f"{schedule.solve_time_seconds:.1f}s")
        
    # Diagnosis (Simplified version of original logic)
    if validation.slots_vides > 0:
        st.error(f"❌ Gaps détectés: {validation.slots_vides}")
    else:
        st.success("✅ Planning complet")

def _render_matrix(state):
    st.subheader("Matrice des affectations")
    schedule = state.schedule
    people = state.people
    weeks = state.config_weeks  # type: ignore
    
    # Rebuild simple matrix
    matrix_data = []
    names = sorted([p.name for p in people])
    
    # Pre-fetch assignments
    assign_map = schedule.get_person_day_matrix(code_map={"D":"J", "S":"S", "N":"N"})
    
    for name in names:
        row = {"Nom": name}
        for w in range(1, weeks+1):
            for d in JOURS:
                col = f"S{w}_{d}"
                val = assign_map.get((name, w, d), "")
                row[col] = val
        matrix_data.append(row)
        
    df = pd.DataFrame(matrix_data)
    st.dataframe(df, use_container_width=True)

def _render_coverage(state):
    st.subheader("📅 Calendrier de Couverture")
    # simplified placeholder for now
    st.write("Couverture visual will go here.")

def _render_charts(state):
    st.subheader("📈 Analytics")
    schedule = state.schedule
    
    # Pie chart example
    shift_counts = {"Jour": 0, "Soir": 0, "Nuit": 0}
    for a in schedule.assignments:
        if a.shift == "D": shift_counts["Jour"] += 2 
        elif a.shift == "N": shift_counts["Nuit"] += 2
        elif a.shift == "S": shift_counts["Soir"] += 1
            
    fig = px.pie(values=list(shift_counts.values()), names=list(shift_counts.keys()))
    st.plotly_chart(fig, use_container_width=True)

def _render_by_shift(state):
    st.subheader("Affectations par poste")
    st.write("Shift details go here.")

def _render_stats(state):
    st.subheader("Statistiques par personne")
    st.write("Person stats go here.")
