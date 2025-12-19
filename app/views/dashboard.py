"""
Dashboard View (Redesigned)
============================
Displays results, KPIs, matrices, and charts.
Organized by typology and importance.
"""
import streamlit as st
import pandas as pd
import plotly.express as px
from app.state.session import SessionStateManager
from rota.solver.staffing import JOURS


def render_dashboard(state: SessionStateManager, merged_mode: bool = False):
    """Render the main dashboard - restructured for better UX.
    
    Args:
        state: Session state manager
        merged_mode: If True, show Lun-Dim in single matrix; if False, weekday only
    """
    if not state.schedule or state.schedule.status not in ["optimal", "feasible"]:
        if state.schedule and state.schedule.status:
            st.error(f"❌ Pas de solution trouvée: {state.schedule.status}")
        else:
            st.info("👋 Veuillez lancer une optimisation pour voir les résultats.")
        return

    # === 1. ZONE HERO - Métriques Critiques (toujours visible) ===
    _render_hero_kpis(state, merged_mode=merged_mode)

    # === 2. BANDEAU ALERTE - Diagnostic conditionnel ===
    _render_diagnostic_banner(state)

    # === 3. ONGLETS PRINCIPAUX - Ordonnés par importance d'usage ===
    t1, t2, t3, t4, t5 = st.tabs([
        "📊 Planning",       # Priorité 1 - 80% usage
        "📅 Couverture",     # Priorité 2 - 60% usage
        "👥 Personnes",      # Priorité 3 - 40% usage
        "📈 Analyses",       # Priorité 4 - 20% usage
        "⚙️ Détails"         # Priorité 5 - 10% usage (technique)
    ])

    with t1:
        _render_matrix(state, merged_mode=merged_mode)

    with t2:
        _render_coverage(state, merged_mode=merged_mode)

    with t3:
        _render_person_stats(state, merged_mode=merged_mode)

    with t4:
        _render_analytics(state, merged_mode=merged_mode)

    with t5:
        _render_technical_details(state, merged_mode=merged_mode)

    # === 4. FOOTER TECHNIQUE ===
    st.divider()
    study_hash = state.study_hash[:8] if state.study_hash else "N/A"
    st.caption(f"🌱 Seed: {state.best_seed} | Étude: {study_hash}...")


# =============================================================================
# ZONE 1: HERO KPIs
# =============================================================================

def _render_hero_kpis(state, merged_mode: bool = False):
    """Render the critical KPIs at the top."""
    schedule = state.schedule
    validation = state.validation
    w_result = state.w_result

    col1, col2, col3, col4 = st.columns(4)
    
    # Score - combine if merged mode
    with col1:
        total_score = state.best_score or 0
        if merged_mode and w_result and hasattr(w_result, 'score'):
            # Could add weekend score if available
            pass
        st.metric("Score", f"{total_score:.0f}")
    
    with col2:
        if validation:
            total_violations = validation.rolling_48h_violations + validation.nuit_suivie_travail
            st.metric("Violations", total_violations,
                      delta="⚠️" if total_violations > 0 else None,
                      delta_color="inverse")
        else:
            st.metric("Violations", "N/A")
    
    with col3:
        if validation:
            st.metric("Manques", validation.slots_vides,
                      delta="❌" if validation.slots_vides > 0 else None,
                      delta_color="inverse")
        else:
            st.metric("Manques", "N/A")
    
    with col4:
        total_time = schedule.solve_time_seconds
        if merged_mode and w_result and hasattr(w_result, 'solve_time'):
            total_time += w_result.solve_time
        st.metric("Temps", f"{total_time:.1f}s")


# =============================================================================
# ZONE 2: DIAGNOSTIC BANNER
# =============================================================================

