"""
Compatibility shim exposing `solve(...)` for the legacy solver interface.

The Streamlit UI (and bench script) import `rota.engine.solve`,
so this module forwards to the overlay wrapper which chooses the best restart
using score + targets penalty.
"""
from .targets_overlay import solve as solve
from .config import SolveConfig

__all__ = ["solve", "SolveConfig"]
