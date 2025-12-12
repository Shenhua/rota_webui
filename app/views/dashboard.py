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
        
    # Diagnosis
    from app.services.diagnosis import DiagnosisService
    
    # Needs edo_plan and staffing (which are optional in state, but should be there if schedule is valid)
    edo_plan = state.edo_plan
    staffing = state.staffing
    
    if edo_plan and staffing:
        result = DiagnosisService.diagnose(schedule, state.people, validation, edo_plan, staffing)
        
        st.divider()
        st.subheader("📋 État du Planning")
        
        # Display main message based on type
        if result.scenario_type == "DEFICIT":
            st.error(f"❌ **{result.message}**")
            st.markdown("Le nombre d'agents est insuffisant pour couvrir la demande.")
            
            with st.expander("🚨 Détail des Besoins Externes (Contractors)", expanded=True):
                if result.details:
                    df_missing = pd.DataFrame(result.details)
                    total_people = df_missing["Besoins"].sum()
                    st.markdown(f"**Total à recruter: {total_people} personnes**")
                    st.dataframe(df_missing, use_container_width=True)
                else:
                    st.info("Aucun détail disponible.")
                    
        elif result.scenario_type == "SURPLUS":
            st.success(f"✅ **{result.message}**")
            st.markdown("Tous les besoins sont couverts et l'équipe a encore de la disponibilité.")
            
        else: # BALANCED
            st.warning("⚠️ **Planning Tendu / Équilibré**")
            st.markdown("L'équipe couvre exactement la charge (« Juste-à-temps »).")
    else:
        st.warning("⚠️ Impossible de calculer le diagnostic (données EDO/Staffing manquantes).")

    # === Secondary Metrics (Detailed) ===
    with st.expander("📈 Détails des métriques", expanded=False):
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Violations 48h", validation.rolling_48h_violations,
                    delta="CRITIQUE" if validation.rolling_48h_violations > 0 else None,
                    delta_color="inverse")
        with col2:
            st.metric("Nuit→Travail", validation.nuit_suivie_travail, 
                    delta="violations" if validation.nuit_suivie_travail > 0 else None,
                    delta_color="inverse")
        with col3:
            st.metric("Soir→Jour", validation.soir_vers_jour)
        with col4:
            st.metric("σ Nuits", f"{state.fairness.night_std:.2f}" if state.fairness else "N/A")
        with col5:
            st.metric("σ Soirs", f"{state.fairness.eve_std:.2f}" if state.fairness else "N/A")
        
        st.caption(f"🌱 Seed gagnant: {state.best_seed}")

    # === Capacity Analysis ===
    if staffing and edo_plan:
        with st.expander("📊 Analyse de Capacité", expanded=False):
            from rota.solver.capacity import calculate_capacity
            
            cap_analysis = calculate_capacity(schedule, state.people, staffing, edo_plan)
            
            # Summary row
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Capacité dispo.", f"{cap_analysis.net_capacity} jrs", 
                            delta=f"-{cap_analysis.total_edo_days} EDO")
            with col2:
                st.metric("Besoins totaux", f"{cap_analysis.total_required_person_shifts} shifts")
            with col3:
                st.metric("Affectés", f"{cap_analysis.total_assigned_person_shifts} shifts")
            with col4:
                balance_icon = "✅" if cap_analysis.capacity_balance >= 0 else "⚠️"
                st.metric(f"{balance_icon} Balance", f"{cap_analysis.capacity_balance:+d}")
            
            st.divider()
            
            # Per-shift breakdown
            st.markdown("**Par type de quart:**")
            shift_data = []
            for shift, data in cap_analysis.by_shift.items():
                shift_name = {"D": "Jour 🌅", "S": "Soir 🌆", "N": "Nuit 🌙"}.get(shift, shift)
                gap = data["gap"]
                shift_data.append({
                    "Quart": shift_name,
                    "Requis": data["required"],
                    "Affectés": data["assigned"],
                    "Écart": gap,
                    "Status": "✅" if gap <= 0 else f"❌ -{gap}"
                })
            st.dataframe(pd.DataFrame(shift_data), use_container_width=True, hide_index=True)
            
            # Recommendation
            st.divider()
            st.markdown("**💡 Recommandation:**")
            if cap_analysis.agents_needed > 0.5:
                st.error(f"⚠️ **Besoin d'environ {cap_analysis.agents_needed:.1f} agents supplémentaires** pour couvrir tous les créneaux.")
            elif cap_analysis.excess_agent_days > 10:
                st.success(f"✅ **Équipe bien dimensionnée**. {cap_analysis.excess_agent_days:.0f} jours-agent disponibles en marge.")
            else:
                st.info(f"ℹ️ L'équipe est à **{cap_analysis.utilization_percent:.0f}%** de sa capacité. Marge confortable.")
            
            # Violation breakdown by type (re-added here as per legacy)
            if validation.violations:
                st.divider()
                st.write("**Détail des violations:**")
                viol_types = {}
                for v in validation.violations:
                    viol_types[v.type] = viol_types.get(v.type, 0) + 1
                
                cols = st.columns(len(viol_types))
                for i, (vtype, count) in enumerate(viol_types.items()):
                    type_labels = {
                        "unfilled_slot": "🔴 Slots vides",
                        "night_followed_work": "🟠 Nuit→Travail",
                        "clopening": "🟡 Soir→Jour",
                        "48h_exceeded": "🔴 48h dépassé",
                        "duplicate": "⚠️ Doublon"
                    }
                    label = type_labels.get(vtype, vtype)
                    with cols[i]:
                        st.metric(label, count)

