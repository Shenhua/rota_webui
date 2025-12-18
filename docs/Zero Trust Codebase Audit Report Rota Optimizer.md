# 🔴 Zero Trust Codebase Audit Report: Rota Optimizer

## Executive Summary

This report documents a comprehensive "Zero Trust" audit of the **Rota Optimizer** codebase — a staff scheduling system using OR-Tools CP-SAT constraint programming. The audit analyzed 74 Python files across `src/rota`, `app`, and `tests` directories, totaling ~6,000 lines of core logic.

**Critical Findings:** 4 objective flaws requiring immediate attention
**Major Findings:** 6 issues with moderate risk
**Test Coverage Status:** Limited — missing edge cases, destructive paths, and error handling scenarios

------

## 1. Logic vs. Goal Discrepancies

### 1.1 🔴 OBJECTIVE FLAW: Rolling 48h Window Logic Bug

| Field            | Value                                                        |
| :--------------- | :----------------------------------------------------------- |
| **Goal**         | The README and code comments claim to enforce a "48h rolling window constraint" to prevent overwork (max 48h over any 7-day sliding window). |
| **Reality**      | The implementation in pairs.py:299-324 has a critical logic error. It iterates through `start_day_idx in range(5)` (Mon=0 to Fri=4) but then uses `day_idx = (start_day_idx + offset) % 7` which causes `day_idx >= 5` to be skipped as "weekend". This means windows starting from e.g., Wednesday **only capture Wed-Fri of current week + Mon-Tue of next week** (5 days), NOT a proper 7-day window. The modulo operation also incorrectly maps days. |
| **Severity**     | **Critical** — Labor law compliance at risk                  |
| **Fix Required** | Rewrite rolling window logic to properly track 7 calendar days using absolute day indices across the entire horizon, not per-week iteration with broken modulo math. |

```
# BUGGY CODE (pairs.py:309-311):

for offset in range(7):

    day_idx = (start_day_idx + offset) % 7

    if day_idx >= 5:  # Weekend (Sat=5, Sun=6)

        continue  # BUG: Skips days instead of treating as 0 hours
```

------

### 1.2 🔴 OBJECTIVE FLAW: EDO Constraint Only Applied When Fixed Day Exists

| Field            | Value                                                        |
| :--------------- | :----------------------------------------------------------- |
| **Goal**         | EDO (Earned Day Off) should prevent a person from working on their EDO week, giving them one fewer workday. |
| **Reality**      | In pairs.py:262-269, the EDO constraint `model.Add(person_works[p][w][fixed] == 0)` is **only applied when `fixed` is truthy AND in `days`**. If a person has no fixed EDO day (`edo_plan.fixed.get(p, "")` returns `""`), **no constraint is added at all**. This means EDO-eligible people without a fixed day preference can be scheduled to work every day of their EDO week. |
| **Severity**     | **Critical** — Violates EDO entitlement contract             |
| **Fix Required** | When no fixed day is specified, the solver should either: (a) add a "pick any one day off" constraint, or (b) let the solver choose one day to mark as EDO. |

------

### 1.3 🔴 OBJECTIVE FLAW: `is_contractor` Missing in `Person.from_dict()`

| Field            | Value                                                        |
| :--------------- | :----------------------------------------------------------- |
| **Goal**         | Loading team data from CSV/dict should preserve all person attributes, including contractor status. |
| **Reality**      | person.py:77-92 — `from_dict()` does NOT read the `is_contractor` field. Any contractor loaded from saved data will default to `False`, silently breaking the "forbid contractor pairs" constraint. |
| **Severity**     | **Major** — Silent data corruption on save/load cycle        |
| **Fix Required** | Add `is_contractor=bool(d.get("is_contractor", False))` to `Person.from_dict()`. |

------

### 1.4 🟡 SUBJECTIVE IMPROVEMENT: Validation 48h Rolling Window Differs from Solver

