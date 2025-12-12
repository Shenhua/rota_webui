import streamlit as st

from rota.models.rules import RULES, SHIFTS


def apply_styling():
    """Apply global CSS styling based on configuration."""
    
    # Generate CSS dynamically from SHIFTS
    css = "<style>\n"
    for code, cfg in SHIFTS.items():
        css_class = RULES.css_classes.get(code, f"shift-{code}")
        css += f".{css_class} {{ background-color: {cfg.color_bg} !important; color: {cfg.color_text}; font-weight: bold; }}\n"

    # Additional static styles
    css += """
    .shift-OFF { background-color: #F5F5F5 !important; color: #999; }
    .shift-EDO { background-color: #D8D8D8 !important; color: #666; font-style: italic; }
    .kpi-card { padding: 1rem; border-radius: 8px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; margin: 0.5rem 0; }
    .kpi-value { font-size: 2rem; font-weight: bold; }
    .kpi-label { font-size: 0.9rem; opacity: 0.9; }
    
    /* Improve dataframe density */
    div[data-testid="stDataFrame"] div[data-testid="stTable"] { font-size: 0.8rem; }
    
    /* Active tab highlight */
    button[data-baseweb="tab"][aria-selected="true"] {
        background-color: #667eea !important;
        color: white !important;
        border-radius: 4px;
        font-weight: bold;
    }
    
    /* Hide Streamlit deploy button */
    .stDeployButton { display: none !important; }
    
    </style>
    """
    
    st.markdown(css, unsafe_allow_html=True)
