import streamlit as st
import pandas as pd

from rota.models.rules import RULES
from rota.models.person import Person
from rota.io.csv_loader import load_team


def render_sidebar():
    """Render the configuration sidebar."""
    
    # ============ SECTION 1: TEAM SETUP ============
    st.sidebar.header("📂 Équipe")
    
    uploaded_file = st.sidebar.file_uploader("Charger CSV", type=["csv"], key="team_csv_uploader")
    
    # Load team
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            people = load_team(df)
            st.session_state.people = people
            st.sidebar.success(f"✅ {len(people)} personnes")
        except Exception as e:
            st.sidebar.error(f"Erreur: {e}")
            people = []
    else:
        # Demo mode
        if "people" not in st.session_state or not st.session_state.people:
            people = [Person(name=f"P4_{i+1}", workdays_per_week=4, edo_eligible=True) for i in range(12)] + \
                     [Person(name=f"P3_{i+1}", workdays_per_week=3, edo_eligible=False) for i in range(4)]
            st.session_state.people = people
            st.sidebar.info("ℹ️ Mode démo (16 p.)")
        else:
            people = st.session_state.people
    
    # Show team editor in expander
    if people:
        with st.sidebar.expander(f"👥 Équipe ({len(people)})", expanded=False):
            # Build editable dataframe
            team_df = pd.DataFrame([{
                "Nom": p.name,
                "J/sem": p.workdays_per_week,
                "EDO": p.edo_eligible,
                "EDO jour": p.edo_fixed_day or "",
                "Préf. Nuit": p.prefers_night,
                "Pas Soir": p.no_evening,
                "Max Nuits": p.max_nights if p.max_nights < 99 else None,
                "WE dispo": p.available_weekends,
                "Max WE/mois": p.max_weekends_per_month,
                "Externe": p.is_contractor,
                "Équipe": p.team or "",
            } for p in people])
            
            # Column config for better UX
            column_config = {
                "Nom": st.column_config.TextColumn("Nom", width="medium"),
                "J/sem": st.column_config.NumberColumn("J/sem", min_value=1, max_value=7, step=1, width="small"),
                "EDO": st.column_config.CheckboxColumn("EDO", width="small"),
                "EDO jour": st.column_config.SelectboxColumn("EDO jour", options=["", "Lun", "Mar", "Mer", "Jeu", "Ven"], width="small"),
                "Préf. Nuit": st.column_config.CheckboxColumn("Nuit", width="small"),
                "Pas Soir": st.column_config.CheckboxColumn("¬Soir", width="small"),
                "Max Nuits": st.column_config.NumberColumn("Max N", min_value=0, max_value=50, width="small"),
                "WE dispo": st.column_config.CheckboxColumn("WE", width="small"),
                "Max WE/mois": st.column_config.NumberColumn("WE/m", min_value=0, max_value=4, step=1, width="small"),
                "Externe": st.column_config.CheckboxColumn("Ext", width="small", help="Externe/Contractuel"),
                "Équipe": st.column_config.TextColumn("Team", width="small"),
            }
            
            edited_df = st.data_editor(
                team_df,
                use_container_width=True,
                hide_index=True,
                num_rows="dynamic",  # Allow adding/removing rows
                column_config=column_config,
                key="team_editor",
            )
            
            # Sync edits back to session_state.people
            if edited_df is not None:
                updated_people = []
                for _, row in edited_df.iterrows():
                    if pd.notna(row["Nom"]) and str(row["Nom"]).strip():
                        updated_people.append(Person(
                            name=str(row["Nom"]).strip(),
                            workdays_per_week=int(row["J/sem"]) if pd.notna(row["J/sem"]) else 4,
                            edo_eligible=bool(row["EDO"]) if pd.notna(row["EDO"]) else False,
                            edo_fixed_day=str(row["EDO jour"]) if pd.notna(row["EDO jour"]) and row["EDO jour"] else None,
                            prefers_night=bool(row["Préf. Nuit"]) if pd.notna(row["Préf. Nuit"]) else False,
                            no_evening=bool(row["Pas Soir"]) if pd.notna(row["Pas Soir"]) else False,
                            max_nights=int(row["Max Nuits"]) if pd.notna(row["Max Nuits"]) else 99,
                            available_weekends=bool(row["WE dispo"]) if pd.notna(row["WE dispo"]) else True,
                            max_weekends_per_month=int(row["Max WE/mois"]) if pd.notna(row["Max WE/mois"]) else 2,
                            is_contractor=bool(row["Externe"]) if pd.notna(row["Externe"]) else False,
                            team=str(row["Équipe"]) if pd.notna(row["Équipe"]) else "",
                        ))
                # Only update if team actually changed
                # Compare full list of objects (dataclass equality checks all fields)
                if updated_people:
                    current_people = st.session_state.get("people", [])
                    if updated_people != current_people:
                        st.session_state.people = updated_people
                        people = updated_people  # Update local reference
                        # No st.rerun() needed - downstream code uses updated 'people' variable

    
    st.sidebar.divider()
    
    # ============ SECTION 2: STUDY & OPTIMIZATION ============
    st.sidebar.header("🚀 Optimisation")
    
    # Check for existing study
    from app.components.utils import get_solver_config, get_custom_staffing, get_weekend_config
    solver_cfg = get_solver_config()
    custom_staffing = get_custom_staffing()
    weekend_config = get_weekend_config()
    
    if people:
        from rota.solver.study_manager import StudyManager, compute_study_hash
        manager = StudyManager()
        study_hash = compute_study_hash(solver_cfg, people, custom_staffing, weekend_config)
        
        # DEBUG: Show hash and available studies
        all_studies = manager.list_studies(limit=3)
        st.sidebar.caption(f"🔍 Hash: `{study_hash[:12]}`")
        st.sidebar.caption(f"📊 weeks={solver_cfg.weeks} staff={custom_staffing}")
        if all_studies:
            for s in all_studies:
                match = "✅" if s.study_hash == study_hash else "❌"
                st.sidebar.caption(f"{match} `{s.study_hash[:12]}` ({s.total_trials})")

        
        if manager.study_exists(study_hash):

            summary = manager.get_study_summary(study_hash)
            if summary and summary.total_trials > 0:
                st.sidebar.info(f"📚 Étude existante: {summary.total_trials} essais | Score: {summary.best_score:.1f}")
                
                col1, col2 = st.sidebar.columns(2)
                with col1:
                    if st.button("▶️ + essais", key="sidebar_run_more", use_container_width=True):
                        st.session_state.trigger_optimize = True
                with col2:
                    if st.button("📥 Charger", key="sidebar_load_best", use_container_width=True):
                        from app.components.study_browser import load_study_result
                        load_study_result(study_hash, people, solver_cfg)
                        st.rerun()
            else:
                if st.sidebar.button("🚀 Lancer Optimisation", type="primary", use_container_width=True, key="sidebar_optimize"):
                    st.session_state.trigger_optimize = True
        else:
            if st.sidebar.button("🚀 Lancer Optimisation", type="primary", use_container_width=True, key="sidebar_optimize_new"):
                st.session_state.trigger_optimize = True
    
    st.sidebar.divider()
    
    # ============ SECTION 3: CONFIG ============
    st.sidebar.header("⚙️ Configuration")

    # Global options
    merge_calendars = st.sidebar.checkbox(
        "📅 Mode Fusionné (Semaine + WE)", value=st.session_state.get("merge_calendars", False),
        help="Active l'optimisation conjointe et l'export fusionné"
    )
    st.session_state.merge_calendars = merge_calendars

    # Basic Settings
    st.sidebar.number_input(
        "Semaines", min_value=1, max_value=24, key="config_weeks",
        help="Nombre de semaines à planifier (horizon de planification)"
    )
    st.sidebar.number_input(
        "Essais (multi-seed)", min_value=1, max_value=50, key="config_tries",
        help="Nombre de tentatives avec différents seeds - plus d'essais = meilleur résultat potentiel"
    )
    st.sidebar.number_input(
        "Seed (0=auto)", min_value=0, key="config_seed",
        help="Graine aléatoire pour reproductibilité. 0 = automatique basé sur l'heure"
    )
    st.sidebar.number_input(
        "Temps limite (sec)", min_value=10, max_value=600, key="config_time_limit",
        help="Temps maximum accordé au solveur pour trouver une solution optimale"
    )

    # Advanced panel (Week)
    with st.sidebar.expander("🔧 Paramètres Avancés (Semaine)", expanded=False):
        st.subheader("Contraintes dures")
        st.session_state.setdefault("cfg_forbid_night_to_day", True)
        st.checkbox("Repos après nuit", key="cfg_forbid_night_to_day",
            help="Interdire de travailler le jour après une nuit")
            
        st.session_state.setdefault("cfg_edo_enabled", True)
        st.checkbox("EDO activé", key="cfg_edo_enabled",
            help="Activer les jours de repos (1 jour/2 semaines)")
            
        st.session_state.setdefault("cfg_forbid_contractor_pairs", True)
        st.checkbox("Pas 2 externes ensemble", key="cfg_forbid_contractor_pairs",
            help="Interdire de mettre 2 externes/contractuels en binôme (pour tutorat)")

        st.session_state.setdefault("cfg_max_nights_seq", 3)
        st.number_input("Nuits consécutives max", min_value=1, max_value=5, key="cfg_max_nights_seq")
        
        st.session_state.setdefault("cfg_max_consecutive_days", 6)
        st.number_input("Jours consécutifs max", min_value=3, max_value=14, key="cfg_max_consecutive_days",
            help="Maximum de jours travaillés sans interruption (sauf si week-end travaillé)")
        
        st.subheader("Effectifs Requis (Par Jour)")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.session_state.setdefault("cfg_req_pairs_D", RULES.default_staffing["D"])
            st.number_input("Paires Jour", min_value=1, max_value=10, key="cfg_req_pairs_D", help="Nb de paires (x2 personnes)")
        with c2:
            st.session_state.setdefault("cfg_req_solos_S", RULES.default_staffing["S"])
            st.number_input("Pers. Soir", min_value=1, max_value=5, key="cfg_req_solos_S", help="Nb de personnes (Solo)")
        with c3:
            st.session_state.setdefault("cfg_req_pairs_N", RULES.default_staffing["N"])
            st.number_input("Paires Nuit", min_value=1, max_value=5, key="cfg_req_pairs_N", help="Nb de paires (x2 personnes)")
        
        st.subheader("Poids objectif (soft)")
        st.caption("Plus le poids est élevé, plus la contrainte est prioritaire")
        
        st.session_state.setdefault("cfg_weight_night_fairness", 10)
        st.slider("σ Nuits", min_value=0, max_value=20, key="cfg_weight_night_fairness")
        
        st.session_state.setdefault("cfg_weight_eve_fairness", 3)
        st.slider("σ Soirs", min_value=0, max_value=20, key="cfg_weight_eve_fairness")
        
        st.session_state.setdefault("cfg_weight_deviation", 5)
        st.slider("Écart cible", min_value=0, max_value=20, key="cfg_weight_deviation")
        
        st.session_state.setdefault("cfg_weight_clopening", 1)
        st.slider("Soir→Jour", min_value=0, max_value=10, key="cfg_weight_clopening",
            help="Pénalité pour enchaînement soir suivi d'un jour")
        
        st.subheader("Équité")
        st.session_state.setdefault("cfg_fairness_mode", ("by-wd", "Par jours/semaine"))
        st.selectbox("Mode cohorte", [("by-wd", "Par jours/semaine"), ("by-team", "Par équipe"), ("none", "Global")], 
            key="cfg_fairness_mode", format_func=lambda x: x[1] if isinstance(x, tuple) else x)
        
        st.divider()
        st.subheader("🧪 Tests")
        st.session_state.setdefault("cfg_stress_test", False)
        st.checkbox(
            "Mode Stress Test", key="cfg_stress_test",
            help="Active la demande impossible pour vérifier le logging des déficits"
        )

    # Advanced panel (Weekend)
    with st.sidebar.expander("🔧 Paramètres Avancés (Week-end)", expanded=False):
        st.caption("Samedi & Dimanche")
        
        st.session_state.setdefault("cfg_max_weekends_month", 2)
        st.number_input(
            "Max WE/mois", min_value=0, max_value=4, key="cfg_max_weekends_month",
            help="Maximum de week-ends travaillés par mois"
        )
        
        st.session_state.setdefault("cfg_forbid_consecutive_nights_we", True) 
        st.checkbox(
            "Pas 2 nuits consécutives", key="cfg_forbid_consecutive_nights_we",
            help="Interdire d'enchaîner Vendredi+Samedi ou Samedi+Dimanche Nuit"
        )
        
        st.subheader("Poids objectif")
        st.session_state.setdefault("cfg_weight_w_fairness", 10)
        st.slider("σ Fairness", min_value=0, max_value=20, key="cfg_weight_w_fairness", help="Équité charge globale")
        
        st.session_state.setdefault("cfg_weight_w_split", 5)
        st.slider("Pénalité Split", min_value=0, max_value=20, key="cfg_weight_w_split", help="Éviter de travailler Samedi ET Dimanche (sauf 24h)")
        
        st.session_state.setdefault("cfg_weight_w_24h", 5)
        st.slider("Équité 24h", min_value=0, max_value=20, key="cfg_weight_w_24h", help="Répartir équitablement les shifts 24h")
        
        st.session_state.setdefault("cfg_weight_w_consecutive", 50)
        st.slider("Pénalité 3 WE consécutifs", min_value=0, max_value=500, step=10, key="cfg_weight_w_consecutive", help="Pénalité forte pour travailler 3 week-ends de suite")