| Field            | Value                                                        |
| :--------------- | :----------------------------------------------------------- |
| **Goal**         | Validation should catch what the solver missed.              |
| **Reality**      | validation.py:411-499 — `check_rolling_48h()` uses a **different** algorithm than the solver constraint. The validation correctly builds a flat timeline with weekends as 0h (lines 448-479), then slides a 7-day window. **This means the validation may catch violations that the solver allowed**, or vice versa. |
| **Severity**     | **Minor** — Inconsistency between solver and validator       |
| **Fix Required** | Align algorithms. Ideally, extract shared logic into a common utility. |

------

### 1.5 🟡 SUBJECTIVE IMPROVEMENT: Scoring Ignores 48h Violations

| Field            | Value                                                        |
| :--------------- | :----------------------------------------------------------- |
| **Goal**         | Schedule score should penalize 48h rolling window violations. |
| **Reality**      | validation.py:400 — The `score_solution()` function explicitly **multiplies by 0**: `0 * validation.rolling_48h_violations`. This means 48h violations have zero impact on the score. |
| **Severity**     | **Minor** — Misleading score metric                          |
| **Fix Required** | Either add a non-zero weight or remove the dead term.        |

------

## 2. "Mental Sandbox" Findings

### 2.1 Workflow: Multi-Seed Parallel Optimization (`optimizer.py:optimize`)

| Scenario                                  | Current Behavior                                             | Expected Behavior                                            |
| :---------------------------------------- | :----------------------------------------------------------- | :----------------------------------------------------------- |
| **Happy Path**                            | ✅ Runs N parallel solvers, collects results, picks best score. Works correctly. | N/A                                                          |
| **All Solvers Crash** (e.g., OOM, killed) | Returns empty `PairSchedule` with `status="infeasible"` and `score=inf`. **Silent failure** — no indication that crashes occurred vs. genuinely infeasible. | Should return distinct status (e.g., `"error"`) or aggregate exception details in stats. |
| **ProcessPoolExecutor Hangs**             | `as_completed()` will block indefinitely. No timeout on futures. | Add `concurrent.futures.wait()` with timeout or use `Future.result(timeout=X)`. |
| **Exception in Child Process**            | Caught at line 133, logged, but loop continues. If ALL processes except one crash, that one's result is used (even if bad). | Accumulate errors, fail-fast if all failed, report partial failures in stats. |

------

### 2.2 Workflow: Weekend Solver (`weekend.py:WeekendSolver.solve`)

| Scenario                                                    | Current Behavior                                             | Expected Behavior                |
| :---------------------------------------------------------- | :----------------------------------------------------------- | :------------------------------- |
| **Happy Path**                                              | ✅ Builds variables, constraints, objective. Returns assignments. | N/A                              |
| **No Eligible People** (`available_weekends=False` for all) | Returns early with status `"INFEASIBLE"` and French message. ✅ Correct. | N/A                              |
| **`friday_night_workers` Key Missing Week**                 | Line 274: `if w > self.config.num_weeks: continue` — skips, but doesn't warn. Friday-to-Saturday constraint silently ignored for that week. | Log warning or raise ValueError. |
| **Person Has `id=0` Collision**                             | Uses `p.name` as key (line 128) which is correct. ✅ Code comment explicitly documents this issue and workaround. | N/A                              |

------

### 2.3 Workflow: CSV Loading (`csv_loader.py:load_team`)

| Scenario                                         | Current Behavior                                             | Expected Behavior                                            |
| :----------------------------------------------- | :----------------------------------------------------------- | :----------------------------------------------------------- |
| **Missing `name` Column**                        | Raises `ValueError` with clear message. ✅ Correct.           | N/A                                                          |
| **Empty Name Values**                            | Skips row silently (line 53-54).                             | May want to log skipped rows.                                |
| **Invalid `workdays_per_week` (e.g., `"five"`)** | `_safe_int` returns default `5`. **Silent fallback** — user doesn't know their input was ignored. | Should log warning or return validation errors.              |
| **Duplicate Names**                              | No deduplication. Same name appears twice → two distinct `Person` objects with same name. Solver will treat them as separate, causing double assignments. | Should warn or error on duplicate names.                     |
| **CSV Injection (`=CMD                           | ...`)**                                                      | Pandas reads as string. **No sanitization.** If exported to Excel, could trigger formula execution. |

