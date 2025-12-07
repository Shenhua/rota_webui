"""Team editor UI component for Streamlit."""
from typing import List, Optional, Callable
import pandas as pd
import streamlit as st

from rota.models.person import Person
from rota.io.csv_loader import load_team, team_to_dataframe


def render_team_editor(
    team: List[Person],
    on_change: Optional[Callable[[List[Person]], None]] = None,
    key_prefix: str = "team_editor",
) -> List[Person]:
    """
    Render an editable team table in Streamlit.
    
    Args:
        team: Current team list
        on_change: Callback when team changes
        key_prefix: Unique key prefix for Streamlit widgets
        
    Returns:
        Updated team list
    """
    st.subheader("👥 Team Members")
    
    # Convert team to DataFrame for editing
    if team:
        df = team_to_dataframe(team)
    else:
        df = pd.DataFrame(columns=[
            "name", "workdays_per_week", "weeks_pattern", "prefers_night",
            "no_evening", "max_nights", "edo_eligible", "edo_fixed_day", "team"
        ])
    
    # Column configuration for better editing
    column_config = {
        "name": st.column_config.TextColumn("Name", required=True),
        "workdays_per_week": st.column_config.NumberColumn(
            "Days/Week", min_value=1, max_value=7, default=5
        ),
        "weeks_pattern": st.column_config.NumberColumn(
            "Pattern", min_value=1, max_value=4, default=1
        ),
        "prefers_night": st.column_config.CheckboxColumn("Prefers Night", default=False),
        "no_evening": st.column_config.CheckboxColumn("No Evening", default=False),
        "max_nights": st.column_config.NumberColumn(
            "Max Nights", min_value=0, max_value=99, default=99
        ),
        "edo_eligible": st.column_config.CheckboxColumn("EDO Eligible", default=False),
        "edo_fixed_day": st.column_config.SelectboxColumn(
            "EDO Day", options=["", "Lun", "Mar", "Mer", "Jeu", "Ven"]
        ),
        "team": st.column_config.TextColumn("Team"),
    }
    
    # Editable data editor
    edited_df = st.data_editor(
        df,
        column_config=column_config,
        num_rows="dynamic",
        use_container_width=True,
        key=f"{key_prefix}_editor",
        hide_index=True,
    )
    
    # Convert back to Person list
    updated_team = []
    for idx, row in edited_df.iterrows():
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        
        person = Person(
            name=name,
            workdays_per_week=int(row.get("workdays_per_week", 5) or 5),
            weeks_pattern=int(row.get("weeks_pattern", 1) or 1),
            prefers_night=bool(row.get("prefers_night", False)),
            no_evening=bool(row.get("no_evening", False)),
            max_nights=int(row.get("max_nights", 99) or 99),
            edo_eligible=bool(row.get("edo_eligible", False)),
            edo_fixed_day=str(row.get("edo_fixed_day", "")).strip() or None,
            team=str(row.get("team", "")).strip(),
            id=idx,
        )
        updated_team.append(person)
    
    # Action buttons
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("➕ Add Person", key=f"{key_prefix}_add"):
            new_person = Person(name=f"New Person {len(updated_team) + 1}")
            updated_team.append(new_person)
            if on_change:
                on_change(updated_team)
            st.rerun()
    
    with col2:
        # CSV export
        csv_data = team_to_dataframe(updated_team).to_csv(index=False)
        st.download_button(
            "📥 Export CSV",
            data=csv_data,
            file_name="team.csv",
            mime="text/csv",
            key=f"{key_prefix}_export",
        )
    
    with col3:
        # Quick stats
        st.metric("Total", len(updated_team))
    
    # Check if team changed
    if len(updated_team) != len(team):
        if on_change:
            on_change(updated_team)
    else:
        for i, (old, new) in enumerate(zip(team, updated_team)):
            if old.name != new.name or old.workdays_per_week != new.workdays_per_week:
                if on_change:
                    on_change(updated_team)
                break
    
    return updated_team


def render_team_import(
    key_prefix: str = "team_import",
) -> Optional[List[Person]]:
    """
    Render CSV import widget.
    
    Returns:
        List of people if file uploaded, None otherwise
    """
    uploaded_file = st.file_uploader(
        "Upload team CSV",
        type=["csv"],
        key=f"{key_prefix}_uploader",
        help="CSV with columns: name, workdays_per_week, prefers_night, etc."
    )
    
    if uploaded_file is not None:
        try:
            df = pd.read_csv(uploaded_file)
            people = load_team(df)
            st.success(f"✅ Loaded {len(people)} people")
            return people
        except Exception as e:
            st.error(f"Error loading CSV: {e}")
    
    return None
