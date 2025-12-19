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
    """Render a standalone weekend dashboard (for separate mode) - mirrors weekday structure."""
    import pandas as pd
    import plotly.express as px
    
    st.header("📅 Planning Week-end")
    
    w_result = state.w_result
    if not w_result or w_result.status not in ["OPTIMAL", "FEASIBLE"]:
        st.warning("Aucun résultat week-end disponible.")
        return
    
    # === HERO KPIs ===
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Statut", "✅ Optimal" if w_result.status == "OPTIMAL" else "⚠️ Faisable")
    with col2:
        total_shifts = len(w_result.assignments)
        st.metric("Affectations", f"{total_shifts}")
    with col3:
        weeks = state.config_weeks or 12
        required = weeks * 4 * 2  # 4 shifts per weekend × 2 staff
        coverage_pct = (total_shifts / required * 100) if required > 0 else 0
        st.metric("Couverture", f"{coverage_pct:.0f}%")
    with col4:
        solve_time = getattr(w_result, 'solve_time', 0)
        st.metric("Temps", f"{solve_time:.1f}s")
    
    st.divider()
    
    # === TABS (mirroring weekday structure) ===
    t1, t2, t3, t4 = st.tabs(["📊 Planning", "📅 Couverture", "👥 Personnes", "📈 Analyses"])
    
    # === TAB 1: PLANNING MATRIX ===
    with t1:
        st.subheader("🗓️ Affectations Samedi / Dimanche")
        
        if hasattr(w_result, 'assignments') and w_result.assignments:
            # Group by person for better display
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
                
                # Create merged cell headers using MultiIndex
                new_cols = []
                for w in range(1, min(weeks + 1, 13)):
                    for d in ["Sam", "Dim"]:
                         new_cols.append((f"Semaine {w}", d))
                
                if len(df.columns) == len(new_cols):
                    df.columns = pd.MultiIndex.from_tuples(new_cols)
                
                def color_shift(val):
                    colors = {
                        "J": "background-color: #DDEEFF; color: #333; font-weight: bold;",
                        "N": "background-color: #E6CCFF; color: #333; font-weight: bold;",
                        "OFF": "background-color: #F8F8F8; color: #BBB;",
                    }
                    return colors.get(val, "")
                
                st.dataframe(df.style.map(color_shift), width="stretch", height=400)
            else:
                st.info("Aucune affectation week-end.")
        else:
            st.info(f"Aucune affectation. Statut: {w_result.status}")
    
    # === TAB 2: COUVERTURE ===
    with t2:
        st.subheader("📅 Calendrier de Couverture Week-end")
        st.caption("🟢 Couvert | 🟡 Partiel | 🔴 Manque")
        
        weeks = state.config_weeks or 12
        coverage_data = []
        
        for w in range(1, weeks + 1):
            row = {"Semaine": f"S{w}"}
            for we_day in ["Sam", "Dim"]:
                day_assignments = [a for a in w_result.assignments if a.week == w and a.day == we_day]
                filled = len(day_assignments)
                required = 4  # 2 shifts × 2 staff per shift
                
                pct = (filled / required * 100) if required > 0 else 100
                if pct >= 100:
                    row[we_day] = "✅"
                elif pct >= 50:
                    row[we_day] = f"⚠️ {int(pct)}%"
                else:
                    row[we_day] = f"❌ {int(pct)}%"
            coverage_data.append(row)
        
        df_cov = pd.DataFrame(coverage_data)
        
        def color_coverage(val):
            if "✅" in str(val):
                return "background-color: #D4EDDA; color: #155724;"
            elif "⚠️" in str(val):
                return "background-color: #FFF3CD; color: #856404;"
            elif "❌" in str(val):
                return "background-color: #F8D7DA; color: #721C24; font-weight: bold;"
            return ""
        
        styled_cov = df_cov.style.map(color_coverage, subset=["Sam", "Dim"])
        st.dataframe(styled_cov, width="stretch", hide_index=True)
    
    # === TAB 3: PERSONNES ===
    with t3:
        st.subheader("Statistiques par Personne (Week-end)")
        
        # Count shifts per person
        person_counts = {}
        for a in w_result.assignments:
            name = a.person.name
            person_counts[name] = person_counts.get(name, 0) + 1
        
        person_data = [{"Nom": name, "Shifts WE": count} for name, count in sorted(person_counts.items())]
        
        if person_data:
            df_person = pd.DataFrame(person_data)
            st.dataframe(df_person, width="stretch", hide_index=True)
        else:
            st.info("Aucune donnée de personne.")
    
    # === TAB 4: ANALYSES ===
    with t4:
        st.subheader("📈 Analyses Week-end")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**Répartition par jour/shift**")
            we_counts = {"Sam D": 0, "Sam N": 0, "Dim D": 0, "Dim N": 0}
            for a in w_result.assignments:
                key = f"{a.day} {a.shift}"
                if key in we_counts:
                    we_counts[key] += 1
            
            fig = px.pie(
                values=list(we_counts.values()),
                names=list(we_counts.keys()),
                color_discrete_sequence=["#C8E6C9", "#A5D6A7", "#81C784", "#66BB6A"]
            )
            fig.update_layout(margin=dict(l=20, r=20, t=30, b=20), height=300)
            st.plotly_chart(fig, width="stretch")
        
        with col2:
            st.write("**Top 10 shifts WE par personne**")
            sorted_counts = sorted(person_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            if sorted_counts:
                df_top = pd.DataFrame(sorted_counts, columns=["Personne", "Shifts"])
                fig_bar = px.bar(df_top, x="Personne", y="Shifts", color_discrete_sequence=["#4CAF50"])
                fig_bar.update_layout(margin=dict(l=20, r=20, t=30, b=20), height=300)
                st.plotly_chart(fig_bar, width="stretch")

if __name__ == "__main__":
    main()