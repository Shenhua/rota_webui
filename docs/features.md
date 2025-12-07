# Rota Tool — Feature Reference

Complete list of features from the legacy implementation that must be preserved in the refactor.

## Core Scheduling Features

### Shift Types
| Code | Name | French | Hours |
|------|------|--------|-------|
| J | Day | Jour | 10h |
| S | Evening | Soir | 10h |
| N | Night | Nuit | 12h |
| A | Admin | Admin | 8h |
| OFF | Rest day | Repos | - |
| EDO | Earned Day Off | Jour de repos gagné | - |

### Person Attributes (from CSV)
- `name` — Person's name
- `workdays_per_week` — Target days per week (e.g., 4 or 5)
- `weeks_pattern` — Pattern cycle length (1 = weekly)
- `prefers_night` — Bool, prioritize for night shifts
- `no_evening` — Bool, avoid evening shifts
- `max_nights` — Maximum night shifts over horizon
- `edo_eligible` — Bool, eligible for earned days off
- `edo_fixed_day` — Preferred EDO day (Lun/Mar/Mer/Jeu/Ven)
- `team` — Optional team assignment for grouping

### Scheduling Rules (Hard Constraints)
1. **One shift per day** — No double assignments
2. **No work after night** — Day after night shift is rest
3. **Coverage requirements** — Minimum staff per shift type per day
4. **Max days per week** — Typically 4 or 5 based on contract
5. **EDO allocation** — Alternating eligible people across weeks
6. **Night cap** — Respect `max_nights` per person

### Scheduling Rules (Soft/Fairness)
1. **Fair night distribution** — Equal nights across cohorts
2. **Fair evening distribution** — Equal evenings across cohorts
3. **Cohort-based fairness** — Group by `workdays_per_week`
4. **Avoid evening→day transitions** — Soft penalty
5. **Night preference** — Prioritize `prefers_night` people
6. **No-evening preference** — Avoid evenings for `no_evening` people

## Solver Features

### Multi-restart Optimization
- `--tries N` — Run N random restarts, keep best
- `--seed S` — Reproducible runs (S, S+1, S+2, ...)
- Scoring function combines violations + fairness std dev

### Scoring Components
```python
score = (
    10 * vacant_slots +
    5 * duplicate_assignments +
    3 * night_followed_by_work +
    1 * evening_to_day_transition +
    2 * weekly_day_deviation +
    2 * horizon_total_deviation +
    10 * night_fairness_stddev +
    3 * evening_fairness_stddev
)
```

### Post-processing
- `--post-rebalance-steps N` — Local search to fix imbalances

## UI Features (Streamlit)

### Input
- CSV file upload for team data
- YAML file upload for configuration
- Editable service needs (coverage targets per day/shift)
- Preset management (save/load YAML presets)

### Configuration Options
- Calendar mode: 5 days (Mon–Fri) or 7 days (Mon–Sun)
- Appearance: Team tint intensity, color theme (Pastel/Colorblind)
- Fairness mode: None, by-workdays, fair-nights, fair-weekends
- EDO toggle: Enable/disable earned days off
- Max nights sequence, max evenings sequence
- Min rest after night
- Impose targets toggle

### Results Display
- **Matrix view** — Person × Day with shift colors + team tinting
- **Counts table** — Staff counts per shift per day (gradient colored)
- **Coverage table** — Required vs Assigned with RAG coloring
- **Admin panel** — Per-person totals, nights by team
- **Metadata** — Weeks, seed, calendar mode, etc.

### Color Coding
| Shift | Color (Pastel) | Color (Colorblind) |
|-------|----------------|-------------------|
| J | Yellow #FFF8E1 | Blue #DCEAF7 |
| S | Pink #FDECEC | Orange #F8E5CC |
| N | Blue #EAF2FD | Purple #E8DDF0 |
| A | Grey #F5F6F7 | Grey #E9ECEF |
| OFF | Light Grey | Light Grey |
| EDO | Light Blue | Light Blue |

### Coverage RAG Status
- 🟢 Green: Assigned ≥ Required
- 🟠 Orange: Deficit of 1
- 🔴 Red: Deficit of 2+

## Export Features

### Excel Export
Multi-sheet workbook with:
1. **Tableau de bord** — Dashboard with KPIs
2. **Matrice** — Full schedule grid with colors
3. **ParPoste_Statique** — Staff list by shift type
4. **Synthèse** — Person summary (totals, hours)
5. **Technique** — Validation details
6. **Per-person sheets** — Individual schedules (optional)

### Excel Formatting
- Week separators (double black borders)
- Alternating week header shading
- Shift-specific cell colors
- Team grouping with borders
- Merged cells for week headers

### Other Exports
- CSV assignments download
- Debug bundle (ZIP with JSON + CSVs)
- YAML preset export

## CLI Features (`legacy_v29.py`)

```bash
python legacy_v29.py \
  --pattern-csv team.csv \
  --weeks 12 \
  --xlsx-path output.xlsx \
  --csv-path output.csv \
  --edo \
  --edo-jour-fixe Mer \
  --fairness-cohorts by-wd \
  --hard-average-mode warn|enforce|off \
  --overassign-last-week \
  --night-fairness off|global|cohort \
  --night-fairness-mode count|rate \
  --evening-fairness off|global|cohort \
  --inter-team-night-share off|proportional|global \
  --post-rebalance-steps 300 \
  --tries 20 \
  --seed 12345 \
  --matrice-team-borders \
  -v|-vv
```

## Features NOT Currently Working

1. ❌ **Solver-to-UI connection** — Results are dummy data
2. ❌ **Excel export from UI** — Doesn't use real schedule
3. ❌ **Weekend scheduling** — Only Mon–Fri in legacy solver
4. ❌ **In-UI person editing** — Must use CSV upload
