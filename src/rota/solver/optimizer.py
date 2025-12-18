"""
Multi-Seed Optimizer
====================
Runs multiple solver attempts with different seeds and keeps the best.
"""
import concurrent.futures
import os
import random
import time
from typing import Dict, List, Optional, Tuple

from rota.models.constraints import SolverConfig
from rota.models.person import Person
from rota.solver.edo import EDOPlan, build_edo_plan
from rota.solver.pairs import PairSchedule, solve_pairs
from rota.solver.staffing import WeekStaffing, derive_staffing
from rota.solver.validation import calculate_fairness, score_solution, validate_schedule
from rota.utils.logging_setup import SolverLogger, get_logger

logger = get_logger("rota.solver.optimizer")
slog = SolverLogger("rota.solver.optimizer")


def _solve_single_try(
    seed: int,
    people: List[Person],
    config: SolverConfig,
    staffing: Dict[int, WeekStaffing],
    edo_plan: EDOPlan,
    cohort_mode: str
) -> Tuple[PairSchedule, float]:
    """Helper for parallel execution."""
    random.seed(seed)
    
    # Run solver
    schedule = solve_pairs(people, config, staffing, edo_plan)
    
    # Score result
    score = float("inf")
    if schedule.status in ["optimal", "feasible"]:
        # We need to validate to score
        validation = validate_schedule(schedule, people, edo_plan, staffing)
        fairness = calculate_fairness(schedule, people, cohort_mode)
        
        # Use standard weights (could be passed in config if needed, but defaults are fine for now)
        score = score_solution(
            validation, 
            fairness,
            w_night=config.night_fairness_weight, 
            w_eve=config.evening_fairness_weight, 
            w_dev=5.0, # default deviation weight
            w_clopen=1.0 # default clopening weight
        )
        
    return schedule, score