------

## 3. The "Matrix of Pain" (Test Plan)

### 3.1 Critical Test Gaps Identified

Existing tests (`tests/test_pairs.py`, `test_validation.py`) cover:

- Basic solver returns schedule
- Slots filled / pairs have two people
- Night rest constraint
- Max nights constraint
- EDO day not worked (only for fixed day)

**Missing Test Categories:**

| Component                      | Scenario                          | Input Data                                                 | Expected Outcome                                             | Type              |
| :----------------------------- | :-------------------------------- | :--------------------------------------------------------- | :----------------------------------------------------------- | :---------------- |
| `csv_loader`                   | Duplicate person names            | CSV with two "Alice" rows                                  | Error or warning raised                                      | Unit              |
| `csv_loader`                   | Invalid `workdays_per_week` value | `{"name": "X", "workdays_per_week": "five"}`               | Default applied + warning logged                             | Unit              |
| `csv_loader`                   | CSV injection strings             | `{"name": "=CMD                                            | ..."}`                                                       | Sanitized on load |
| `Person.from_dict`             | Contractor field missing          | Dict without `is_contractor`                               | Defaults to `False` (currently broken)                       | Unit              |
| `pairs.solve_pairs`            | EDO eligible but no fixed day     | Person with `edo_eligible=True, edo_fixed_day=None`        | Gets one fewer workday somehow                               | Integration       |
| `pairs.solve_pairs`            | 48h rolling window across weeks   | 4×12h nights Wed-Sat (48h in 4 days)                       | Should be allowed; Mon+Tue+Wed+Thu+Fri = 48h should be allowed | Integration       |
| `pairs.solve_pairs`            | All contractors team              | 5 people, all `is_contractor=True`                         | Infeasible or soft constraint violation                      | Integration       |
| `optimizer.optimize`           | All parallel workers crash        | Mock `_solve_single_try` to raise exceptions               | Returns meaningful error status, not silent "infeasible"     | Unit              |
| `optimizer.optimize`           | Timeout before any result         | `time_limit_seconds=0.001`                                 | Returns `status="unknown"` with proper error                 | Unit              |
| `WeekendSolver.solve`          | Zero weekend-eligible people      | All people have `available_weekends=False`                 | Returns `INFEASIBLE` with message                            | Unit              |
| `WeekendSolver.solve`          | Consecutive 3+ weekends           | Force scheduler to assign same person 3 weeks in a row     | Validation flags it                                          | Integration       |
| `validate_schedule`            | 48h rolling window violation      | Manual schedule with 60h in 7 days                         | `rolling_48h_violations > 0`                                 | Unit              |
| `validation.check_rolling_48h` | English day names                 | Schedule with `"Mon"`, `"Tue"` instead of `"Lun"`, `"Mar"` | Correctly calculates hours                                   | Unit              |
| `streamlit_app`                | Empty team submitted              | Click optimize with 0 people                               | Clear error message, no crash                                | E2E/Manual        |
| `streamlit_app`                | Network drop during solve         | Kill process mid-optimization                              | Spinner clears, error displayed                              | E2E/Manual        |

------

### 3.2 Existing Test Commands

```
# Run all tests

pytest tests/ -v



# Run specific test file

pytest tests/test_pairs.py -v



# Run with coverage

pytest tests/ --cov=src/rota --cov-report=html
```

------

## 4. Recommendations for Refactoring

### 4.1 Untestable Code

