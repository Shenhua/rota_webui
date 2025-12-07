
from __future__ import annotations
import os, json, zipfile
import pandas as pd

_TARGET_FILENAMES = ["targets.csv", "targets_from_editor.csv"]
_CONFIG_FILENAMES = ["config.json", "sidebar_config.json"]

def _read_csv(path):
    try:
        return pd.read_csv(path)
    except Exception:
        return None

def _read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _pick_first_csv(dirpath: str, candidates):
    for name in candidates:
        p = os.path.join(dirpath, name)
        if os.path.exists(p):
            df = _read_csv(p)
            if df is not None:
                return df
    return None

def _pick_first_json(dirpath: str, candidates):
    cfg = {}
    for name in candidates:
        p = os.path.join(dirpath, name)
        if os.path.exists(p):
            data = _read_json(p)
            # Merge shallowly, last wins
            if data:
                cfg.update(data)
    return cfg

def load_bundle(input_path: str):
    """Supports:
    - directory containing assignments.csv / targets*.csv / config*.json
    - zip archive containing those filenames at root
    - single assignments.csv with optional sidecars:
        <base>.targets.csv / <base>.config.json OR files located in the same directory:
        targets.csv, targets_from_editor.csv, config.json, sidebar_config.json
    Returns (assignments_df|None, targets_df|None, config_dict)
    """
    if not input_path:
        return None, None, {}
    if os.path.isdir(input_path):
        assignments = _read_csv(os.path.join(input_path, "assignments.csv"))
        targets = _pick_first_csv(input_path, _TARGET_FILENAMES)
        cfg = _pick_first_json(input_path, _CONFIG_FILENAMES)
        return assignments, targets, cfg

    low = input_path.lower()
    if low.endswith(".zip"):
        with zipfile.ZipFile(input_path) as z:
            names = set(z.namelist())
            def zcsv(name):
                try:
                    if name in names:
                        return pd.read_csv(z.open(name))
                except Exception:
                    return None
            def zjson(name):
                try:
                    if name in names:
                        return json.load(z.open(name))
                except Exception:
                    return {}
            assignments = zcsv("assignments.csv")
            # try both target filenames
            targets = None
            for nm in _TARGET_FILENAMES:
                if nm in names and targets is None:
                    targets = zcsv(nm)
            # merge config files (config.json + sidebar_config.json if present)
            cfg = {}
            for nm in _CONFIG_FILENAMES:
                if nm in names:
                    data = zjson(nm) or {}
                    cfg.update(data)
            return assignments, targets, cfg

    # single CSV path
    assignments = _read_csv(input_path)
    base, _ = os.path.splitext(input_path)
    # sidecars with same base
    targets = _read_csv(base + ".targets.csv")
    cfg = _read_json(base + ".config.json")
    # if not present, also try sibling files in the same folder
    dirpath = os.path.dirname(input_path) or "."
    if targets is None:
        sib_targets = _pick_first_csv(dirpath, _TARGET_FILENAMES)
        if sib_targets is not None:
            targets = sib_targets
    sib_cfg = _pick_first_json(dirpath, _CONFIG_FILENAMES)
    if sib_cfg:
        cfg.update(sib_cfg)
    return assignments, targets, cfg