def optimize(
    people: List[Person],
    config: SolverConfig,
    tries: int = 1,
    seed: Optional[int] = None,
    cohort_mode: str = "by-wd",
    custom_staffing: Optional[Dict[str, int]] = None,
) -> Tuple[PairSchedule, int, float]:
    """
    Run multiple solver attempts and keep the best.
    
    Args:
        people: List of Person objects
        config: Solver configuration
        tries: Number of attempts with sequential seeds
        seed: Base seed (defaults to current time)
        cohort_mode: For fairness calculation
        custom_staffing: Optional override for staffing needs (e.g. for stress test)
        
    Returns:
        (best_schedule, best_seed, best_score)
    """
    slog.phase(f"Multi-Seed Optimization ({tries} tries)")
    
    base_seed = seed if seed is not None else int(time.time())
    
    # Pre-compute staffing and EDO (same for all tries)
    edo_plan = build_edo_plan(people, config.weeks)
    staffing = derive_staffing(people, config.weeks, edo_plan.plan, custom_staffing=custom_staffing)
    
    # Enable portfolio mode if >1 try
    # We use roughly 1 core per try, capped by available cores
    if tries > 1:
        config.parallel_portfolio = True
        total_cores = os.cpu_count() or 4
        # Launch at most 'tries' parallel processes, but also limit by CPU count
        num_concurrent_solvers = min(tries, total_cores)
        
        # Calculate how many internal threads each solver can use
        # If we have 10 cores and 2 solvers, each gets 5 threads.
        # If we have 10 cores and 10 solvers, each gets 1 thread.
        workers_per_solve_calc = max(1, total_cores // num_concurrent_solvers)
        config.workers_per_solve = workers_per_solve_calc
        
        slog.step(f"Parallel Execution: {num_concurrent_solvers} solvers x {workers_per_solve_calc} threads (Total Cores: {total_cores})")
        
        best_schedule = None
        best_score = float("inf")
        best_seed = base_seed
        
        with concurrent.futures.ProcessPoolExecutor(max_workers=num_concurrent_solvers) as executor:
            # Prepare tasks
            futures = {}
            for t in range(tries):
                cur_seed = base_seed + t
                future = executor.submit(
                    _solve_single_try, 
                    cur_seed, people, config, staffing, edo_plan, cohort_mode
                )
                futures[future] = cur_seed
                
            # Process results as they complete
            # Timeout per future = 2x the solver time limit (or 120s minimum)
            future_timeout = max(120, config.time_limit_seconds * 2)
            completed_count = 0
            for future in concurrent.futures.as_completed(futures):
                completed_count += 1
                cur_seed = futures[future]
                try:
                    schedule, score = future.result(timeout=future_timeout)
                    slog.step(f"▸ Try {completed_count}/{tries} (seed={cur_seed}) finished. Score: {score:.2f}")
                    
                    if score < best_score:
                        slog.step(f"New best: seed={cur_seed}, score={score:.2f}")
                        best_score = score
                        best_schedule = schedule
                        best_seed = cur_seed
                        
                except concurrent.futures.TimeoutError:
                    logger.error(f"Try timed out for seed {cur_seed} (>{future_timeout}s)")
                except Exception as e:
                    logger.error(f"Try failed for seed {cur_seed}: {e}")
                    
                    
        # Return best found
        if best_schedule:
             slog.phase(f"optimization complete. Best: {best_score:.2f}")
             # Update schedule with final score
             best_schedule.score = best_score
             best_schedule.stats["best_seed"] = best_seed
             best_schedule.stats["tries"] = tries
             return best_schedule, best_seed, best_score
        else:
             # Fallback if all failed (unlikely) or 0 tries
             logger.error("All parallel tries failed to find a feasible solution")
             return PairSchedule(
                 assignments=[],
                 weeks=config.weeks,
                 people_count=len(people),
                 status="infeasible",
             ), base_seed, float("inf")

    else:
        # Sequential (Single Try)
        # config.parallel_portfolio is False by default
        schedule, score = _solve_single_try(base_seed, people, config, staffing, edo_plan, cohort_mode)
        
        # Update schedule with stats
        schedule.score = score
        schedule.stats["best_seed"] = base_seed
        schedule.stats["tries"] = 1
        
        return schedule, base_seed, score


def solve_with_validation(
    people: List[Person],
    config: SolverConfig,
    cohort_mode: str = "by-wd",
) -> Tuple[PairSchedule, float]:
    """
    Convenience function: solve and return with score.
    
    Args:
        people: List of Person objects
        config: Solver configuration
        cohort_mode: For fairness calculation
        
    Returns:
        (schedule, score)
    """
    edo_plan = build_edo_plan(people, config.weeks)
    staffing = derive_staffing(people, config.weeks, edo_plan.plan)
    
    schedule = solve_pairs(people, config, staffing, edo_plan)
    
    if schedule.status not in ["optimal", "feasible"]:
        return schedule, float("inf")
    
    validation = validate_schedule(schedule, people, edo_plan, staffing)
    fairness = calculate_fairness(schedule, people, cohort_mode)
    score = score_solution(validation, fairness)
    
    schedule.score = score
    
    return schedule, score


def optimize_with_cache(
    people: List[Person],
    config: SolverConfig,
    tries: int = 1,
    seed: Optional[int] = None,
    cohort_mode: str = "by-wd",
    custom_staffing: Optional[Dict[str, int]] = None,
    weekend_config: Optional[Dict] = None,
    use_cache: bool = True,
) -> Tuple[PairSchedule, int, float, str]:
    """
    Run optimization with study caching.
    
    If a matching study exists:
        - Skips already-tried seeds
        - Compares new results with cached best
        - Returns the overall best (cached or new)
    
    Args:
        people: List of Person objects
        config: Solver configuration
        tries: Number of attempts
        seed: Base seed
        cohort_mode: For fairness calculation
        custom_staffing: Optional staffing override
        weekend_config: Optional weekend configuration
        use_cache: Whether to use study caching (default True)
        
    Returns:
        (best_schedule, best_seed, best_score, study_hash)
    """
    from rota.solver.study_manager import StudyManager, compute_study_hash
    
    manager = StudyManager()
    study_hash = compute_study_hash(config, people, custom_staffing, weekend_config)
    
    # Check if study exists
    if not manager.study_exists(study_hash):
        manager.create_study(
            study_hash, 
            config, 
            people, 
            custom_staffing=custom_staffing, 
            weekend_config=weekend_config
        )

    
    # Get previously tried seeds to avoid duplicates
    tried_seeds = set(manager.get_tried_seeds(study_hash)) if use_cache else set()
    
    # Generate new seeds, skipping already-tried ones
    base_seed = seed if seed is not None else int(time.time())
    seeds_to_try = []
    candidate_seed = base_seed
    while len(seeds_to_try) < tries:
        if candidate_seed not in tried_seeds:
            seeds_to_try.append(candidate_seed)
        candidate_seed += 1
    
    if not seeds_to_try:
        logger.info(f"All {tries} seeds already tried for study {study_hash}")
        # Return cached best
        best_trial = manager.get_best_trial(study_hash)
        if best_trial:
            logger.info(f"Returning cached best: seed={best_trial.seed}, score={best_trial.score:.2f}")
            schedule = manager.load_schedule_from_trial(best_trial)
            return schedule, best_trial.seed, best_trial.score, study_hash
    
    # Run optimization with the new seeds
    edo_plan = build_edo_plan(people, config.weeks)
    staffing = derive_staffing(people, config.weeks, edo_plan.plan, custom_staffing=custom_staffing)
    
    slog.phase(f"Cached Optimization ({len(seeds_to_try)} new tries, study={study_hash[:8]})")
    
    best_schedule = None
    best_score = float("inf")
    best_seed = base_seed
    
    # Simple sequential for now (could parallelize)
    for cur_seed in seeds_to_try:
        random.seed(cur_seed)
        schedule = solve_pairs(people, config, staffing, edo_plan)
        
        score = float("inf")
        validation_dict = {}
        fairness_dict = {}
        
        if schedule.status in ["optimal", "feasible"]:
            validation = validate_schedule(schedule, people, edo_plan, staffing)
            fairness = calculate_fairness(schedule, people, cohort_mode)
            score = score_solution(
                validation, fairness,
                w_night=config.night_fairness_weight,
                w_eve=config.evening_fairness_weight,
            )
            validation_dict = validation.as_dict()
            fairness_dict = {
                "night_std": fairness.night_std,
                "eve_std": fairness.eve_std,
                "night_std_by_cohort": fairness.night_std_by_cohort,
                "eve_std_by_cohort": fairness.eve_std_by_cohort,
            }
        
        # Save trial to cache
        if use_cache:
            manager.save_trial(study_hash, cur_seed, score, schedule, validation_dict, fairness_dict)
        
        slog.step(f"▸ Seed {cur_seed}: score={score:.2f}")
        
        if score < best_score:
            best_score = score
            best_schedule = schedule
            best_seed = cur_seed
    
    # Compare with cached best
    cached_best = manager.get_best_trial(study_hash)
    if cached_best and cached_best.score < best_score:
        slog.step(f"Cached result better: {cached_best.score:.2f} vs {best_score:.2f}")
        best_schedule = manager.load_schedule_from_trial(cached_best)
        best_score = cached_best.score
        best_seed = cached_best.seed
    
    if best_schedule:
        best_schedule.score = best_score
        best_schedule.stats["best_seed"] = best_seed
        best_schedule.stats["study_hash"] = study_hash
    
    return best_schedule, best_seed, best_score, study_hash
