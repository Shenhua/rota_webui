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
from app.components.utils import get_solver_config, get_solver_config_dict, get_weekend_config
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
    
    st.title("📅 Rota Optimizer — Pair Scheduling")
    
    # 2. Sidebar (Inputs)
    render_inputs(state)
    
    # 3. Optimization Logic (Triggered from Sidebar)
    _handle_optimization(state)
    _handle_weekend_optimization(state)
    
    # 4. Main Tabs
    labels = ["📈 Tableau de bord"]
    if state.schedule and state.schedule.status in ["optimal", "feasible"]:
         labels.append("📥 Téléchargements")
         
    tabs = st.tabs(labels)
    
    with tabs[0]:
        render_dashboard(state)
        
    if len(tabs) > 1:
        with tabs[1]:
            render_downloads(state)

def _handle_optimization(state: SessionStateManager):
    """Run optimization if triggered."""
    if st.session_state.get("trigger_optimize"):
        st.session_state.trigger_optimize = False  # Reset
        
        with st.spinner("Optimisation Semaine en cours..."):
            solver_cfg = get_solver_config()
            
            # Using custom staffing if not stress test (placeholder for now)
            schedule, best_seed, best_score, study_hash = optimize_with_cache(
                state.people, 
                solver_cfg, 
                tries=state.config_tries, 
                seed=state.config_seed if state.config_seed > 0 else None,
                cohort_mode=solver_cfg.fairness_mode.value,
                # use_cache=True # Default
            )
            
            if schedule.status in ["optimal", "feasible"]:
                # Post-process artifacts
                edo_plan = build_edo_plan(state.people, state.config_weeks)
                state.edo_plan = edo_plan
                
                state.staffing = derive_staffing(state.people, state.config_weeks, edo_plan.plan)
                state.validation = validate_schedule(schedule, state.people, edo_plan, state.staffing)
                state.fairness = calculate_fairness(schedule, state.people, solver_cfg.fairness_mode.value)
                
                state.schedule = schedule
                state.best_seed = best_seed
                state.best_score = best_score
                state.study_hash = study_hash
                st.success(f"Solution trouvée! Score: {best_score:.0f}")

def _handle_weekend_optimization(state: SessionStateManager):
    """Run weekend solver if needed."""
    # Placeholder: Logic to run weekend solver if merge_calendars is True
    # or if triggered explicitly. For now, we focus on the main wiring.
    pass

if __name__ == "__main__":
    main()