| Location                | Issue                                                        | Recommendation                                               |
| :---------------------- | :----------------------------------------------------------- | :----------------------------------------------------------- |
| pairs.py:106-625        | `solve_pairs` is a **519-line monolith**. It creates variables, adds 11 constraint types, builds objective, solves, and extracts solution — all in one function. **Cannot unit test individual constraints.** | Extract constraint-adding logic into separate functions: `_add_staffing_constraints()`, `_add_night_rest_constraints()`, etc. |
| optimizer.py:107-152    | `ProcessPoolExecutor` block is hard to test without integration infra. | Extract parallelization logic into a separate interchangeable strategy class (SequentialExecutor vs ParallelExecutor). |
| streamlit_app.py:92-147 | `_handle_optimization` mixes session state mutation, spinner UI, solver invocation, and post-processing. | Extract pure-logic portions into service layer.              |

------

### 4.2 Hardening Steps (Must Fix Now)

| Priority | Action                                               | File(s)                     |
| :------- | :--------------------------------------------------- | :-------------------------- |
| 🔴 **P0** | Fix rolling 48h window constraint logic              | `pairs.py:299-324`          |
| 🔴 **P0** | Add EDO constraint for non-fixed-day-eligible people | `pairs.py:262-269`          |
| 🔴 **P0** | Add `is_contractor` to `Person.from_dict()`          | `person.py:77-92`           |
| 🟠 **P1** | Add duplicate name detection in `load_team()`        | `csv_loader.py`             |
| 🟠 **P1** | Add timeout to parallel executor futures             | `optimizer.py:120-135`      |
| 🟠 **P1** | Give 48h violations non-zero weight in scoring       | `validation.py:400`         |
| 🟡 **P2** | Log warnings for invalid CSV field values            | `csv_loader.py:63-72`       |
| 🟡 **P2** | Add CSV injection sanitization                       | `csv_loader.py`             |
| 🟡 **P2** | Align validation 48h algorithm with solver           | `validation.py`, `pairs.py` |

------

## 5. Calibration & Reality Check

### Findings Classification Summary

| Category                                    | Count | Examples                                                     |
| :------------------------------------------ | :---- | :----------------------------------------------------------- |
| 🔴 **OBJECTIVE FLAW** (Must Fix)             | 3     | Rolling 48h bug, EDO not enforced, `is_contractor` missing   |
| 🟡 **SUBJECTIVE IMPROVEMENT** (Nice to Have) | 7     | Logging enhancements, code refactoring, algorithm alignment  |
| ⚪ **False Positives Avoided**               | 3     | Initially suspected issues that turned out to be design choices |

### What I Did NOT Flag

1. **The Person id=0 issue in WeekendSolver** — Explicitly documented in code comment (line 121-122), and workaround using `p.name` as key is correct.
2. **French day names** — Legitimate domain choice, validation code supports both French and English (line 453-456).
3. **No type hints in some functions** — Stylistic preference, not a bug.
4. **Large file sizes** — While `pairs.py` is 626 lines, this is acceptable for a complex CP-SAT model. Refactoring is a P2 improvement, not a flaw.

------

## Appendix: Files Reviewed

| File                                 | Lines | Status             |
| :----------------------------------- | :---- | :----------------- |
| `src/rota/solver/pairs.py`           | 626   | ⚠️ Issues found     |
| `src/rota/solver/optimizer.py`       | 328   | ⚠️ Issues found     |
| `src/rota/solver/validation.py`      | 500   | ⚠️ Issues found     |
| `src/rota/solver/weekend.py`         | 317   | ✅ OK               |
| `src/rota/solver/edo.py`             | 201   | ✅ OK               |
| `src/rota/solver/staffing.py`        | 173   | ✅ OK               |
| `src/rota/models/person.py`          | 93    | ⚠️ Issue found      |
| `src/rota/models/constraints.py`     | 118   | ✅ OK               |
| `src/rota/models/rules.py`           | 60    | ✅ OK               |
| `src/rota/io/csv_loader.py`          | 115   | ⚠️ Issues found     |
| `src/rota/engine/targets_overlay.py` | 183   | ✅ OK               |
| `app/streamlit_app.py`               | 369   | ✅ OK               |
| `tests/test_pairs.py`                | 235   | ⚠️ Limited coverage |
| `tests/test_validation.py`           | 159   | ⚠️ Limited coverage |