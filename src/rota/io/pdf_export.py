"""
PDF Export for Rota Schedules
==============================
Generates A4 landscape PDF reports matching Excel export content.
Uses fpdf2 for lightweight PDF generation.
"""
import io
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from fpdf import FPDF

from rota.models.person import Person
from rota.solver.edo import JOURS, EDOPlan
from rota.solver.pairs import PairSchedule
from rota.solver.stats import calculate_person_stats
from rota.solver.validation import FairnessMetrics, ValidationResult
from rota.solver.weekend import WeekendResult
from rota.utils.logging_setup import get_logger

logger = get_logger("rota.io.pdf_export")

# Colors (RGB)
COLORS = {
    "header_bg": (68, 114, 196),    # Blue for headers
    "header_text": (255, 255, 255), # White text
    "day": (221, 238, 255),         # Light blue
    "night": (230, 204, 255),       # Light purple
    "soir": (255, 228, 204),        # Light orange
    "gap": (255, 200, 200),         # Light red for gaps
    "ok": (212, 237, 218),          # Green for OK
    "warning": (255, 243, 205),     # Yellow for warning
    "total_bg": (224, 224, 224),    # Grey for totals
}


class RotaPDF(FPDF):
    """Custom PDF class with headers and footers."""
    
    def __init__(self, title: str = "Planning Rota"):
        super().__init__(orientation="L", unit="mm", format="A4")
        self.title = title
        self.set_auto_page_break(auto=True, margin=15)
    
    def header(self):
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 10, self.title, border=0, align="C")
        self.ln(5)
        self.set_font("Helvetica", "", 8)
        self.cell(0, 5, f"Généré le {datetime.now().strftime('%Y-%m-%d %H:%M')}", border=0, align="C")
        self.ln(10)
    
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}/{{nb}}", align="C")


