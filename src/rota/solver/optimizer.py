"""
Multi-Seed Optimizer
====================
Runs multiple solver attempts with different seeds and keeps the best.
"""
import random
import time
from typing import List, Dict, Optional, Tuple
import concurrent.futures
import os

from rota.models.person import Person
from rota.models.constraints import SolverConfig
from rota.solver.pairs import solve_pairs, PairSchedule
from rota.solver.staffing import derive_staffing, WeekStaffing
from rota.solver.edo import build_edo_plan, EDOPlan
from rota.solver.validation import validate_schedule, calculate_fairness, score_solution
from rota.utils.logging_setup import get_logger, SolverLogger

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
        
        slog.step(f"Parallel Execution: {num_concurrent_solvers} solers x {workers_per_solve_calc} threads (Total Cores: {total_cores})")
        
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
            completed_count = 0
            for future in concurrent.futures.as_completed(futures):
                completed_count += 1
                cur_seed = futures[future]
                try:
                    schedule, score = future.result()
                    slog.step(f"▸ Try {completed_count}/{tries} (seed={cur_seed}) finished. Score: {score:.2f}")
                    
                    if score < best_score:
                        slog.step(f"New best: seed={cur_seed}, score={score:.2f}")
                        best_score = score
                        best_schedule = schedule
                        best_seed = cur_seed
                        
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