def _render_diagnostic_banner(state):
    """Render the diagnostic alert banner."""
    from app.services.diagnosis import DiagnosisService

    edo_plan = state.edo_plan
    staffing = state.staffing
    validation = state.validation

    if not edo_plan or not staffing:
        st.warning("⚠️ Diagnostic non disponible (données manquantes).")
        return

    result = DiagnosisService.diagnose(
        state.schedule, state.people, validation, edo_plan, staffing
    )

    st.divider()

    if result.scenario_type == "DEFICIT":
        st.error(f"❌ **{result.message}**")
        st.markdown("Le nombre d'agents est insuffisant pour couvrir la demande.")

        with st.expander("🚨 Détail des Créneaux Non Pourvus", expanded=True):
            if result.details:
                df_missing = pd.DataFrame(result.details)
                total_people = df_missing["Besoins"].sum()
                st.markdown(f"**Total à recruter: {total_people} personnes**")
                st.dataframe(df_missing, width="stretch", hide_index=True)
            else:
                st.info("Aucun détail disponible.")

    elif result.scenario_type == "SURPLUS":
        st.success(f"✅ **{result.message}**")
        st.markdown("Tous les besoins sont couverts et l'équipe a encore de la disponibilité.")

    else:  # BALANCED
        st.warning("⚠️ **Planning Tendu / Équilibré**")
        st.markdown("L'équipe couvre exactement la charge (« Juste-à-temps »).")


# =============================================================================
# ONGLET 1: PLANNING (Matrice)
# =============================================================================

def _render_matrix(state, merged_mode: bool = False):
    """Render the schedule matrix.
    
    Args:
        merged_mode: If True, show Lun-Dim in single matrix; if False, weekday only
    """
    st.subheader("Matrice des Affectations")
    
    if merged_mode:
        # MERGED MODE: Single matrix with Lun-Dim (7 days)
        _render_full_week_matrix(state)
    else:
        # SEPARATE MODE: Weekday only (Lun-Ven)
        _render_weekday_matrix(state)


def _render_full_week_matrix(state):
    """Render full week matrix (Lun-Dim) for merged mode."""
    st.caption("🔵 Jour | 🟠 Soir | 🟣 Nuit | ⬜ Admin | ⚪ OFF")
    
    schedule = state.schedule
    people = state.people
    weeks = state.config_weeks
    w_result = state.w_result

    if not people:
        st.warning("Aucun personnel chargé.")
        return

    # Full week days
    JOURS_FULL = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]

    # Pre-fetch weekday assignments
    assign_map = schedule.get_person_day_matrix(code_map={"D": "J", "S": "S", "N": "N", "A": "A"})
    
    # Pre-fetch weekend assignments if available
    weekend_map = {}
    if w_result and hasattr(w_result, 'assignments') and w_result.assignments:
        for a in w_result.assignments:
            key = (a.person.name, a.week, a.day)
            shift_code = {"D": "J", "S": "S", "N": "N"}.get(a.shift, a.shift)
            weekend_map[key] = shift_code

    # Build matrix data
    names = sorted([p.name for p in people])
    matrix_data = []

    for name in names:
        row = {"Nom": name}
        for w in range(1, weeks + 1):
            for d in JOURS_FULL:
                col = f"S{w}_{d}"
                if d in ["Sam", "Dim"]:
                    # Weekend from w_result
                    val = weekend_map.get((name, w, d), "OFF")
                else:
                    # Weekday from schedule
                    val = assign_map.get((name, w, d), "OFF")
                row[col] = val
        matrix_data.append(row)

    if not matrix_data:
        st.warning("Aucune donnée de planning disponible.")
        return

    df = pd.DataFrame(matrix_data)
    df = df.drop_duplicates(subset=["Nom"]).set_index("Nom")
    
    # Create merged cell headers using MultiIndex
    # Structure: ("Semaine 1", "Lun"), ("Semaine 1", "Mar"), ...
    new_cols = []
    for w in range(1, weeks + 1):
        for d in JOURS_FULL:
             new_cols.append((f"Semaine {w}", d))
    
    if len(df.columns) == len(new_cols):
        df.columns = pd.MultiIndex.from_tuples(new_cols)

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

    st.dataframe(df.style.map(color_shift), width="stretch", height=450)


