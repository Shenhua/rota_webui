# Legacy v2.9 — Complete Feature Specification

> This document is the authoritative reference for reimplementing the Rota Optimizer.
> Based on thorough analysis of `legacy_v29.py` (1032 lines) and user documentation.

---

## 1. Data Model

### 1.1 Person Attributes (from CSV)

```python
Person = {
    "n":    str,          # name (required)
    "wd":   int,          # workdays_per_week (0-5) 
    "pat":  int,          # weeks_pattern (≥1, repeating cycle)
    "pn":   bool,         # prefers_night
    "ne":   bool,         # no_evening (avoid evenings)
    "mxn":  int,          # max_nights (cap over horizon, default=10^6)
    "edo":  bool,         # edo_eligible
    "edof": str,          # edo_fixed_day (Lun|Mar|Mer|Jeu|Ven or "")
    "team": str,          # optional team label
}
```

### 1.2 Shift Types

| Internal | Display | Hours | Notes |
|----------|---------|-------|-------|
| D | J (Jour) | 10h | Day shift |
| E | S (Soir) | 10h | Evening shift |
| N | N (Nuit) | 12h | Night shift |
| A | A (Admin) | 8h | Admin (solo, not paired) |
| - | OFF | 0h | Rest day |
| - | EDO | 0h | Earned Day Off |
| - | EDO* | 0h | EDO moved (fixed day was busy) |

### 1.3 Days

```python
JOURS = ["Lun", "Mar", "Mer", "Jeu", "Ven"]  # Mon-Fri only
HEURES = {"D": 10, "E": 10, "N": 12, "A": 8}
```

---

## 2. Scheduling Model

### 2.1 Key Concept: PAIR SCHEDULING

> **CRITICAL**: Each shift slot (except Admin) requires **2 people working together**.

```python
for s in ["N", "E", "D", "A"]:
    slots = staff[w][day][s]  # Number of slots for this shift type
    for ps in range(1, slots + 1):
        need = 2 if s != "A" else 1  # <-- PAIRS
        take = pick_candidates(w, di, day, s, need)
        row = [week, day, shift, pair_number, person_A, person_B]
```

**Output Format**:
```
Semaine, Jour, Poste, Pair#, Pers_A, Pers_B
1, Lun, N, 1, Alice, Bob       # Night shift pair 1
1, Lun, N, 2, Charlie, Diana   # Night shift pair 2 (if needed)
1, Lun, A, 1, Eve, ""          # Admin is solo
```

### 2.2 Dynamic Staffing Derivation

The number of slots per shift type per day is **calculated dynamically** based on total available person-days:

```python
def derive_staffing(P, W, edo_plan):
    for w in week_range(W):
        # Total person-days available this week
        edo_count = sum(1 for p in P if p["edo"] and p["n"] in edo_plan[w])
        person_days = sum(p["wd"] for p in P) - edo_count
        
        # Odd number? Add 1 Admin slot (solo)
        admin_days = 1 if (person_days % 2) else 0
        remaining = person_days - admin_days
        
        # Night shifts: 1 pair per day = 2 people × 5 days = 10 person-days
        baseN = 1  # pairs per day
        pairsN = baseN * 5
        
        # Remaining pairs distributed evenly across Day/Evening
        pairs = max(0, (remaining - 2*pairsN) // 2)
        
        # Initialize: 1 night pair per day, 0 day/evening
        per_day = {d: {"D": 0, "E": 0, "N": baseN, "A": 0} for d in JOURS}
        if admin_days:
            per_day[JOURS[0]]["A"] = 1
        
        # Distribute remaining pairs round-robin to Day/Evening
        fill = list(itertools.product(JOURS, ["D", "E"]))
        i = 0
        while pairs > 0:
            d, s = fill[i % len(fill)]
            per_day[d][s] += 1
            pairs -= 1
            i += 1
```

**Result**: Each week has different staffing targets based on EDO allocation.

---

## 3. EDO (Earned Day Off) System

### 3.1 Alternation Logic

EDO-eligible people are split into two halves, alternating by week:

