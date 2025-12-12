"""
Input View (Sidebar)
====================
Handles user inputs, file loading, and configuration.
"""
import streamlit as st
from typing import List, Optional
import pandas as pd

from app.components.sidebar import render_logo, render_file_upload, render_team_editor, render_solver_config
from app.state.session import SessionStateManager
from rota.models.person import Person

def render_inputs(state: SessionStateManager):
    """Render the sidebar inputs and update state."""
    with st.sidebar:
        render_logo()
        
        st.header("1. Équipe")
        
        # File Upload
        uploaded_file = render_file_upload()
        
        # Team Editor (if people loaded)
        state_people = state.people
        if uploaded_file or state_people:
             # Logic from original sidebar to load/edit people
             # We reuse the existing components for now, but facilitate state update
             people = render_team_editor(uploaded_file)
             if people:
                 st.session_state.people = people  # Update raw state for compatibility
        
        st.divider()
        
        st.header("2. Configuration")
        render_solver_config()
        
        # Trigger button
        if st.button("🚀 Lancer l'optimisation", type="primary", use_container_width=True):
            st.session_state.trigger_optimize = True
