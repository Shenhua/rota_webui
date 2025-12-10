---
description: How to run and test the Rota Optimizer
---

# Rota Optimizer Workflow

## Quick Start

// turbo
1. Set PYTHONPATH and run tests:
```bash
cd /Users/mperrier/rota_refactor
PYTHONPATH=$PWD/src python -m pytest tests/ -q --tb=short
```

// turbo
2. Start the Streamlit UI:
```bash
PYTHONPATH=$PWD/src streamlit run app/streamlit_app.py
```

3. Open browser at http://localhost:8501

4. Upload a team CSV file (e.g., `team_dummy.csv`)

5. Configure settings in sidebar:
   - Semaines: Number of weeks (1-24)
   - Essais: Multi-seed attempts (1-50)
   - Repos après nuit: Enable night rest constraint
   - EDO activé: Enable earned day off

6. Click "🚀 Générer Planning"

7. View results in tabs:
   - Matrice: Person × day grid
   - ParPoste: Pairs per shift
   - Synthèse: Statistics
   - Export: Download CSV/Excel

## Running Legacy Solver (for comparison)

// turbo
```bash
python archive/legacy_v29.py \
  --pattern-csv team_dummy.csv \
  --weeks 4 \
  --edo \
  --night-fairness cohort \
  --evening-fairness cohort \
  --seed 42 --tries 10 \
  --xlsx-path legacy_output.xlsx
```

## Running Tests

// turbo-all

```bash
# All tests
PYTHONPATH=$PWD/src python -m pytest tests/ -v

# Specific module tests
PYTHONPATH=$PWD/src python -m pytest tests/test_pairs.py -v
PYTHONPATH=$PWD/src python -m pytest tests/test_validation.py -v
PYTHONPATH=$PWD/src python -m pytest tests/test_optimizer.py -v
```

## CSV Format

```csv
name,workdays_per_week,weeks_pattern,prefers_night,no_evening,max_nights,edo_eligible,edo_fixed_day,team
Alice Martin,4,1,0,0,,1,,
Bob Dupont,4,1,0,0,,1,,
Claire Bernard,3,1,0,0,,0,,
```

Columns:
- `name`: Person name (required)
- `workdays_per_week`: 0-5 (required)
- `weeks_pattern`: Cycle length, usually 1
- `prefers_night`: 1 = prefers night shifts
- `no_evening`: 1 = avoid evening shifts
- `max_nights`: Cap on total nights (optional)
- `edo_eligible`: 1 = gets EDO every 2 weeks
- `edo_fixed_day`: Lun|Mar|Mer|Jeu|Ven (optional)
- `team`: Team label (optional)

## Troubleshooting

### Solver returns "infeasible"
- Team too small for required slots
- Night rest constraint reduces capacity
- Try: increase team size or disable "Repos après nuit"

### Slow performance
- Reduce weeks or time limit
- Use fewer tries initially
- Pair model is O(n²) on team size

### Missing module error
- Ensure PYTHONPATH is set: `PYTHONPATH=$PWD/src`