```python
def build_edo_plan(P, W, fixed_global=None):
    plan = {w: set() for w in range(1, W+1)}
    
    # Group by workdays_per_week
    groups = {}
    for p in P:
        if p["edo"]:
            groups.setdefault(p["wd"], []).append(p["n"])
    
    # Split each group in half, alternate by week
    for arr in groups.values():
        arr = sorted(arr)
        half = (len(arr) + 1) // 2
        for w in range(1, W+1):
            take = arr[:half] if (w % 2) else arr[half:]
            plan[w].update(take)
    
    return plan, {p["n"]: (p["edof"] or fixed_global or "") for p in P}
```

### 3.2 EDO Day Assignment

1. If person has `edo_fixed_day` and that day is OFF → mark as EDO
2. Else: first OFF day of the week becomes EDO
3. If fixed day was busy → mark as `EDO*` (conflict indicator)

---

## 4. Constraints

### 4.1 Hard Constraints

| # | Constraint | Implementation |
|---|------------|----------------|
| 1 | **One assignment per person per day** | `info[n]["last"][(w,day)]` tracking |
| 2 | **No work after night** | `ok_after_night(n, w, idx)`: if previous day was N, skip |
| 3 | **Pair requirement** | `need = 2 if s != "A" else 1` |
| 4 | **Max nights cap** | `info[n]["nights"] < caps[n]` |
| 5 | **Workdays target per week** | `info[n]["wkdays"][w] < target` |
| 6 | **Horizon total target** | `remain_total(n) > 0` (when hard_mode=enforce) |

### 4.2 Soft Constraints (Optimization)

Candidates are sorted by multiple criteria (lower = better):

```python
cand.sort(key=lambda n: (
    team_share_gap(n, w),           # Inter-team night share
    rate_deficit_night(n, mode),    # Night fairness (rate or count)
    bad_e_to_d(n, w, di, s),        # Evening→Day transition penalty
    avg_deficit(n, "E", eve_mode),  # Evening fairness
    (s == "E" and noE[n]),          # Avoid evenings for no_evening people
    -(s == "N" and prefers[n]),     # Prioritize night-preferring people
    -remain_total(n),               # People with more remaining days
    info[n]["cnt"][s],              # Fewer shifts of this type
    info[n]["wkdays"][w],           # Fewer days this week
))
```

---

## 5. Fairness Modes

### 5.1 Cohort Definition (`--fairness-cohorts`)

| Value | Behavior |
|-------|----------|
| `none` | All people in one group |
| `by-wd` | Group by `workdays_per_week` (e.g., "4j", "3j") |

### 5.2 Night/Evening Fairness (`--night-fairness`, `--evening-fairness`)

| Value | Behavior |
|-------|----------|
| `off` | No fairness optimization |
| `global` | Minimize variance across all people |
| `cohort` | Minimize variance within each cohort |

### 5.3 Night Fairness Mode (`--night-fairness-mode`)

| Value | Behavior |
|-------|----------|
| `count` | Absolute number of nights |
| `rate` | Nights ÷ total target (proportional) — **recommended** |

### 5.4 Inter-Team Night Share (`--inter-team-night-share`)

| Value | Behavior |
|-------|----------|
| `off` | No balancing |
| `proportional` | Proportional to total workdays |
| `global` | Equal share regardless of team size |

---

## 6. Validation & Scoring

### 6.1 Validation Checks

```python
def validate(rows, info, W, P, edo_plan, ttarget):
    return {
        "doublons_jour": duplicates,           # Same person twice on same day
        "Nuit_suivie_travail": n2o,            # Worked after night shift
        "Soir_vers_Jour": e2d,                 # Day shift after evening
        "Ecarts_hebdo_jours": weekly_misses,   # Weekly target not met
        "Ecarts_horizon_personnes": total_miss, # Horizon total not met
        "Slots_vides": vacancies,              # Unfilled pair slots
    }
```

### 6.2 Scoring Formula