def _render_weekday_matrix(state):
    """Render the weekday schedule matrix (Lun-Ven)."""
    st.caption("🔵 Jour | 🟠 Soir | 🟣 Nuit | ⬜ Admin | ⚪ OFF")

    schedule = state.schedule
    people = state.people
    weeks = state.config_weeks

    if not people:
        st.warning("Aucun personnel chargé.")
        return

    # Pre-fetch assignments
    assign_map = schedule.get_person_day_matrix(code_map={"D": "J", "S": "S", "N": "N", "A": "A"})

    # Build matrix data
    names = sorted([p.name for p in people])
    matrix_data = []

    for name in names:
        row = {"Nom": name}
        for w in range(1, weeks + 1):
            for d in JOURS:
                col = f"S{w}_{d}"
                val = assign_map.get((name, w, d), "OFF")
                row[col] = val
        matrix_data.append(row)

    if not matrix_data:
        st.warning("Aucune donnée de planning disponible.")
        return

    df = pd.DataFrame(matrix_data)
    df = df.drop_duplicates(subset=["Nom"]).set_index("Nom")
    
    # Create merged cell headers using MultiIndex
    new_cols = []
    for w in range(1, weeks + 1):
        for d in JOURS:
             new_cols.append((f"Semaine {w}", d))
    
    if len(df.columns) == len(new_cols):
        df.columns = pd.MultiIndex.from_tuples(new_cols)

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

    st.dataframe(df.style.map(color_shift), width="stretch", height=450)


def _render_weekend_matrix(state):
    """Render the weekend schedule matrix (Sam-Dim)."""
    st.caption("🔵 Jour | 🟠 Soir | 🟣 Nuit")
    
    w_result = state.w_result
    
    if not w_result:
        st.warning("Aucun résultat week-end disponible.")
        return
        
    if not hasattr(w_result, 'assignments') or not w_result.assignments:
        st.info(f"Statut: {w_result.status}. {getattr(w_result, 'message', '')}")
        return
    
    # Build weekend matrix
    # WeekendAssignment has: person (Person object), week, day, shift
    we_data = []
    for a in w_result.assignments:
        shift_name = {"D": "Jour 🌅", "S": "Soir 🌆", "N": "Nuit 🌙"}.get(a.shift, a.shift)
        person_name = a.person.name if hasattr(a, 'person') and a.person else "-"
        we_data.append({
            "Semaine": f"S{a.week}",
            "Jour": "Sam" if a.day in ["Sam", "Samedi", "Saturday"] else "Dim",
            "Quart": shift_name,
            "Personne": person_name,
        })
    
    df_we = pd.DataFrame(we_data)
    
    # Color function for weekend
    def color_weekend(val):
        if "Jour" in str(val):
            return "background-color: #DDEEFF;"
        elif "Soir" in str(val):
            return "background-color: #FFE4CC;"
        elif "Nuit" in str(val):
            return "background-color: #E6CCFF;"
        return ""
    
    styled_we = df_we.style.map(color_weekend, subset=["Quart"])
    st.dataframe(styled_we, width="stretch", hide_index=True)


# =============================================================================
# ONGLET 2: COUVERTURE
# =============================================================================

def _render_coverage(state, merged_mode: bool = False):
    """Render the coverage calendar."""
    st.subheader("📅 Calendrier de Couverture")
    st.caption("🟢 Couvert | 🟡 Partiel | 🔴 Manque")

    schedule = state.schedule
    weeks = state.config_weeks
    staffing = state.staffing
    w_result = state.w_result if merged_mode else None

    if not staffing:
        st.warning("Données de staffing manquantes.")
        return

    # Define columns based on mode
    weekday_cols = JOURS  # Lun-Ven
    weekend_cols = ["Sam", "Dim"] if merged_mode and w_result else []
    all_cols = list(weekday_cols) + weekend_cols

    coverage_data = []
    for w in range(1, weeks + 1):
        row = {"Semaine": f"S{w}"}
        ws = staffing.get(w)
        if not ws:
            continue

        # Weekday coverage
        for d in JOURS:
            req_d = ws.slots[d].get("D", 0) * 2
            req_s = ws.slots[d].get("S", 0)
            req_n = ws.slots[d].get("N", 0) * 2
            total_required = req_d + req_s + req_n

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

        # Weekend coverage (from w_result)
        if merged_mode and w_result and w_result.assignments:
            for we_day in ["Sam", "Dim"]:
                # Count assignments for this day
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

    df_coverage = pd.DataFrame(coverage_data)

    def color_coverage(val):
        if "✅" in str(val):
            return "background-color: #D4EDDA; color: #155724;"
        elif "⚠️" in str(val):
            return "background-color: #FFF3CD; color: #856404;"
        elif "❌" in str(val):
            return "background-color: #F8D7DA; color: #721C24; font-weight: bold;"
        return ""

    # Only style columns that exist in the dataframe
    cols_to_style = [c for c in all_cols if c in df_coverage.columns]
    if cols_to_style:
        styled_cov = df_coverage.style.map(color_coverage, subset=cols_to_style)
        st.dataframe(styled_cov, width="stretch", hide_index=True)
    else:
        st.dataframe(df_coverage, width="stretch", hide_index=True)

    # Gap details
    validation = state.validation
    if validation and validation.slots_vides > 0:
        with st.expander("Voir détails des manques", expanded=False):
            gaps = [v for v in validation.violations if v.type in {"unfilled_slot", "incomplete_pair"}]
            for v in gaps[:20]:
                st.write(f"• **S{v.week} {v.day}** - {v.shift}: {v.message}")
            if len(gaps) > 20:
                st.write(f"... et {len(gaps) - 20} autres")


