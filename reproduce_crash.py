
import logging
import time
from rota.models.person import Person
from rota.models.constraints import SolverConfig, FairnessMode
from rota.solver.optimizer import optimize

logging.basicConfig(level=logging.INFO)

# Deficit Scenario that forces unfilled slots
WEEKS = 4
people = [Person(name="Alice", workdays_per_week=3), Person(name="Bob", workdays_per_week=3)]
# Capacity = 2 * 3 * 4 = 24 shifts
# Demand = 60 shifts (Deficit 36)

# Config with STRICT targets and PARALLEL execution
config = SolverConfig(
    weeks=WEEKS,
    fairness_mode=FairnessMode.BY_WORKDAYS,
    impose_targets=True,
    parallel_portfolio=True,
    time_limit_seconds=30 # Short timeout to catch "unknown" quickly
)

custom_staffing = {"D": 3, "S": 0, "N": 0} 

if __name__ == "__main__":
    print("--- Running Reproduction Script ---")
    start = time.time()
    schedule, seed, score = optimize(people, config, tries=2, custom_staffing=custom_staffing)
    end = time.time()

    print(f"Status: {schedule.status}")
    print(f"Time: {end-start:.2f}s")
    if schedule.status == "unknown":
        print("CRASH REPRODUCED: Status is unknown.")
    else:
        print(f"Worked! Score={score}")
