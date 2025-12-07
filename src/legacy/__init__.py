# src/legacy/__init__.py
try:
    from .legacy_v29 import solve  # seulement si ça existe vraiment
    __all__ = ["solve"]
except Exception:
    __all__ = []