# =============================================================================
# ONGLET 3: PERSONNES (Stats individuelles + Équité)
# =============================================================================

def _render_person_stats(state, merged_mode: bool = False):
    """Render person-level statistics and fairness."""
    st.subheader("Statistiques par Personne")

    from rota.solver.stats import calculate_person_stats, stats_to_dict_list

    if not state.edo_plan:
        st.warning("Plan EDO manquant pour les stats.")
        return

    person_stats = calculate_person_stats(state.schedule, state.people, state.edo_plan)
    stats_data = stats_to_dict_list(person_stats)

    df_stats = pd.DataFrame(stats_data)
    
    # Add weekend stats if merged mode and we have weekend assignments
    w_result = state.w_result if merged_mode else None
    if merged_mode and w_result and w_result.assignments:
        # Count weekend shifts per person
        we_counts = {}
        for a in w_result.assignments:
            name = a.person.name
            we_counts[name] = we_counts.get(name, 0) + 1
        
        # Add columns to stats dataframe
        if "Nom" in df_stats.columns:
            df_stats["WE Shifts"] = df_stats["Nom"].map(lambda n: we_counts.get(n, 0))
            # Calculate total if we have a total column
            if "Total" in df_stats.columns:
                df_stats["Total+WE"] = df_stats["Total"] + df_stats["WE Shifts"]
            else:
                df_stats["Total+WE"] = df_stats["WE Shifts"]

    def color_delta(val):
        if val > 0:
            return "background-color: #FFE4E4; color: #D00;"
        elif val < 0:
            return "background-color: #E4E4FF; color: #00D;"
        return ""

    if "Δ" in df_stats.columns:
        styled_stats = df_stats.style.map(color_delta, subset=["Δ"])
        st.dataframe(styled_stats, width="stretch", hide_index=True)
    else:
        st.dataframe(df_stats, width="stretch", hide_index=True)

    # Fairness by cohort
    st.divider()
    st.subheader("Équité par Cohorte")
    fairness = state.fairness
    if fairness:
        cohort_data = []
        for cid, std_n in fairness.night_std_by_cohort.items():
            std_e = fairness.eve_std_by_cohort.get(cid, 0.0)
            cohort_data.append({
                "Cohorte": cid,
                "σ Nuits": f"{std_n:.2f}",
                "σ Soirs": f"{std_e:.2f}"
            })
        st.dataframe(pd.DataFrame(cohort_data), width="stretch", hide_index=True)
    else:
        st.info("Données d'équité non disponibles.")


# =============================================================================
# ONGLET 4: ANALYSES (Graphiques)
# =============================================================================

