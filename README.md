# Rota UI + Targets Overlay (Option A)

## Structure
- `app/streamlit_app.py` — UI (v4.10) avec "Besoins de service" éditables, presets YAML, toggle "Imposer au solveur".
- `src/rota/engine/targets_overlay.py` — wrapper `solve` qui gère les besoins et appelle votre solveur legacy.
- `src/rota/engine/config.py` & `targets.py` — dataclass, normalisation, couverture & pénalité.
- `tests/test_targets_overlay.py` — mini tests.
- `requirements.txt`

## Intégration — Option A (non intrusive)
L'app importe :
```python
from rota.engine.targets_overlay import solve
from rota.engine.config import SolveConfig  # si dispo
```
Le wrapper tentera d'appeler automatiquement votre solveur legacy via l'un de ces modules :
- `rota.engine.solve_legacy`
- `rota.engine.solve`
- `rota.legacy.legacy_v29`
- `legacy.legacy_v29`

> Vous n'avez rien à renommer si votre legacy est déjà présent sous l'un de ces chemins.

## Installation
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export PYTHONPATH=$PWD/src  # Windows PowerShell: $env:PYTHONPATH="$PWD/src"
streamlit run app/streamlit_app.py
```

## Notes
- Si "Activer les EDO" est désactivé dans l'UI, l'overlay mappe EDO→OFF pour la couverture/penalité (comme l'UI).
- En mode "Imposer", l'overlay fait plusieurs restarts externes et choisit la meilleure solution selon (pénalité, score).