def _render_matrix(state):
    st.subheader("Matrice des affectations")
    st.caption("🔵 Jour | 🟠 Soir | 🟣 Nuit | ⬜ Admin | ⚪ OFF")
    
    schedule = state.schedule
    people = state.people
    weeks = state.config_weeks
    edo_plan = state.edo_plan
    
    # Pre-fetch assignments
    assign_map = schedule.get_person_day_matrix(code_map={"D":"J", "S":"S", "N":"N", "A":"A"})
    
    # Rebuild matrix data
    names = sorted([p.name for p in people])
    matrix_data = []
    
    for name in names:
        row = {"Nom": name}
        for w in range(1, weeks+1):
            has_edo = name in edo_plan.plan.get(w, set()) if edo_plan else False
            edo_assigned = False
            
            for d in JOURS:
                col = f"S{w}_{d}"
                val = assign_map.get((name, w, d), "OFF")
                
                # Check for unassigned EDO
                if val == "OFF" and has_edo and not edo_assigned:
                    # In a real impl we'd check strict EDO day, here simple approx
                    # We rely on the solver having placed the EDO as a gap, but display needs to know
                    # For now, simplistic: if off and is edo week, mark one OFF as EDO
                    # Better: check if this specific day is the EDO Fixed day or just an OFF
                    pass # Keep simple for now or logic gets complex rebuilding "EDO" label
                
                row[col] = val
        matrix_data.append(row)
        
    df = pd.DataFrame(matrix_data)
    # Ensure unique index
    df = df.drop_duplicates(subset=["Nom"]).set_index("Nom")
    
    # Color function
    def color_shift(val):
        colors = {
            "J": "background-color: #DDEEFF; color: #333; font-weight: bold;",
            "S": "background-color: #FFE4CC; color: #333; font-weight: bold;",
            "N": "background-color: #E6CCFF; color: #333; font-weight: bold;",
            "A": "background-color: #DDDDDD; color: #333; font-weight: bold;",
            "OFF": "background-color: #F8F8F8; color: #BBB;",
        }
        return colors.get(val, "")
        
    st.dataframe(df.style.map(color_shift), use_container_width=True, height=450)

def _render_coverage(state):
    st.subheader("📅 Calendrier de Couverture")
    st.caption("🟢 Couvert | 🟡 Partiel | 🔴 Manque")
    
    schedule = state.schedule
    weeks = state.config_weeks
    staffing = state.staffing

    if not staffing:
        st.warning("Données de staffing manquantes.")
        return

    # Calculate coverage per day per week
    coverage_data = []
    for w in range(1, weeks + 1):
        row = {"Semaine": f"S{w}"}
        ws = staffing.get(w)
        if not ws: continue
        
        for d in JOURS:
            # Required slots for this day
            req_d = ws.slots[d].get("D", 0) * 2
            req_s = ws.slots[d].get("S", 0)
            req_n = ws.slots[d].get("N", 0) * 2
            total_required = req_d + req_s + req_n
            
            # Actual filled
            day_assignments = schedule.get_day_assignments(w, d)
            filled = sum(
                (1 if a.person_a else 0) + (1 if a.person_b else 0)
                for a in day_assignments
            )
            
            pct = (filled / total_required * 100) if total_required > 0 else 100
            if pct >= 100:
                row[d] = "✅"
            elif pct >= 80:
                row[d] = f"⚠️ {int(pct)}%"
            else:
                row[d] = f"❌ {int(pct)}%"
        coverage_data.append(row)
    
    df_coverage = pd.DataFrame(coverage_data)
    
    # Color function for coverage
    def color_coverage(val):
        if "✅" in str(val):
            return "background-color: #D4EDDA; color: #155724;"
        elif "⚠️" in str(val):
            return "background-color: #FFF3CD; color: #856404;"
        elif "❌" in str(val):
            return "background-color: #F8D7DA; color: #721C24; font-weight: bold;"
        return ""
    
    styled_cov = df_coverage.style.map(color_coverage, subset=JOURS)
    st.dataframe(styled_cov, use_container_width=True, hide_index=True)
    
    # Show gap details if any
    validation = state.validation
    if validation and validation.slots_vides > 0:
        with st.expander("Voir détails des manques", expanded=False):
            gaps = [v for v in validation.violations if v.type in {"unfilled_slot", "incomplete_pair"}]
            for v in gaps[:20]:
                st.write(f"• **S{v.week} {v.day}** - {v.shift}: {v.message}")
            if len(gaps) > 20:
                st.write(f"... et {len(gaps) - 20} autres")

