"""
Rota Optimizer — Streamlit UI
=============================
Simplified UI for staff scheduling with OR-Tools solver.
"""
import io
import tempfile
from typing import List, Dict, Optional

import pandas as pd
import streamlit as st

# Import from new packages
from rota.models.person import Person
from rota.models.schedule import Schedule
from rota.models.constraints import SolverConfig, WeekendMode, FairnessMode
from rota.models.shift import ShiftType, WEEKDAYS, WEEKEND, ALL_DAYS
from rota.io.csv_loader import load_team, team_to_dataframe
from rota.io.excel_export import export_to_excel, export_to_csv
from rota.solver.engine import solve
from rota.ui.normalize import normalize_assignments, apply_edo_policy


# ============ Page Config ============
st.set_page_config(
    page_title="Rota Optimizer",
    page_icon="📅",
    layout="wide",
)

st.title("📅 Rota Optimizer")
st.caption("Staff scheduling with constraint programming (OR-Tools CP-SAT)")


# ============ Session State ============
if "team" not in st.session_state:
    st.session_state.team = []
if "schedule" not in st.session_state:
    st.session_state.schedule = None


# ============ Sidebar ============
with st.sidebar:
    st.header("📥 Team Data")
    
    csv_file = st.file_uploader(
        "Upload team CSV",
        type=["csv"],
        help="CSV with columns: name, workdays_per_week, etc."
    )
    
    if csv_file is not None:
        try:
            df = pd.read_csv(csv_file)
            st.session_state.team = load_team(df)
            st.success(f"Loaded {len(st.session_state.team)} people")
        except Exception as e:
            st.error(f"Error loading CSV: {e}")
    
    st.divider()
    
    # ============ Solver Settings ============
    st.header("⚙️ Settings")
    
    weeks = st.number_input("Weeks", min_value=1, max_value=24, value=4)
    
    weekend_mode = st.selectbox(
        "Weekend scheduling",
        options=["disabled", "integrated"],
        index=0,
        help="disabled = Mon-Fri only, integrated = full week"
    )
    
    with st.expander("Constraints", expanded=False):
        forbid_night_to_day = st.checkbox("No work after night", value=True)
        max_nights_seq = st.number_input("Max consecutive nights", 1, 7, 3)
        max_evenings_seq = st.number_input("Max consecutive evenings", 1, 7, 3)
        max_days_per_week = st.number_input("Max days per week", 1, 7, 5)
    
    with st.expander("Fairness", expanded=False):
        fairness_mode = st.selectbox(
            "Fairness mode",
            ["by-wd", "global", "none"],
            index=0,
            help="How to group people for fair distribution"
        )
    
    st.divider()
    
    # ============ Solve Button ============
    run_solver = st.button("🚀 Generate Schedule", type="primary", use_container_width=True)


# ============ Main Content ============
if run_solver:
    if not st.session_state.team:
        st.error("Please upload a team CSV first")
    else:
        # Build config
        config = SolverConfig(
            weeks=weeks,
            weekend_mode=WeekendMode(weekend_mode) if weekend_mode != "disabled" else WeekendMode.DISABLED,
            forbid_night_to_day=forbid_night_to_day,
            max_nights_sequence=max_nights_seq,
            max_evenings_sequence=max_evenings_seq,
            max_days_per_week=max_days_per_week,
            fairness_mode=FairnessMode(fairness_mode) if fairness_mode != "none" else FairnessMode.NONE,
        )
        
        with st.spinner("Solving..."):
            schedule = solve(st.session_state.team, config)
            st.session_state.schedule = schedule
        
        if schedule.status == "infeasible":
            st.error("No feasible schedule found. Try relaxing constraints.")
        else:
            st.success(f"✅ Schedule found! Status: {schedule.status}, Score: {schedule.score:.2f}")


# ============ Display Results ============
if st.session_state.schedule is not None:
    schedule = st.session_state.schedule
    people = st.session_state.team
    
    # Metrics row
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Weeks", schedule.weeks)
    col2.metric("People", schedule.people_count)
    col3.metric("Score", f"{schedule.score:.1f}")
    col4.metric("Solve Time", f"{schedule.solve_time_seconds:.2f}s")
    
    # Determine days
    days = ALL_DAYS if weekend_mode != "disabled" else WEEKDAYS
    
    # ============ Schedule Matrix ============
    st.subheader("📊 Schedule Matrix")
    
    matrix = schedule.to_matrix(days)
    if not matrix.empty:
        # Rename columns for display
        new_cols = [f"W{w} {d}" for w, d in matrix.columns]
        matrix.columns = new_cols
        
        # Color function
        def color_shift(val):
            colors = {
                "J": "background-color: #DDEEFF",
                "S": "background-color: #FFE4CC",
                "N": "background-color: #E6CCFF",
                "A": "background-color: #DDDDDD",
                "OFF": "background-color: #F5F5F5",
                "EDO": "background-color: #D8D8D8",
            }
            return colors.get(str(val).strip(), "")
        
        styled = matrix.style.applymap(color_shift)
        st.dataframe(styled, use_container_width=True, height=400)
    else:
        st.warning("No assignments to display")
    
    # ============ Per-Person Stats ============
    st.subheader("👥 Per-Person Statistics")
    
    stats = schedule.get_person_stats()
    if not stats.empty:
        st.dataframe(stats, use_container_width=True)
    
    # ============ Export ============
    st.subheader("📤 Export")
    
    col_xlsx, col_csv = st.columns(2)
    
    with col_xlsx:
        xlsx_buffer = io.BytesIO()
        export_to_excel(schedule, people, xlsx_buffer, days=days)
        xlsx_buffer.seek(0)
        st.download_button(
            "📥 Download Excel",
            data=xlsx_buffer,
            file_name="schedule.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    with col_csv:
        csv_buffer = io.StringIO()
        export_to_csv(schedule, csv_buffer)
        st.download_button(
            "📥 Download CSV",
            data=csv_buffer.getvalue(),
            file_name="schedule.csv",
            mime="text/csv"
        )


# ============ Team Display ============
if st.session_state.team:
    with st.expander("👥 Current Team", expanded=False):
        team_df = team_to_dataframe(st.session_state.team)
        st.dataframe(team_df, use_container_width=True)
else:
    st.info("👆 Upload a team CSV to get started")