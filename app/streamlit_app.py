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
    
    # 4. Main Tabs - Architecture depends on merge_calendars mode
    has_week_result = state.schedule and state.schedule.status in ["optimal", "feasible"]
    has_weekend_result = state.w_result and state.w_result.status in ["OPTIMAL", "FEASIBLE"]
    
    if state.merge_calendars:
        # MERGED MODE: Single dashboard with Lun-Dim integrated
        labels = ["📈 Tableau de bord"]
        if has_week_result:
            labels.append("📥 Téléchargements")
        
        tabs = st.tabs(labels)
        
        with tabs[0]:
            render_dashboard(state, merged_mode=True)
        
        if len(labels) > 1:
            with tabs[1]:
                render_downloads(state)
    else:
        # SEPARATE MODE: Two dashboards (Semaine + Week-end)
        labels = []
        if has_week_result:
            labels.append("📈 Semaine")
        if has_weekend_result:
            labels.append("📅 Week-end")
        if has_week_result:
            labels.append("📥 Téléchargements")
        
        if not labels:
            st.info("👋 Veuillez lancer une optimisation pour voir les résultats.")
            return
        
        tabs = st.tabs(labels)
        tab_idx = 0
        
        if has_week_result:
            with tabs[tab_idx]:
                render_dashboard(state, merged_mode=False)
            tab_idx += 1
        
        if has_weekend_result:
            with tabs[tab_idx]:
                _render_weekend_only_dashboard(state)
            tab_idx += 1
        
        if has_week_result:
            with tabs[tab_idx]:
                render_downloads(state)

def _handle_optimization(state: SessionStateManager):
    """Run optimization if triggered."""
    if st.session_state.get("trigger_optimize"):
        solver_cfg = get_solver_config()
        custom_staffing = None # Placeholder for now
        weekend_config = None # Placeholder for now

        if state.trigger_optimize:
            with st.spinner("🚀 Optimisation en cours..."):
                # Get fairness mode from config
                fm = solver_cfg.fairness_mode
                fm_str = fm.value if hasattr(fm, 'value') else str(fm)
                
                # Run/Resume optimization
                schedule, seed, score, study_hash = optimize_with_cache(
                    people=state.people,
                    config=solver_cfg,
                    tries=state.config_tries,
                    seed=None if state.config_seed == 0 else state.config_seed,
                    cohort_mode=fm_str,
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
    """Run weekend solver if a valid schedule exists (runs in both merged and separate modes)."""
    # Only run if we have a valid weekday schedule
    if not state.schedule or state.schedule.status not in ["optimal", "feasible"]:
        return
    
    # Only run if we don't already have a weekend result with assignments
    # (Re-run if previous result had 0 assignments - likely cached from buggy solver)
    if state.w_result and state.w_result.status in ["OPTIMAL", "FEASIBLE"]:
        if hasattr(state.w_result, 'assignments') and len(state.w_result.assignments) > 0:
            return  # Already have valid weekend result
    
    # Get weekend config
    we_config_dict = get_weekend_config()
    
    try:
        we_config = WeekendConfig(
            num_weeks=state.config_weeks,  # Required first argument
            max_weekends_per_month=we_config_dict.get("max_weekends_month", 2),
            forbid_consecutive_nights=we_config_dict.get("forbid_consecutive_nights", True),
        )
        
        people = state.people or []
        
        with st.spinner("🗓️ Optimisation week-end en cours..."):
            solver = WeekendSolver(
                config=we_config,
                people=people,
            )
            
            w_result = solver.solve()
            state.w_result = w_result
            
            if w_result.status in ["OPTIMAL", "FEASIBLE"]:
                st.success(f"✅ Week-end optimisé! {len(w_result.assignments)} affectations")
            else:
                st.warning(f"⚠️ Week-end: {w_result.status}")
                
    except Exception as e:
        import traceback
        st.error(f"❌ Erreur week-end: {e}")
        st.code(traceback.format_exc())

def _render_weekend_only_dashboard(state: SessionStateManager):
    """Render a standalone weekend dashboard (for separate mode)."""
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
        score = getattr(w_result, 'score', 0)
        st.metric("Score", f"{score:.1f}")
    with col3:
        solve_time = getattr(w_result, 'solve_time', 0)
        st.metric("Temps", f"{solve_time:.1f}s")
    
    st.divider()
    
    # Weekend assignments matrix - organized by person
    st.subheader("🗓️ Affectations Samedi / Dimanche")
    
    if hasattr(w_result, 'assignments') and w_result.assignments:
        # Group by person for better display
        people = state.people or []
        weeks = state.config_weeks or 12
        
        # Build person-centric matrix
        person_map = {}
        for a in w_result.assignments:
            name = a.person.name if hasattr(a, 'person') and a.person else "?"
            key = (name, a.week, a.day)
            shift = {"D": "J", "S": "S", "N": "N"}.get(a.shift, a.shift)
            person_map[key] = shift
        
        # Build matrix data
        names = sorted(set(a.person.name for a in w_result.assignments if hasattr(a, 'person')))
        matrix_data = []
        
        for name in names:
            row = {"Nom": name}
            for w in range(1, min(weeks + 1, 13)):  # Limit display
                for d in ["Sam", "Dim"]:
                    col = f"S{w}_{d}"
                    val = person_map.get((name, w, d), "OFF")
                    row[col] = val
            matrix_data.append(row)
        
        if matrix_data:
            df = pd.DataFrame(matrix_data)
            df = df.set_index("Nom")
            
            def color_shift(val):
                colors = {
                    "J": "background-color: #DDEEFF; color: #333; font-weight: bold;",
                    "S": "background-color: #FFE4CC; color: #333; font-weight: bold;",
                    "N": "background-color: #E6CCFF; color: #333; font-weight: bold;",
                    "OFF": "background-color: #F8F8F8; color: #BBB;",
                }
                return colors.get(val, "")
            
            st.dataframe(df.style.map(color_shift), use_container_width=True, height=400)
        else:
            st.info("Aucune affectation week-end.")
    else:
        st.info(f"Aucune affectation. Statut: {w_result.status}")

if __name__ == "__main__":
    main()