
# tests/test_targets_overlay.py
import pandas as pd
from rota.engine.config import SolveConfig
from rota.engine.targets_overlay import SolveResult
from rota.engine.targets import normalize_targets_payload, coverage_from_assignments, targets_penalty

def test_normalize_targets_payload_list():
    payload = {"list":[{"week":1,"day":"Lun","shift":"J","required":2}]}
    df = normalize_targets_payload(payload)
    assert list(df.columns) == ["week","day","shift","required"]
    assert df.iloc[0].to_dict() == {"week":1,"day":"Lun","shift":"J","required":2}

def test_coverage_and_penalty():
    assignments = pd.DataFrame([
        {"name":"A","week":1,"day":"Lun","shift":"J"},
        {"name":"B","week":1,"day":"Lun","shift":"J"},
        {"name":"C","week":1,"day":"Lun","shift":"S"},
    ])
    targets = pd.DataFrame([
        {"week":1,"day":"Lun","shift":"J","required":3},
        {"week":1,"day":"Lun","shift":"S","required":1},
    ])
    cov = coverage_from_assignments(assignments, targets)
    # For J: assigned=2, required=3 → gap = -1
    # For S: assigned=1, required=1 → gap = 0
    pen = targets_penalty(cov, {"J":1.0,"S":1.0,"N":1.0,"A":1.0,"OFF":1.0,"EDO":1.0}, 1.0)
    assert pen == 1.0
