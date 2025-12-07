
# src/rota/engine/targets_overlay.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
import importlib
import copy
import pandas as pd

from .config import SolveConfig
from .targets import normalize_targets_payload, apply_edo_policy, coverage_from_assignments, targets_penalty
from . import utils_bundle

@dataclass
class SolveResult:
    assignments: pd.DataFrame
    summary: Dict[str, Any]
    metrics_json: Dict[str, Any]

def _import_legacy():
    try:
        return importlib.import_module("rota.engine.solve_legacy")
    except Exception:
        # Fallback to direct legacy module
        return importlib.import_module("legacy.legacy_v29")

def _call_legacy_solve(legacy_mod, csv_path: str, cfg: SolveConfig):
    # Legacy exposes `solve(csv_path, cfg)` returning an object with .assignments, .summary, .metrics_json
    return legacy_mod.solve(csv_path, cfg)

def _attach_coverage(res: SolveResult, cfg: SolveConfig, targets_df: pd.DataFrame) -> SolveResult:
    cov = coverage_from_assignments(apply_edo_policy(res.assignments, getattr(cfg, 'allow_edo', True)), targets_df)
    pen = targets_penalty(cov, cfg.targets_weights_by_shift, cfg.targets_weight)
    res.metrics_json = dict(res.metrics_json or {})
    res.metrics_json["coverage"] = cov.to_dict(orient="records") if not cov.empty else []
    res.metrics_json["targets_penalty"] = pen
    res.summary = dict(res.summary or {})
    res.summary.setdefault("score", 0.0)
    res.summary["targets_penalty"] = pen
    res.summary["coverage_cells"] = 0 if cov is None or cov.empty else int((cov["gap"] < 0).sum())
    return res

def solve(csv_path: str, cfg: Optional[SolveConfig] = None) -> SolveResult:
    """
    Overlay that can optionally impose service needs 'targets' by reranking restarts.
    - If cfg.impose_targets is False or no targets provided: just forward to legacy (attach coverage if possible).
    - If True: run multiple restarts (outer loop) and select best by composite score and tie‑breakers.
    """
    legacy = _import_legacy()
    cfg = cfg or SolveConfig()
    assign_df_u, targets_df_u, cfg_json = utils_bundle.load_bundle(csv_path)

    # Hydrate cfg from config.json (without clobbering already-specified fields)
    for k, v in (cfg_json or {}).items():
        try:
            if not hasattr(cfg, k) or getattr(cfg, k) in (None, False, 0, {}, []):
                setattr(cfg, k, v)
        except Exception:
            pass

    targets_payload = cfg.coverage_targets or cfg.targets or cfg.service_needs
    if targets_payload:
        targets_df = normalize_targets_payload(targets_payload)
    elif targets_df_u is not None and not targets_df_u.empty:
        targets_df = targets_df_u[["week","day","shift","required"]].copy()
    else:
        targets_df = pd.DataFrame(columns=["week","day","shift","required"])

    if not bool(cfg.impose_targets) or targets_df.empty:
        res = _call_legacy_solve(legacy, csv_path, cfg)
        return _attach_coverage(res, cfg, targets_df)

    # Imposed: run multiple restarts externally and select best by composite score
    outer_tries = max(1, int(cfg.tries))
    inner_cfg = copy.deepcopy(cfg)
    try:
        inner_cfg.tries = 1
    except Exception:
        pass

    best: Optional[SolveResult] = None
    best_key: Optional[Tuple[float, float, float]] = None  # (score_total, penalty, legacy_score) ascending
    best_cov = None
    best_pen = None

    for _ in range(outer_tries):
        res = _call_legacy_solve(legacy, csv_path, inner_cfg)
        cov = coverage_from_assignments(apply_edo_policy(res.assignments, getattr(cfg, 'allow_edo', True)), targets_df)
        pen = targets_penalty(cov, cfg.targets_weights_by_shift, cfg.targets_weight)
        legacy_score = float(res.summary.get("score", 0.0)) if isinstance(res.summary, dict) else 0.0
        score_total = legacy_score + float(cfg.alpha) * float(pen)
        # Lower score_total is better if legacy is a minimization score; if it's higher-is-better, invert here.
        key = (score_total, pen, legacy_score)
        if best is None or key < best_key:
            best = res
            best_key = key
            best_cov = cov.copy()
            best_pen = pen

    # Attach metrics and composite score
    assert best is not None
    best.metrics_json = dict(best.metrics_json or {})
    best.metrics_json["targets_snapshot"] = targets_df.to_dict(orient="records") if not targets_df.empty else []
    best.metrics_json["config_snapshot"] = {k: getattr(cfg, k) for k in ["impose_targets","allow_edo","alpha","tries","weeks","targets_weight"] if hasattr(cfg,k)}
    best.metrics_json["coverage"] = best_cov.to_dict(orient="records") if best_cov is not None and not best_cov.empty else []
    best.metrics_json["targets_penalty"] = best_pen
    best.summary = dict(best.summary or {})
    best.summary["targets_penalty"] = best_pen
    best.summary["coverage_cells"] = 0 if best_cov is None or best_cov.empty else int((best_cov["gap"] < 0).sum())
    best.summary["score_with_targets"] = float(best.summary.get("score", 0.0)) + float(cfg.alpha) * float(best_pen)
    return best
