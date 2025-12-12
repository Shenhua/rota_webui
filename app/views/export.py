"""
Export View
===========
Handles file downloads (Excel, PDF, CSV).
"""
import streamlit as st
import io
from app.state.session import SessionStateManager
from rota.io.pair_export import export_pairs_to_csv, export_pairs_to_excel, export_merged_calendar, export_weekend_to_excel
from rota.io.pdf_export import export_schedule_to_pdf

def render_downloads(state: SessionStateManager):
    """Render the download section."""
    if not state.schedule or state.schedule.status not in ["optimal", "feasible"]:
         st.warning("Veuillez générer un planning valide avant d'exporter.")
         return

    st.subheader("📥 Téléchargements")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # CSV Export
        csv_buffer = io.StringIO()
        export_pairs_to_csv(state.schedule, csv_buffer)
        st.download_button(
            "📥 Télécharger CSV",
            csv_buffer.getvalue(),
            "planning.csv",
            "text/csv"
        )
    
    with col2:
        # Excel Export
        xlsx_buffer = io.BytesIO()
        
        # Check for merged export
        should_merge = (
            state.merge_calendars and 
            state.w_result and 
            state.w_result.status in ["OPTIMAL", "FEASIBLE"]
        )
        
        # Use config from state
        config_dict = {
            "weeks": state.config_weeks, 
            "tries": state.config_tries, 
            "seed": state.best_seed
        }
        
        if should_merge:
            export_merged_calendar(
                state.schedule, state.w_result, state.people, state.edo_plan, xlsx_buffer,
                validation=state.validation, fairness=state.fairness,
                staffing=state.staffing,
                config=config_dict
            )
            filename = "planning_complet.xlsx"
        else:
            export_pairs_to_excel(
                state.schedule, state.people, state.edo_plan, xlsx_buffer,
                validation=state.validation, fairness=state.fairness,
                config=config_dict,
                staffing=state.staffing
            )
            filename = "planning_semaine.xlsx"

        st.download_button(
            f"📥 Télécharger Excel ({'Complet' if should_merge else 'Semaine'})",
            xlsx_buffer.getvalue(),
            filename,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    
    # PDF Export
    st.divider()
    
    pdf_buffer = io.BytesIO()
    weekend_for_pdf = state.w_result if should_merge else None
    
    # Needs explicit config passed
    pdf_config = {
        "weeks": state.config_weeks,
        "tries": state.config_tries,
        "seed": state.best_seed,
        "edo_enabled": True # Assumption for now, should read from Rules
    }
    
    export_schedule_to_pdf(
        state.schedule, state.people, state.edo_plan, pdf_buffer,
        validation=state.validation, fairness=state.fairness,
        weekend_result=weekend_for_pdf,
        config=pdf_config
    )
    
    st.download_button(
        "📄 Télécharger PDF (Rapport)",
        pdf_buffer.getvalue(),
        "planning_rapport.pdf",
        "application/pdf"
    )