def _render_analytics(state, merged_mode: bool = False):
    """Render analytics charts."""
    st.subheader("📈 Analytiques")

    schedule = state.schedule
    weeks = state.config_weeks
    w_result = state.w_result if merged_mode else None

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Répartition des quarts (Semaine)**")
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
        st.plotly_chart(fig_pie, width="stretch")

    with col2:
        st.write("**Couverture par semaine**")
        weekly_data = []
        staffing = state.staffing

        for w in range(1, weeks + 1):
            day_assignments = [a for a in schedule.assignments if a.week == w]
            filled = sum(
                (1 if a.person_a else 0) + (1 if a.person_b else 0)
                for a in day_assignments
            )

            required = 0
            if staffing and staffing.get(w):
                ws = staffing[w]
                for d in JOURS:
                    required += ws.slots[d].get("D", 0) * 2 + \
                                ws.slots[d].get("S", 0) + \
                                ws.slots[d].get("N", 0) * 2

            pct = (filled / required * 100) if required > 0 else 0
            weekly_data.append({"Semaine": w, "Couverture %": pct})

        df_weekly = pd.DataFrame(weekly_data)
        st.line_chart(df_weekly.set_index("Semaine"))

    # Weekend analytics (if merged mode)
    if merged_mode and w_result and w_result.assignments:
        st.divider()
        st.write("**📅 Analyses Week-end**")
        
        we_col1, we_col2 = st.columns(2)
        
        with we_col1:
            st.write("**Répartition WE par jour**")
            we_day_counts = {"Sam D": 0, "Sam N": 0, "Dim D": 0, "Dim N": 0}
            for a in w_result.assignments:
                key = f"{a.day} {a.shift}"
                if key in we_day_counts:
                    we_day_counts[key] += 1
            
            fig_we_pie = px.pie(
                values=list(we_day_counts.values()),
                names=list(we_day_counts.keys()),
                color_discrete_sequence=["#C8E6C9", "#A5D6A7", "#81C784", "#66BB6A"]
            )
            fig_we_pie.update_layout(margin=dict(l=20, r=20, t=30, b=20), height=300)
            st.plotly_chart(fig_we_pie, width="stretch")
        
        with we_col2:
            st.write("**WE Shifts par personne (Top 10)**")
            we_person_counts = {}
            for a in w_result.assignments:
                name = a.person.name
                we_person_counts[name] = we_person_counts.get(name, 0) + 1
            
            # Sort and take top 10
            sorted_counts = sorted(we_person_counts.items(), key=lambda x: x[1], reverse=True)[:10]
            if sorted_counts:
                df_we_person = pd.DataFrame(sorted_counts, columns=["Personne", "Shifts WE"])
                fig_bar = px.bar(df_we_person, x="Personne", y="Shifts WE", 
                                 color_discrete_sequence=["#4CAF50"])
                fig_bar.update_layout(margin=dict(l=20, r=20, t=30, b=20), height=300)
                st.plotly_chart(fig_bar, width="stretch")

    # Fairness chart
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
        st.info("Données d'équité non disponibles.")


# =============================================================================
# ONGLET 5: DÉTAILS TECHNIQUES
# =============================================================================

def _render_technical_details(state, merged_mode: bool = False):
    """Render technical details: Capacity, Quality, Pairs."""
    d1, d2, d3 = st.tabs(["📊 Capacité", "🔍 Qualité", "👥 Par Poste"])

    with d1:
        _render_capacity_analysis(state, merged_mode=merged_mode)

    with d2:
        _render_quality_metrics(state, merged_mode=merged_mode)

    with d3:
        _render_by_shift(state, merged_mode=merged_mode)


def _render_capacity_analysis(state, merged_mode: bool = False):
    """Render capacity analysis."""
    st.subheader("Analyse de Capacité")

    staffing = state.staffing
    edo_plan = state.edo_plan
    w_result = state.w_result if merged_mode else None

    if not staffing or not edo_plan:
        st.warning("Données manquantes pour l'analyse de capacité.")
        return

    from rota.solver.capacity import calculate_capacity
    cap_analysis = calculate_capacity(state.schedule, state.people, staffing, edo_plan)

    # Summary KPIs
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
    st.markdown("**Par type de quart (Semaine):**")
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
    st.dataframe(pd.DataFrame(shift_data), width="stretch", hide_index=True)
    
    # Weekend capacity (if merged mode)
    if merged_mode and w_result and w_result.assignments:
        st.divider()
        st.markdown("**Par type de quart (Week-end):**")
        we_shift_data = []
        # Count weekend assignments by shift
        we_counts = {"D": 0, "N": 0}
        for a in w_result.assignments:
            if a.shift in we_counts:
                we_counts[a.shift] += 1
        
        weeks = state.config_weeks
        required_per_shift = weeks * 2 * 2  # weeks × 2 days × 2 staff
        for shift_code, shift_name in [("D", "Jour WE 🌅"), ("N", "Nuit WE 🌙")]:
            assigned = we_counts.get(shift_code, 0)
            gap = required_per_shift - assigned
            we_shift_data.append({
                "Quart": shift_name,
                "Requis": required_per_shift,
                "Affectés": assigned,
                "Écart": gap,
                "Status": "✅" if gap <= 0 else f"❌ -{gap}"
            })
        st.dataframe(pd.DataFrame(we_shift_data), width="stretch", hide_index=True)

    # Recommendation
    st.divider()
    st.markdown("**💡 Recommandation:**")
    if cap_analysis.agents_needed > 0.5:
        st.error(f"⚠️ **Besoin d'environ {cap_analysis.agents_needed:.1f} agents supplémentaires** pour couvrir tous les créneaux.")
    elif cap_analysis.excess_agent_days > 10:
        st.success(f"✅ **Équipe bien dimensionnée**. {cap_analysis.excess_agent_days:.0f} jours-agent disponibles en marge.")
    else:
        st.info(f"ℹ️ L'équipe est à **{cap_analysis.utilization_percent:.0f}%** de sa capacité. Marge confortable.")


