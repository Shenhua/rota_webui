"""
Study Browser UI Component
===========================
Streamlit component for browsing and loading past optimization studies.
"""
from datetime import datetime
from typing import Callable, Optional, Tuple

import streamlit as st

from rota.solver.study_manager import StudyManager, StudySummary, compute_study_hash
from rota.models.constraints import SolverConfig
from rota.models.person import Person


def render_study_info(
    config: SolverConfig,
    people: list,
    on_load: Optional[Callable] = None,
) -> Optional[Tuple[str, StudySummary]]:
    """
    Render study info in sidebar if matching study exists.
    
    Args:
        config: Current solver config
        people: Current team
        on_load: Callback when user clicks Load Best
        
    Returns:
        (study_hash, summary) if study exists, else None
    """
    if not people:
        return None
    
    manager = StudyManager()
    study_hash = compute_study_hash(config, people)
    
    if not manager.study_exists(study_hash):
        return None
    
    summary = manager.get_study_summary(study_hash)
    if not summary:
        return None
    
    # Display study info
    with st.container():
        st.markdown("---")
        st.markdown("**📊 Previous Run Found**")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Best Score", f"{summary.best_score:.1f}")
        with col2:
            st.metric("Trials", summary.total_trials)
        
        st.caption(f"Seed: {summary.best_seed} | {summary.updated_at.strftime('%Y-%m-%d %H:%M')}")
        
        col_load, col_continue = st.columns(2)
        with col_load:
            if st.button("📥 Load Best", key="load_best_study"):
                if on_load:
                    on_load(study_hash)
                return (study_hash, summary)
        
        with col_continue:
            st.caption("Or run optimizer to try more seeds")
    
    return (study_hash, summary)


def render_study_browser(
    on_select: Optional[Callable[[str], None]] = None,
) -> Optional[StudySummary]:
    """
    Render a study browser in an expander.
    
    Args:
        on_select: Callback when user selects a study
        
    Returns:
        Selected study summary, if any
    """
    manager = StudyManager()
    studies = manager.list_studies(limit=10)
    
    if not studies:
        st.info("No previous studies found.")
        return None
    
    with st.expander("📚 Browse Past Studies", expanded=False):
        for study in studies:
            col1, col2, col3 = st.columns([3, 2, 1])
            
            with col1:
                st.markdown(f"**{study.study_name}**")
                st.caption(f"{study.team_size} people, {study.weeks} weeks")
            
            with col2:
                st.metric("Score", f"{study.best_score:.1f}", label_visibility="collapsed")
                st.caption(f"{study.total_trials} trials")
            
            with col3:
                if st.button("Load", key=f"load_{study.study_hash}"):
                    if on_select:
                        on_select(study.study_hash)
                    return study
            
            st.divider()
    
    return None


def load_study_result(study_hash: str, people: list = None, config = None):
    """
    Load best result from a study into session state.
    
    Sets:
        st.session_state.schedule
        st.session_state.validation
        st.session_state.fairness
        st.session_state.edo_plan
        st.session_state.staffing
        st.session_state.best_seed
        st.session_state.best_score
        st.session_state.study_hash
    """
    import json
    from rota.solver.pairs import PairSchedule
    from rota.solver.edo import build_edo_plan
    from rota.solver.staffing import derive_staffing
    from rota.solver.validation import calculate_fairness, validate_schedule
    
    manager = StudyManager()
    trial = manager.get_best_trial(study_hash)
    
    if not trial:
        st.error("Could not load study result.")
        return False
    
    # Get study summary to load config/team if not provided
    saved_config = manager.get_study_config(study_hash)
    if saved_config:
        # Update session state config to match loaded study
        st.session_state["config_weeks"] = saved_config.get("weeks", 12)
        st.session_state["cfg_forbid_night_to_day"] = saved_config.get("forbid_night_to_day", True)
        st.session_state["cfg_edo_enabled"] = saved_config.get("edo_enabled", True)
        st.session_state["cfg_max_nights_seq"] = saved_config.get("max_nights_sequence", 3)
        st.session_state["cfg_max_consecutive_days"] = saved_config.get("max_consecutive_days", 6)
        st.session_state["cfg_forbid_contractor_pairs"] = saved_config.get("forbid_contractor_pairs", True)
        
        # Restore Fairness
        st.session_state["cfg_fairness_mode"] = saved_config.get("fairness_mode", "by-wd")
        st.session_state["cfg_weight_night_fairness"] = saved_config.get("night_fairness_weight", 10.0)
        st.session_state["cfg_weight_eve_fairness"] = saved_config.get("evening_fairness_weight", 3.0)
        
        # Restore Staffing (if saved in config_json)
        if "custom_staffing" in saved_config:
            staffing = saved_config["custom_staffing"]
            st.session_state["cfg_req_pairs_D"] = staffing.get("D", 4)
            st.session_state["cfg_req_solos_S"] = staffing.get("S", 1)
            st.session_state["cfg_req_pairs_N"] = staffing.get("N", 1)
            
        # Restore Weekend Config (if saved in config_json)
        if "weekend_config" in saved_config:
            wc = saved_config["weekend_config"]
            st.session_state["cfg_max_weekends_month"] = wc.get("max_weekends_month", 2)
            st.session_state["cfg_forbid_consecutive_nights_we"] = wc.get("forbid_consecutive_nights", True)
            
            # Restore weights if present
            weights = wc.get("weights", {})
            st.session_state["cfg_weight_w_fairness"] = weights.get("fairness", 10)
            st.session_state["cfg_weight_w_split"] = weights.get("split", 5)
            st.session_state["cfg_weight_w_24h"] = weights.get("24h", 5)
            st.session_state["cfg_weight_w_consecutive"] = weights.get("consecutive", 50)
        
        # Also ensure st.session_state["trigger_optimize"] doesn't re-fire

        st.session_state["config_restored"] = True  # Signal that we're in sync

    summary = manager.get_study_summary(study_hash)
    
    # Load schedule
    schedule = manager.load_schedule_from_trial(trial)
    
    # We need people and config to compute edo_plan, validation, etc.
    # Get from session state if not provided
    if people is None:
        people = st.session_state.get("people", [])
    if config is None:
        from app.components.utils import get_solver_config
        config = get_solver_config()
    
    if not people:
        st.warning("Cannot load validation data - team not found in session.")
        # Still load schedule
        st.session_state.schedule = schedule
        st.session_state.best_seed = trial.seed
        st.session_state.best_score = trial.score
        st.session_state.study_hash = study_hash
        st.success(f"✅ Loaded schedule (score: {trial.score:.1f}, seed: {trial.seed})")
        return True
    
    # Compute matching edo_plan and staffing
    weeks = schedule.weeks or config.weeks
    edo_plan = build_edo_plan(people, weeks)
    staffing = derive_staffing(people, weeks, edo_plan.plan)
    
    # Compute validation and fairness
    validation = validate_schedule(schedule, people, edo_plan, staffing)
    fairness_mode = config.fairness_mode.value if hasattr(config.fairness_mode, 'value') else str(config.fairness_mode)
    fairness = calculate_fairness(schedule, people, fairness_mode)
    
    # Store all in session state
    st.session_state.schedule = schedule
    st.session_state.validation = validation
    st.session_state.fairness = fairness
    st.session_state.edo_plan = edo_plan
    st.session_state.staffing = staffing
    st.session_state.best_seed = trial.seed
    st.session_state.best_score = trial.score
    st.session_state.study_hash = study_hash
    st.session_state.loaded_from_cache = True
    
    st.success(f"✅ Loaded best result (score: {trial.score:.1f}, seed: {trial.seed})")
    return True
