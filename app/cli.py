import argparse

from rota.engine.solve_legacy import solve


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pattern-csv", required=True)
    p.add_argument("--weeks", type=int, default=4)
    args = p.parse_args()
    res = solve(args.pattern_csv, None)
    print("summary:", getattr(res, "summary", {}))

if __name__ == "__main__":
    main()