def _render_quality_metrics(state, merged_mode: bool = False):
    """Render quality/violation metrics."""
    st.subheader("Métriques de Qualité")

    validation = state.validation
    fairness = state.fairness

    if not validation:
        st.warning("Données de validation non disponibles.")
        return

    # Detailed metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("Violations 48h", validation.rolling_48h_violations,
                  delta="CRITIQUE" if validation.rolling_48h_violations > 0 else None,
                  delta_color="inverse")
    with col2:
        st.metric("Nuit→Travail", validation.nuit_suivie_travail,
                  delta="⚠️" if validation.nuit_suivie_travail > 0 else None,
                  delta_color="inverse")
    with col3:
        st.metric("Soir→Jour", validation.soir_vers_jour)
    with col4:
        st.metric("σ Nuits", f"{fairness.night_std:.2f}" if fairness else "N/A")
    with col5:
        st.metric("σ Soirs", f"{fairness.eve_std:.2f}" if fairness else "N/A")

    # Violation breakdown
    if validation.violations:
        st.divider()
        st.markdown("**Détail par type de violation:**")
        viol_types = {}
        for v in validation.violations:
            viol_types[v.type] = viol_types.get(v.type, 0) + 1

        cols = st.columns(len(viol_types)) if viol_types else []
        for i, (vtype, count) in enumerate(viol_types.items()):
            type_labels = {
                "unfilled_slot": "🔴 Slots vides",
                "night_followed_work": "🟠 Nuit→Travail",
                "clopening": "🟡 Soir→Jour",
                "48h_exceeded": "🔴 48h dépassé",
                "duplicate": "⚠️ Doublon",
                "incomplete_pair": "🟠 Paire incomplète",
                "48h_rolling": "🔴 48h glissant"
            }
            label = type_labels.get(vtype, vtype)
            with cols[i]:
                st.metric(label, count)


def _render_by_shift(state, merged_mode: bool = False):
    """Render assignments by shift (pairs)."""
    st.subheader("Affectations par Poste (Paires)")

    schedule = state.schedule
    weeks = state.config_weeks
    w_result = state.w_result if merged_mode else None

    for w in range(1, min(weeks + 1, 5)):
        st.write(f"**Semaine {w}**")
        pairs_data = []
        
        # Weekday assignments
        for d in JOURS:
            row = {"Date": f"S{w}_{d}"}
            for shift_name, shift_code in [("Jour", "D"), ("Soir", "S"), ("Nuit", "N"), ("Admin", "A")]:
                pairs = [a for a in schedule.assignments
                         if a.week == w and a.day == d and a.shift == shift_code]

                if shift_code == "A":
                    row[shift_name] = ", ".join(a.person_a for a in pairs if a.person_a)
                else:
                    display_list = []
                    for a in pairs:
                        p_str = a.person_a or ""
                        if a.person_b:
                            p_str += f" / {a.person_b}"
                        if p_str:
                            display_list.append(p_str)
                    row[shift_name] = "; ".join(display_list)
            pairs_data.append(row)
        
        # Weekend assignments (if merged mode)
        if merged_mode and w_result and w_result.assignments:
            for we_day in ["Sam", "Dim"]:
                row = {"Date": f"S{w}_{we_day}"}
                for shift_name, shift_code in [("Jour", "D"), ("Nuit", "N")]:
                    we_assignments = [a for a in w_result.assignments
                                      if a.week == w and a.day == we_day and a.shift == shift_code]
                    names = [a.person.name for a in we_assignments]
                    row[shift_name] = ", ".join(names) if names else "-"
                row["Soir"] = "-"  # No evening shift on weekends
                row["Admin"] = "-"  # No admin on weekends
                pairs_data.append(row)
        
        st.dataframe(pd.DataFrame(pairs_data), width="stretch", hide_index=True)