```python
score = (
    10 * Slots_vides +           # HIGHEST: unfilled slots
    5  * doublons_jour +         # Duplicates
    3  * Nuit_suivie_travail +   # Night→work violations
    1  * Soir_vers_Jour +        # Evening→day transitions
    2  * Ecarts_hebdo_jours +    # Weekly deviations
    2  * Ecarts_horizon_personnes + # Horizon deviations
    10 * stdN +                  # Night fairness std dev (sum across cohorts)
    3  * stdE                    # Evening fairness std dev
)
```

**Lower score = better solution**

---

## 7. Post-Processing

### 7.1 Greedy Rebalance (`--post-rebalance-steps N`)

After initial assignment, a local search swaps people to fix imbalances:

```python
def post_rebalance(rows, info, W, caps, ttarget, max_steps=200):
    for step in range(max_steps):
        for row in rows:
            w, d, s, _, a, b = row
            for person in [a, b]:
                if person has DEFICIT (total < target):
                    for other_person with SURPLUS:
                        if swap is valid (no conflicts):
                            swap them
                            break
```

### 7.2 Multi-Seed Optimization (`--seed N --tries T`)

Run the solver T times with seeds [N, N+1, ..., N+T-1], keep the best:

```python
best = None
best_score = float("inf")
for t in range(tries):
    seed = base_seed + t
    random.seed(seed)
    rows, info = schedule(...)
    if post_rebalance_steps > 0:
        rows, info = post_rebalance(rows, info, ...)
    score = score_solution(validate(...))
    if score < best_score:
        best = (rows, info); best_score = score; best_seed = seed
```

---

## 8. CLI Arguments

```bash
python legacy_v29.py \
    --pattern-csv PATH           # Required: team CSV
    --weeks N                    # Horizon (default: 12)
    --xlsx-path FILE             # Excel output
    --csv-path FILE              # CSV output
    --edo                        # Enable EDO
    --edo-jour-fixe {Lun|...}    # Global EDO day
    --fairness-cohorts {none|by-wd}
    --hard-average-mode {off|warn|enforce}
    --overassign-last-week       # Allow over-assignment on last week
    --night-fairness {off|global|cohort}
    --night-fairness-mode {count|rate}
    --evening-fairness {off|global|cohort}
    --inter-team-night-share {off|proportional|global}
    --post-rebalance-steps N     # Local search iterations
    --seed N                     # RNG seed
    --tries N                    # Multi-restart attempts
    --matrice-team-borders       # Excel team borders
    --no-spinner                 # Disable CLI animation
    -v | -vv                     # Verbosity levels
```

---

## 9. Excel Export Structure

### 9.1 Sheets

| Sheet | Content |
|-------|---------|
| `Tableau de bord` | KPIs, options, summary, seed info |
| `Matrice` | Person × Day grid with shift colors + counts table |
| `ParPoste_Statique` | By shift type: "Alice / Bob; Charlie / Diana" per day |
| `Synthèse` | Per-person totals (J/S/N/A, hours, EDO count) |
| `Technique` | Validation details, 48h check, fairness averages |
| `Planning — {Name}` | Per-person sheet with weekly view |

### 9.2 Pair Display in ParPoste_Statique

```
Jour:  Alice / Bob; Charlie / Diana
Soir:  Eve / Frank
Nuit:  Grace / Hugo
Admin: Isabelle
```

---

## 10. Summary: What Must Be Reimplemented

### Critical (Blocking)

1. **Pair scheduling model** — `need = 2 if s != "A" else 1`
2. **Dynamic staffing derivation** — `derive_staffing()`
3. **EDO alternation** — Half/half by week
4. **Multi-level candidate sorting** — 9-criteria sort key
5. **Post-rebalance local search**
6. **Multi-seed optimization**
7. **Pair display in exports** — "A / B" format

### Important

8. Inter-team night share balancing
9. Rate-based night fairness (proportional)
10. Weekly hours tracking (48h check)
11. Per-person Excel sheets

### Nice to Have

12. Team borders in matrix
13. EDO* conflict indicator
14. Spinner/verbose CLI

---

*Document created from analysis of `archive/legacy_v29.py` and user documentation.*
