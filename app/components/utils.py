import streamlit as st

from rota.models.constraints import FairnessMode, SolverConfig


def get_solver_config() -> SolverConfig:
    """Build SolverConfig from session state."""
    
    cfg = SolverConfig()
    
    # Basic
    cfg.weeks = st.session_state.get("config_weeks", 12)
    cfg.time_limit_seconds = st.session_state.get("config_time_limit", 60)
    
    # Advanced Week
    cfg.forbid_night_to_day = st.session_state.get("cfg_forbid_night_to_day", True)
    cfg.edo_enabled = st.session_state.get("cfg_edo_enabled", True)
    cfg.max_nights_sequence = st.session_state.get("cfg_max_nights_seq", 3)
    cfg.max_consecutive_days = st.session_state.get("cfg_max_consecutive_days", 6)
    
    # Fairness
    fm_raw = st.session_state.get("cfg_fairness_mode", "by-wd")
    # Handle tuple from selectbox format: ("by-wd", "Par jours/semaine")
    fm_str = fm_raw[0] if isinstance(fm_raw, tuple) else fm_raw
    if fm_str == "none":
        cfg.fairness_mode = FairnessMode.NONE
    elif fm_str == "by-team":
        cfg.fairness_mode = FairnessMode.BY_TEAM
    else:
        cfg.fairness_mode = FairnessMode.BY_WORKDAYS
        
    cfg.night_fairness_weight = st.session_state.get("cfg_weight_night_fairness", 10.0)
    cfg.evening_fairness_weight = st.session_state.get("cfg_weight_eve_fairness", 3.0)
    
    # Note: Staffing customization (req_pairs_D etc) is handled by passing custom_staffing 
    # to derive_staffing, NOT by SolverConfig directly usually.
    # But wait, SolverConfig doesn't hold staffing requirements in my implementation yet?
    # staffing.py uses FIXED_STAFFING or custom_staffing arg.
    # So we need to return custom_staffing dict separate from SolverConfig.
    
    return cfg

def get_custom_staffing() -> dict:
    """Get custom staffing dict from session state."""
    return {
        "D": st.session_state.get("cfg_req_pairs_D", 4),
        "S": st.session_state.get("cfg_req_solos_S", 1),
        "N": st.session_state.get("cfg_req_pairs_N", 1),
    }

def get_weekend_config() -> dict:
    """Get weekend configuration dict."""
    return {
        "max_weekends_month": st.session_state.get("cfg_max_weekends_month", 2),
        "forbid_consecutive_nights": st.session_state.get("cfg_forbid_consecutive_nights_we", True),
        "weights": {
            "fairness": st.session_state.get("cfg_weight_w_fairness", 10),
            "split": st.session_state.get("cfg_weight_w_split", 5),
            "24h": st.session_state.get("cfg_weight_w_24h", 5),
            "consecutive": st.session_state.get("cfg_weight_w_consecutive", 50),
        }
    }
