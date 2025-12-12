import streamlit as st

from rota.models.rules import RULES


def init_session_state():
    """Initialize session state variables if they don't exist."""
    
    # Configuration defaults
    if "config_weeks" not in st.session_state:
        st.session_state.config_weeks = RULES.default_weeks
    if "config_tries" not in st.session_state:
        st.session_state.config_tries = RULES.default_tries
    if "config_seed" not in st.session_state:
        st.session_state.config_seed = 0
    if "config_time_limit" not in st.session_state:
        st.session_state.config_time_limit = 60
        
    # Global options
    if "merge_calendars" not in st.session_state:
        st.session_state.merge_calendars = False
        
    # Solver state
    if "schedule" not in st.session_state:
        st.session_state.schedule = None
    if "w_result" not in st.session_state:
        st.session_state.w_result = None
        
    # Verification state
    if "validation" not in st.session_state:
        st.session_state.validation = None
    if "fairness" not in st.session_state:
        st.session_state.fairness = None
    if "best_seed" not in st.session_state:
        st.session_state.best_seed = None
    if "best_score" not in st.session_state:
        st.session_state.best_score = None
