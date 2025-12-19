"""
Sidebar Components
==================
Reusable widgets for the sidebar.
"""
import streamlit as st
import pandas as pd
from typing import Optional, List, Any
from rota.models.person import Person
from rota.models.rules import RULES
from rota.io.csv_loader import load_team

def render_logo():
    """Render the app logo/header."""
    # st.sidebar.image("assets/logo.png", width=150) # Placeholder
    st.sidebar.markdown("### 🧬 Rota Optimizer")

def render_file_upload() -> Optional[Any]:
    """Render file uploader."""
    return st.sidebar.file_uploader("Charger CSV", type=["csv"], key="team_csv_uploader")

def render_team_editor(uploaded_file: Optional[Any] = None) -> List[Person]:
    """
    Render the team editor table. 
    Handles loading from file or session state.
    """
    people: List[Person] = []
    
    # 1. Handle File Upload or Session Load
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
        # Check session state
        if "people" in st.session_state and st.session_state.people:
             people = st.session_state.people
        else:
             people = []
             st.sidebar.info("ℹ️ Veuillez charger un fichier CSV")

    if not people:
        return []

    # 2. Render Editor
    with st.sidebar.expander(f"👥 Équipe ({len(people)})", expanded=False):
        # Build editable dataframe
        team_data = []
        for p in people:
            team_data.append({
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
            })
        
        team_df = pd.DataFrame(team_data)
        
        # Column config
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
            width="stretch",
            hide_index=True,
            num_rows="dynamic",
            column_config=column_config,
            key="team_editor_widget", # Unique key
        )
        
        # 3. Sync back to objects
        if edited_df is not None:
            updated_people = []
            for _, row in edited_df.iterrows():
                if pd.notna(row["Nom"]) and str(row["Nom"]).strip():
                    try:
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
                    except (ValueError, TypeError):
                        continue # Skip invalid rows
            
            # Compare and update state
            if updated_people:
                return updated_people

    return people

def render_solver_config():
    """Render solver configuration inputs."""
    
    # Global options
    merge_calendars = st.sidebar.checkbox(
        "📅 Mode Fusionné (Semaine + WE)", value=st.session_state.get("merge_calendars", False),
        help="Active l'optimisation conjointe et l'export fusionné"
    )
    st.session_state.merge_calendars = merge_calendars

    # Basic Settings - COMPACT 2x2 GRID
    c1, c2 = st.sidebar.columns(2)
    with c1:
        st.number_input(
            "Semaines", min_value=1, max_value=24, key="config_weeks",
            help="Horizon"
        )
        st.number_input(
            "Seed (0=auto)", min_value=0, key="config_seed",
            help="Graine"
        )
    with c2:
        st.number_input(
            "Essais", min_value=1, max_value=50, key="config_tries",
            help="Tentatives"
        )
        st.number_input(
            "Tps limite (s)", min_value=10, max_value=600, key="config_time_limit",
            help="Temps max"
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

        c1, c2 = st.columns(2)
        with c1:
            st.session_state.setdefault("cfg_max_nights_seq", 1)
            st.number_input("Max Nuits", min_value=1, max_value=5, key="cfg_max_nights_seq", help="Nuits consécutives max")
        
        with c2:
            st.session_state.setdefault("cfg_max_consecutive_days", 6)
            st.number_input("Max Jours", min_value=3, max_value=14, key="cfg_max_consecutive_days",
                help="Jours consécutifs max")
        
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
        st.caption("Priorités (Haut = Important)")
        
        c1, c2 = st.columns(2)
        with c1:
            st.session_state.setdefault("cfg_weight_night_fairness", 10)
            st.slider("σ Nuits", 0, 20, key="cfg_weight_night_fairness")
            
            st.session_state.setdefault("cfg_weight_deviation", 5)
            st.slider("Écart", 0, 20, key="cfg_weight_deviation")

        with c2:
            st.session_state.setdefault("cfg_weight_eve_fairness", 3)
            st.slider("σ Soirs", 0, 20, key="cfg_weight_eve_fairness")
            
            st.session_state.setdefault("cfg_weight_clopening", 1)
            st.slider("Soir→Jour", 0, 10, key="cfg_weight_clopening", help="Pénalité repos court")
        
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