def export_schedule_to_pdf(
    schedule: PairSchedule,
    people: List[Person],
    edo_plan: EDOPlan,
    output: Union[str, Path, io.BytesIO],
    validation: Optional[ValidationResult] = None,
    fairness: Optional[FairnessMetrics] = None,
    weekend_result: Optional[WeekendResult] = None,
    config: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Export schedule to PDF with:
    - Page 1: Tableau de bord (KPIs)
    - Page 2+: Vue Manager (matrix)
    - Final pages: Synthèse (per-person stats)
    """
    config = config or {}
    weeks = schedule.weeks
    
    pdf = RotaPDF(title="Planning Rota")
    pdf.alias_nb_pages()
    
    # ============================================================
    # PAGE 1: TABLEAU DE BORD
    # ============================================================
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 10, "Tableau de Bord", ln=True, align="L")
    pdf.ln(5)
    
    # KPI table
    pdf.set_font("Helvetica", "", 10)
    kpi_data = [
        ("Effectif", str(len(people))),
        ("Semaines", str(weeks)),
        ("Score", f"{schedule.score:.2f}" if schedule.score else "N/A"),
    ]
    
    if validation:
        kpi_data.extend([
            ("", ""),  # Spacer
            ("--- Validation ---", ""),
            ("Slots vides", str(validation.slots_vides)),
            ("Violations Nuit->Travail", str(validation.nuit_suivie_travail)),
            ("Transitions Soir->Jour", str(validation.soir_vers_jour)),
        ])
    
    if weekend_result and weekend_result.assignments:
        kpi_data.extend([
            ("", ""),
            ("--- Week-end ---", ""),
            ("Assignations WE", str(len(weekend_result.assignments))),
            ("Statut WE", weekend_result.status),
        ])
    
    kpi_data.extend([
        ("", ""),
        ("--- Options ---", ""),
        ("EDO activé", "Oui" if config.get("edo_enabled") else "Non"),
        ("Seed", str(config.get("seed", "N/A"))),
    ])
    
    # Draw KPI table
    col1_width = 60
    col2_width = 40
    for label, value in kpi_data:
        if label.startswith("---"):
            pdf.set_font("Helvetica", "B", 10)
            pdf.cell(col1_width + col2_width, 6, label, ln=True)
            pdf.set_font("Helvetica", "", 10)
        elif label:
            pdf.cell(col1_width, 6, label, border=1)
            pdf.cell(col2_width, 6, value, border=1, ln=True)
        else:
            pdf.ln(3)
    
    # ============================================================
    # PAGE 2+: VUE MANAGER (Matrix) - Split by weeks if needed
    # ============================================================
    days_all = JOURS + ["Sam", "Dim"] if weekend_result else JOURS
    
    # Build full assignment map
    full_map = {}
    for a in schedule.assignments:
        if a.person_a:
            full_map[(a.person_a, a.week, a.day)] = a.shift
        if a.person_b:
            full_map[(a.person_b, a.week, a.day)] = a.shift
    
    if weekend_result:
        for a in weekend_result.assignments:
            key = (a.person.name, a.week, a.day)
            existing = full_map.get(key, "")
            full_map[key] = f"{existing}+{a.shift}" if existing else a.shift
    
    active_people = sorted([p.name for p in people if p.workdays_per_week > 0])
    
    # Calculate weeks per page (landscape A4 = 297mm width, ~250mm usable)
    weeks_per_page = 4
    cell_width = 8
    name_width = 35
    
    for page_start in range(0, weeks, weeks_per_page):
        page_end = min(page_start + weeks_per_page, weeks)
        
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, f"Vue Manager - Semaines {page_start + 1} à {page_end}", ln=True)
        pdf.ln(3)
        
        # Header row
        pdf.set_font("Helvetica", "B", 7)
        pdf.set_fill_color(*COLORS["header_bg"])
        pdf.set_text_color(*COLORS["header_text"])
        
        pdf.cell(name_width, 6, "Nom", border=1, fill=True)
        for w in range(page_start + 1, page_end + 1):
            for d in days_all:
                pdf.cell(cell_width, 6, d[:2], border=1, align="C", fill=True)
        pdf.ln()
        
        pdf.set_text_color(0, 0, 0)
        
        # Data rows
        pdf.set_font("Helvetica", "", 6)
        for name in active_people:
            pdf.cell(name_width, 5, name[:18], border=1)
            
            for w in range(page_start + 1, page_end + 1):
                for d in days_all:
                    val = full_map.get((name, w, d), "")
                    
                    # Color based on shift
                    if "N" in val:
                        pdf.set_fill_color(*COLORS["night"])
                    elif "D" in val:
                        pdf.set_fill_color(*COLORS["day"])
                    elif val == "S":
                        pdf.set_fill_color(*COLORS["soir"])
                    else:
                        pdf.set_fill_color(255, 255, 255)
                    
                    display = {"D": "J", "N": "N", "S": "S"}.get(val, val[:2] if val else "")
                    pdf.cell(cell_width, 5, display, border=1, align="C", fill=True)
            pdf.ln()
    
    # ============================================================
    # FINAL PAGE: SYNTHÈSE
    # ============================================================
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "Synthèse par Personne", ln=True)
    pdf.ln(3)
    
    # Header
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*COLORS["header_bg"])
    pdf.set_text_color(*COLORS["header_text"])
    
    has_weekend = weekend_result and weekend_result.assignments
    if has_weekend:
        # Weekday stats -> Target/Gap -> Weekend stats -> Final Total
        cols = ["Nom", "Jours", "Soirs", "Nuits", "Total", "Cible", "Écart", "EDO", "WE Shifts", "Total+WE"]
        widths = [40, 15, 15, 15, 15, 15, 15, 15, 20, 20]
    else:
        cols = ["Nom", "Jours", "Soirs", "Nuits", "Total", "Cible", "Écart", "EDO"]
        widths = [40, 15, 15, 15, 15, 15, 15, 15]

    for col, w in zip(cols, widths):
        pdf.cell(w, 6, col, border=1, align="C", fill=True)
    pdf.ln()
    
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 8)
    
    # Use centralized stats calculation
    person_stats = calculate_person_stats(schedule, people, edo_plan)
    
    # Count WE shifts if needed
    we_counts = {}
    if has_weekend:
        for a in weekend_result.assignments:
            we_counts[a.person.name] = we_counts.get(a.person.name, 0) + 1
    
    # Data rows
    for ps in sorted(person_stats, key=lambda x: x.name):
        if ps.workdays_per_week == 0:
            continue
        
        # Calculate Stats matching Web Dashboard logic
        # ps.total is Weekday Total (calculated by calculate_person_stats using schedule only)
        # ps.target is derived from contract (weeks * days_per_week)
        
        we_shifts = we_counts.get(ps.name, 0)
        total_sem = ps.total
        total_we = total_sem + we_shifts if has_weekend else total_sem
        
        # Gap should be Weekday Total vs Target (to avoid rewarding weekend work against weekday deficit)
        ecart = total_sem - ps.target
        
        # Color for écart
        ecart_color = (0, 0, 0)  # Default black
        if ecart < 0:
            ecart_color = (220, 0, 0)  # Red
        elif ecart > 0:
            ecart_color = (0, 150, 0)  # Green
        
        if has_weekend:
            # Nom, J, S, N, Total(Sem), Cible, Ecart, EDO, WE, Total+WE
            row_data = [
                ps.name[:20], 
                str(ps.jours), str(ps.soirs), str(ps.nuits), 
                str(total_sem), str(ps.target), str(ecart), str(ps.edo_weeks),
                str(we_shifts), str(total_we)
            ]
            ecart_idx = 6 # Index of "Écart" column
        else:
            row_data = [ps.name[:20], str(ps.jours), str(ps.soirs), str(ps.nuits), str(total_sem), str(ps.target), str(ecart), str(ps.edo_weeks)]
            ecart_idx = 6

        for i, (val, w) in enumerate(zip(row_data, widths)):
            # Only apply ecart color to the Écart column
            if i == ecart_idx:
                pdf.set_text_color(*ecart_color)
            else:
                pdf.set_text_color(0, 0, 0)
            pdf.cell(w, 5, val, border=1, align="C" if w < 40 else "L")
        pdf.ln()
        
        pdf.set_text_color(0, 0, 0)
    
    # Save PDF
    if isinstance(output, (str, Path)):
        pdf.output(str(output))
    else:
        pdf_bytes = pdf.output()
        output.write(pdf_bytes)
        output.seek(0)  # Reset for reading
    
    logger.info(f"PDF export complete: {len(active_people)} people, {weeks} weeks")
