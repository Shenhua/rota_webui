# Feature Gap Analysis — Legacy vs Refactored App (UPDATED)

## Critical Discoveries from Legacy Code Review

### 🚨 CRITICAL MISSING: Pair Scheduling
The legacy system has **pair-based scheduling** - each shift slot (except Admin) requires **2 people working together**:

```python
# From legacy_v29.py
need = 2 if s!="A" else 1
take = pick_candidates(w,di,day,s,need)
if need==2:
    a,b = (take+["",""])[:2]
    row += [a,b]  # Two people per slot
```

This is **NOT** implemented in the new solver which assigns individuals, not pairs.

---

## Complete Feature Comparison

### Scheduling Model

| Feature | Legacy | New | Status |
|---------|--------|-----|--------|
| **Pair scheduling (2 per slot)** | ✓ `need=2` | Individual only | ❌ CRITICAL |
| **Multiple slots per shift** | ✓ `slots[w][day][s]` | Fixed coverage | ❌ CRITICAL |
| **Pair diversity** | ✓ Implicit via re-picks | Not implemented | ❌ MISSING |
| **Admin single person** | ✓ `need=1 if s=="A"` | Not differentiated | ❌ MISSING |
| Dynamic staffing per week | ✓ `derive_staffing()` | Static targets | ⚠️ PARTIAL |

### Shift Types
| Feature | Legacy | New | Status |
|---------|--------|-----|--------|
| J/S/N/A/OFF/EDO | ✓ | ✓ | ✅ |
| Hours per shift | ✓ `HEURES` | ✓ `shift.hours` | ✅ |
| Shift codes (D→J, E→S) | ✓ `CODE/REVCODE` | ✓ `ShiftType` | ✅ |

### Hard Constraints
| Constraint | Legacy | New | Status |
|------------|--------|-----|--------|
| One shift per person per day | ✓ | ✓ | ✅ |
| No work after night | ✓ `ok_after_night()` | ✓ `forbid_night_to_day` | ✅ |
| Coverage requirements | ✓ Per slot | ✓ Per shift total | ⚠️ Different model |
| Max days per week | ✓ via `wkdays[w]` | ✓ | ✅ |
| Max nights per person | ✓ `caps[n]` | ✓ `person.max_nights` | ✅ |
| Max consecutive nights | ✓ Implicit | ✓ `max_nights_sequence` | ✅ |
| EDO allocation | ✓ `edo_plan` | Model ready | ⚠️ PARTIAL |

### Soft Constraints
| Constraint | Legacy | New | Status |
|------------|--------|-----|--------|
| Night fairness (std dev) | ✓ `fairness_std(info, "N")` | ✓ `night_spread` | ✅ |
| Evening fairness | ✓ `fairness_std(info, "E")` | ✓ `eve_spread` | ✅ |
| Night preference | ✓ `prefers[n]` | ✓ `prefers_night` bonus | ✅ |
| Evening→day penalty | ✓ `Soir_vers_Jour` | ✓ `eve_day` indicator | ✅ |
| Weekly deviation | ✓ `Ecarts_hebdo_jours` | ✓ `over/under` | ✅ |
| Horizon total deviation | ✓ `Ecarts_horizon_personnes` | ✓ Implicit | ✅ |
| Inter-team night share | ✓ `night_share_weights()` | Not implemented | ❌ MISSING |

### Post-processing
| Feature | Legacy | New | Status |
|---------|--------|-----|--------|
| Multi-restart optimization | ✓ `--tries N` | OR-Tools built-in | ✅ Different |
| Post-rebalance local search | ✓ `post_rebalance()` | Not implemented | ❌ MISSING |
| Seed reproducibility | ✓ `--seed S` | Not implemented | ❌ MISSING |

### UI Features
| Feature | Legacy | New | Status |
|---------|--------|-----|--------|
| CSV upload | ✓ | ✓ | ✅ |
| YAML config upload | ✓ | Not implemented | ❌ |
| Coverage targets editor | ✓ | ✓ | ✅ |
| Matrix view | ✓ | ✓ | ✅ |
| Counts table | ✓ | ✓ | ✅ |
| Coverage vs targets | ✓ | ✓ | ✅ |
| RAG coloring | ✓ | ✓ (✅⚠️❌ icons) | ✅ |
| Team tint intensity | ✓ | Not implemented | ❌ |
| Color theme toggle | ✓ | Not implemented | ❌ |

### Export Features
| Feature | Legacy | New | Status |
|---------|--------|-----|--------|
| Tableau de bord | ✓ | ✓ | ✅ |
| Matrice | ✓ | ✓ | ✅ |
| Synthèse | ✓ | ✓ | ✅ |
| **Pair display ("A / B")** | ✓ | Individual only | ❌ CRITICAL |
| ParPoste_Statique | ✓ | Not implemented | ❌ |
| Technique | ✓ | Not implemented | ❌ |
| Per-person sheets | ✓ | Not implemented | ❌ |
| Week separators | ✓ | ✓ | ✅ |
| Team grouping borders | ✓ | Not implemented | ❌ |

---

## Priority Matrix

### 🔴 CRITICAL (Blocking - Different Model)
1. **Pair scheduling** - The entire scheduling model is different
   - Legacy: Assigns pairs (A, B) to each slot
   - New: Assigns individuals to shifts
   - **Impact**: Core business logic mismatch

2. **Multiple slots per shift type** - Legacy has `staff[w][day][s] = number_of_slots`
   - Each slot needs 2 people (except Admin = 1)
   - New solver only counts total people per shift

3. **Pair display in exports** - Shows "Person A / Person B" format

### 🟠 HIGH (Important missing features)
4. Inter-team night sharing
5. EDO allocation logic
6. Post-rebalance local search
7. Seed reproducibility

### 🟡 MEDIUM (Nice to have)
8. Dynamic staffing calculation
9. YAML presets
10. Additional Excel sheets

### 🟢 LOW (Polish)
11. Color themes
12. Team borders in matrix
13. Debug bundle

---

## Recommended Actions

### Option A: Keep Current Model (Simpler)
If pair scheduling is not strictly required:
- Document that the new system assigns individuals
- Add disclaimer that pairs are formed by people sharing same shift/day

### Option B: Implement Pair Model (Full Parity)
If pairs are required:
1. Change solver to create pair variables `pair[p1, p2, w, d, shift]`
2. Each slot consumes one pair
3. Add pair diversity constraint (minimize pair repetition)
4. Update export to show "A / B" format

> [!CAUTION]
> Option B requires significant solver redesign. The model would need to:
> - Pre-compute valid pairs
> - Add channeling constraints between pair and individual assignments
> - Potentially increase solve time significantly

---

## Summary

| Category | Implemented | Partial | Missing |
|----------|-------------|---------|---------|
| Core model | 6 | 2 | **4 (including pair model)** |
| Constraints | 9 | 1 | 2 |
| UI | 7 | 0 | 3 |
| Export | 4 | 0 | 5 |
| **TOTAL** | **26** | **3** | **14** |
