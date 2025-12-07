import time, argparse, os
from rota.engine.solve import solve, SolveConfig

parser = argparse.ArgumentParser()
parser.add_argument("--csv", required=True)
parser.add_argument("--weeks", type=int, default=4)
parser.add_argument("--tries", type=int, default=5)
parser.add_argument("--seed", type=int, default=123)
parser.add_argument("--config", type=str, default=None)
args = parser.parse_args()

cfg = SolveConfig(weeks=args.weeks, tries=args.tries, seed=args.seed, config_path=args.config)
t0 = time.time()
res = solve(args.csv, cfg)
dt = time.time() - t0
print(f"Time: {dt:.3f}s | Score: {res.summary['score']} | People: {res.summary.get('people',0)} | Weeks: {res.summary.get('weeks',0)}")
