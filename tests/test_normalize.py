import pandas as pd
from rota.ui.utils import normalize_assignments_columns

def test_normalize_basic():
    df = pd.read_csv('tests/data/team_small.csv')
    out = normalize_assignments_columns(df)
    assert list(out.columns) == ["name","week","day","shift"]
    assert len(out) == 5
    assert {"J","S","N","OFF","EDO"}.issubset(set(out['shift']))