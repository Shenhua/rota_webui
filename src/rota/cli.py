from __future__ import annotations

import argparse
import json
from typing import Any, Dict

from rota.engine.solve import solve  # Uses targets_overlay wrapper


def _build_cfg(args: argparse.Namespace) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {}
    if args.weeks is not None:
        cfg["weeks"] = int(args.weeks)
    if args.allow_edo is not None:
        cfg["allow_edo"] = bool(args.allow_edo)
    if args.fairness_mode:
        cfg["fairness_mode"] = args.fairness_mode
    if args.night_fairness:
        cfg["night_fairness"] = args.night_fairness
    if args.night_fairness_mode:
        cfg["night_fairness_mode"] = args.night_fairness_mode
    if args.evening_fairness:
        cfg["evening_fairness"] = args.evening_fairness
    if args.inter_team_night_share:
        cfg["inter_team_night_share"] = args.inter_team_night_share
    if args.post_rebalance_steps is not None:
        cfg["post_rebalance_steps"] = int(args.post_rebalance_steps)
    if args.verbose:
        cfg["verbose"] = int(args.verbose)
    return cfg

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Rota CLI (façade legacy)")
    p.add_argument("--csv", required=True, help="Chemin du CSV d'équipe (pattern)")
    p.add_argument("--weeks", type=int, default=4, help="Nombre de semaines (défaut: 4)")
    p.add_argument("--allow-edo", dest="allow_edo", action="store_true", help="Activer EDO")
    p.add_argument("--no-edo", dest="allow_edo", action="store_false", help="Désactiver EDO")
    p.set_defaults(allow_edo=True)
    p.add_argument("--fairness-mode", choices=["none","by-wd"], default="by-wd")
    p.add_argument("--night-fairness", choices=["off","global","cohort"], default="cohort")
    p.add_argument("--night-fairness-mode", choices=["count","rate"], default="rate")
    p.add_argument("--evening-fairness", choices=["off","global","cohort"], default="cohort")
    p.add_argument("--inter-team-night-share", choices=["off","proportional","global"], default="proportional")
    p.add_argument("--post-rebalance-steps", type=int, default=0)
    p.add_argument("-v","--verbose", action="count", default=0)
    p.add_argument("--json", dest="json_out", action="store_true", help="Sortie JSON (summary)")
    args = p.parse_args(argv)

    cfg = _build_cfg(args)
    res = solve(args.csv, cfg)

    if args.json_out:
        print(json.dumps({"summary": res.summary}, ensure_ascii=False, indent=2))
    else:
        print("Résumé:")
        for k,v in res.summary.items():
            print(f" - {k}: {v}")
        print(f"Affectations: {len(res.assignments)} lignes")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())