def _render_charts(state):
    st.subheader("📈 Analytics")
    schedule = state.schedule
    weeks = state.config_weeks
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Workload distribution pie chart
        st.write("**Répartition des quarts**")
        shift_counts = {"Jour": 0, "Soir": 0, "Nuit": 0}
        for a in schedule.assignments:
            if a.shift == "D":
                shift_counts["Jour"] += (1 if a.person_a else 0) + (1 if a.person_b else 0)
            elif a.shift == "S":
                shift_counts["Soir"] += 1 if a.person_a else 0
            elif a.shift == "N":
                shift_counts["Nuit"] += (1 if a.person_a else 0) + (1 if a.person_b else 0)
        
        fig_pie = px.pie(
            values=list(shift_counts.values()),
            names=list(shift_counts.keys()),
            color_discrete_sequence=["#DDEEFF", "#FFE4CC", "#E6CCFF"]
        )
        fig_pie.update_layout(margin=dict(l=20, r=20, t=30, b=20), height=300)
        st.plotly_chart(fig_pie, use_container_width=True)
    
    with col2:
        # Weekly coverage line chart
        st.write("**Couverture par semaine**")
        weekly_data = []
        staffing = state.staffing
        
        for w in range(1, weeks + 1):
            day_assignments = [a for a in schedule.assignments if a.week == w]
            filled = sum(
                (1 if a.person_a else 0) + (1 if a.person_b else 0)
                for a in day_assignments
            )
            
            # Estimate required from staffing if available
            required = 0
            if staffing and staffing.get(w):
                ws = staffing[w]
                for d in JOURS:
                    required += ws.slots[d].get("D", 0)*2 + \
                              ws.slots[d].get("S", 0) + \
                              ws.slots[d].get("N", 0)*2
            
            pct = (filled / required * 100) if required > 0 else 0
            weekly_data.append({"Semaine": w, "Couverture %": pct})
        
        df_weekly = pd.DataFrame(weekly_data)
        st.line_chart(df_weekly.set_index("Semaine"))
    
    # Fairness bar chart
    st.divider()
    st.write("**Équité par cohorte (σ)**")
    fairness = state.fairness
    if fairness:
        cohort_data = []
        for cohort in fairness.night_std_by_cohort:
            cohort_data.append({
                "Cohorte": cohort,
                "σ Nuits": fairness.night_std_by_cohort.get(cohort, 0),
                "σ Soirs": fairness.eve_std_by_cohort.get(cohort, 0)
            })
        df_fairness = pd.DataFrame(cohort_data)
        st.bar_chart(df_fairness.set_index("Cohorte"))
    else:
        st.info("Données d'équité non disponibles")

def _render_by_shift(state):
    st.subheader("Affectations par poste (paires)")
    schedule = state.schedule
    weeks = state.config_weeks
    
    for w in range(1, min(weeks+1, 5)):
        st.write(f"**Semaine {w}**")
        pairs_data = []
        for d in JOURS:
            row = {"Jour": d}
            for shift_name, shift_code in [("Jour", "D"), ("Soir", "S"), ("Nuit", "N"), ("Admin", "A")]:
                pairs = [a for a in schedule.assignments 
                        if a.week == w and a.day == d and a.shift == shift_code]
                
                if shift_code == "A":
                    row[shift_name] = ", ".join(a.person_a for a in pairs if a.person_a)
                else:
                    # Show pairs A/B
                    display_list = []
                    for a in pairs:
                        p_str = a.person_a
                        if a.person_b:
                             p_str += f" / {a.person_b}"
                        display_list.append(p_str)
                    row[shift_name] = "; ".join(display_list)
            pairs_data.append(row)
        st.dataframe(pd.DataFrame(pairs_data), use_container_width=True, hide_index=True)

def _render_stats(state):
    st.subheader("Statistiques par personne")
    
    from rota.solver.stats import calculate_person_stats, stats_to_dict_list
    
    # Needs edo_plan
    if not state.edo_plan:
        st.warning("Plan EDO manquant pour les stats.")
        return

    person_stats = calculate_person_stats(state.schedule, state.people, state.edo_plan)
    stats_data = stats_to_dict_list(person_stats)
    
    df_stats = pd.DataFrame(stats_data)
    
    # Color delta column
    def color_delta(val):
        if val > 0:
            return "background-color: #FFE4E4; color: #D00;"
        elif val < 0:
            return "background-color: #E4E4FF; color: #00D;"
        return ""
    
    if "Δ" in df_stats.columns:
        styled_stats = df_stats.style.map(color_delta, subset=["Δ"])
        st.dataframe(styled_stats, use_container_width=True, hide_index=True)
    else:
        st.dataframe(df_stats, use_container_width=True, hide_index=True)
    
    # Fairness table
    st.subheader("Équité par cohorte")
    fairness = state.fairness
    if fairness:
        cohort_data = []
        for cid, std_n in fairness.night_std_by_cohort.items():
            std_e = fairness.eve_std_by_cohort.get(cid, 0.0)
            cohort_data.append({"Cohorte": cid, "σ Nuits": f"{std_n:.2f}", "σ Soirs": f"{std_e:.2f}"})
        st.dataframe(pd.DataFrame(cohort_data), use_container_width=True, hide_index=True)
