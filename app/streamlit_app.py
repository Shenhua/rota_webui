"""
Rota Optimizer — Streamlit Web UI
=================================
Pair-based scheduling with OR-Tools CP-SAT solver.
"""
import sys
import os
import streamlit as st

# Add src and project root to python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from app.state.session import SessionStateManager
from app.components.styling import apply_styling
from app.views.inputs import render_inputs
from app.views.dashboard import render_dashboard
from app.views.export import render_downloads

# Solver logic (still needed for the "run optimization" trigger)
from app.components.utils import get_solver_config, get_weekend_config
from rota.solver.optimizer import optimize_with_cache
from rota.solver.edo import build_edo_plan
from rota.solver.staffing import derive_staffing
from rota.solver.validation import validate_schedule, calculate_fairness
from rota.solver.weekend import WeekendSolver, WeekendConfig

def main():
    # 1. Init
    SessionStateManager.init_state()
    state = SessionStateManager()
    apply_styling()
    
    st.title("📅 Rota Optimizer — Planification en Binôme")
    
    # 2. Sidebar (Inputs)
    render_inputs(state)
    
    # 3. Optimization Logic (Triggered from Sidebar)
    _handle_optimization(state)
    _handle_weekend_optimization(state)
    
    # 4. Main Tabs
    labels = ["📈 Tableau de bord"]
    if state.schedule and state.schedule.status in ["optimal", "feasible"]:
        labels.append("📥 Téléchargements")
    if state.w_result and state.w_result.status in ["OPTIMAL", "FEASIBLE"]:
        labels.append("📅 Week-end")
         
    tabs = st.tabs(labels)
    
    with tabs[0]:
        render_dashboard(state)
        
    tab_idx = 1
    if len(labels) > 1 and "Téléchargements" in labels:
        with tabs[tab_idx]:
            render_downloads(state)
        tab_idx += 1
    
    if "Week-end" in labels:
        with tabs[tab_idx]:
            _render_weekend_dashboard(state)

def _handle_optimization(state: SessionStateManager):
    """Run optimization if triggered."""
    if st.session_state.get("trigger_optimize"):
        solver_cfg = get_solver_config()
        custom_staffing = None # Placeholder for now
        weekend_config = None # Placeholder for now

        if state.trigger_optimize:
            with st.spinner("🚀 Optimisation en cours..."):
                # Run/Resume optimization
                schedule, seed, score, study_hash = optimize_with_cache(
                    people=state.people,
                    config=solver_cfg,
                    tries=state.config_tries,
                    seed=None if state.config_seed == 0 else state.config_seed,
                    cohort_mode=state.fairness.fairness_mode if state.fairness else "by-wd",
                    custom_staffing=custom_staffing,
                    weekend_config=weekend_config,
                )
                
                # Update state with result
                state.schedule = schedule
                state.best_seed = seed
                state.best_score = score
                state.study_hash = study_hash
                state.trigger_optimize = False  # Reset trigger

                # Result processing
                if schedule and schedule.status in ["optimal", "feasible"]:
                    # Post-process artifacts
                    edo_plan = build_edo_plan(state.people, state.config_weeks)
                    state.edo_plan = edo_plan
                    
                    # Staffing verification
                    if not state.people:
                        st.error("❌ Erreur interne: Liste du personnel vide ou non initialisée.")
                        return

                    staffing = derive_staffing(state.people, state.config_weeks, edo_plan.plan, custom_staffing=custom_staffing)
                    state.staffing = staffing
                    
                    # Validation & Fairness
                    validation = validate_schedule(schedule, state.people, edo_plan, staffing)
                    state.validation = validation
                    
                    fairness_mode = solver_cfg.fairness_mode.value if hasattr(solver_cfg.fairness_mode, 'value') else "by-wd"
                    fairness = calculate_fairness(schedule, state.people, fairness_mode)
                    state.fairness = fairness
                    
                    st.success(f"✅ Solution trouvée! Score: {score:.1f}")
                else:
                    st.error("❌ Aucune solution réalisable trouvée.")

def _handle_weekend_optimization(state: SessionStateManager):
    """Run weekend solver if needed."""
    # Placeholder: Logic to run weekend solver if merge_calendars is True
    # or if triggered explicitly. For now, we focus on the main wiring.
    pass

def _render_weekend_dashboard(state: SessionStateManager):
    """Render the weekend schedule dashboard."""
    import pandas as pd
    
    st.header("📅 Planning Week-end")
    
    w_result = state.w_result
    if not w_result or w_result.status not in ["OPTIMAL", "FEASIBLE"]:
        st.warning("Aucun résultat week-end disponible.")
        return
    
    # KPIs
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Statut", "✅ Optimal" if w_result.status == "OPTIMAL" else "⚠️ Faisable")
    with col2:
        st.metric("Score", f"{w_result.score:.1f}" if hasattr(w_result, 'score') else "N/A")
    with col3:
        st.metric("Temps", f"{w_result.solve_time:.1f}s" if hasattr(w_result, 'solve_time') else "N/A")
    
    st.divider()
    
    # Weekend assignments matrix
    st.subheader("🗓️ Affectations Samedi / Dimanche")
    
    if hasattr(w_result, 'assignments') and w_result.assignments:
        we_data = []
        for a in w_result.assignments:
            we_data.append({
                "Semaine": f"S{a.week}",
                "Jour": "Sam" if a.day == "Sam" else "Dim",
                "Quart": {"D": "Jour", "S": "Soir", "N": "Nuit"}.get(a.shift, a.shift),
                "Personne A": a.person_a or "-",
                "Personne B": a.person_b or "-" if hasattr(a, 'person_b') else "-",
            })
        
        df_we = pd.DataFrame(we_data)
        st.dataframe(df_we, use_container_width=True, hide_index=True)
    else:
        st.info("Aucune affectation week-end trouvée.")

if __name__ == "__main__":
    main()