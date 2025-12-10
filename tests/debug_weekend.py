
from rota.solver.weekend import WeekendSolver, WeekendConfig
from rota.models.person import Person
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)

def debug_weekend():
    # 1. Mock People (16 agents)
    people = []
    for i in range(16):
        p = Person(name=f"Agent_{i}", workdays_per_week=4)
        p.id = i
        people.append(p)
        
    # 2. Config similar to app
    config = WeekendConfig(
        num_weeks=12,
        staff_per_shift=2,
        max_weekends_per_month=2,
        forbid_consecutive_nights=True,
        time_limit_seconds=10
    )
    
    # 3. Solver
    print("Initializing Solver...")
    solver = WeekendSolver(config, people)
    
    # 4. Solve
    print("Solving...")
    result = solver.solve()
    
    print(f"Status: {result.status}")
    print(f"Message: {result.message}")
    print(f"Assignments count: {len(result.assignments)}")
    
    # Check deficits
    if result.status in ["OPTIMAL", "FEASIBLE"]:
        total_shifts = len(result.assignments)
        target_shifts = 12 * 2 * 2 * 2 # 12 w, 2 d, 2 s, 2 p
        print(f"Total shifts: {total_shifts} / {target_shifts}")
        
    # Print variables info if infeasible? 
    # (Can't easily do that without modifying solver, but status is key)

if __name__ == "__main__":
    debug_weekend()
