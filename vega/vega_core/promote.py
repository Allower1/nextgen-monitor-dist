"""Promotion stage: candidates that passed screening (1.0x + 1.5x) → basic gates (G1–G6, G11 with a
2.0x run) → PBO over the tournament pool (G9) → falsification suite (G7, G8, G10, G12, G13).
All evaluations are appended to the trial ledger. Output: results/promotion_report.json

usage: python -m vega_core.promote [--max 20]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time

import numpy as np

from . import kernel as K
from . import metrics as MX
from .evaluate import Context, evaluate, spec_hash
from .evolution import ledger as L
from .evolution.engine import compact
from .gates import all_pass, basic_gates, falsify

REPORT = K.VEGA_ROOT / "results" / "promotion_report.json"


def tournament_pool(rows, k=64):
    """Top-k distinct screened candidates by fitness (for PBO/CSCV)."""
    best = {}
    for r in rows:
        if r.get("stage") == "screen" and r.get("status") == "ok":
            h = r["spec_hash"]
            if h not in best or r["fitness"] > best[h]["fitness"]:
                best[h] = r
    return sorted(best.values(), key=lambda r: -r["fitness"])[:k]


def block_matrix(pool_rows):
    blocks = sorted({int(b) for r in pool_rows for b in r["metrics"]["blocks"]})
    M = np.array([[r["metrics"]["blocks"].get(str(b), r["metrics"]["blocks"].get(b, {"sharpe": 0.0}))["sharpe"]
                   for r in pool_rows] for b in blocks])
    return M


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=20)
    a = ap.parse_args(argv)
    rows = L.read()
    screened = {r["spec_hash"]: r for r in rows if r.get("stage") == "stress" and r.get("status") == "ok"
                and r["metrics"]["expectancy_bps"] > 0}
    screen_rows = {r["spec_hash"]: r for r in rows if r.get("stage") == "screen" and r.get("status") == "ok"}
    cands = sorted((screen_rows[h] for h in screened if h in screen_rows), key=lambda r: -r["fitness"])[: a.max]
    done = {r["spec_hash"] for r in rows if r.get("stage") == "gate"}
    ctx = Context("dev")
    pool_rows = tournament_pool(rows)
    pbo = MX.pbo_cscv(block_matrix(pool_rows)) if len(pool_rows) >= 2 else 1.0
    sr_all = np.array([r["sr_daily"] for r in rows if r.get("sr_daily") is not None])
    var_sr = float(np.var(sr_all)) if len(sr_all) > 1 else 0.0
    report = {"created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "pbo": pbo,
              "pool_size": len(pool_rows), "var_sr_daily": var_sr, "candidates": []}
    for r in cands:
        spec = r["spec"]
        h = r["spec_hash"]
        _, s1, _ = evaluate(spec, ctx, 1.0)
        _, s2, _ = evaluate(spec, ctx, 2.0)
        new_rows = [{"spec_hash": h, "spec": spec, "stage": "gate", "stress": st, "metrics": compact(s),
                     "sr_daily": s["sharpe"] / math.sqrt(365), "status": "ok"} for st, s in ((1.0, s1), (2.0, s2))]
        g = basic_gates(s1, s2)
        g["G9_pbo"] = (pbo <= K.GATES.g9_max_pbo, pbo)
        entry = {"spec_hash": h, "family": spec["family"], "fitness": r["fitness"],
                 "gates": {k: [bool(v[0]), v[1]] for k, v in g.items()}}
        if all_pass(g):
            ntr = L.n_trials() + len(new_rows)
            fz = falsify(spec, ctx, s1, ntr, var_sr, seed=int(h[:8], 16), log_rows=new_rows)
            entry["falsify"] = {k: ([bool(v[0]), v[1]] if isinstance(v, tuple) and len(v) == 2 and isinstance(v[0], (bool, np.bool_)) else v)
                                for k, v in fz.items()}
            g.update({k: v for k, v in fz.items() if k.startswith("G")})
        entry["pass_all"] = bool(all_pass(g) and "falsify" in entry)
        L.append(new_rows)
        report["candidates"].append(entry)
        print(h, spec["family"], "PASS" if entry["pass_all"] else "fail",
              {k: v[0] for k, v in entry["gates"].items()}, flush=True)
    report["n_trials_total"] = L.n_trials()
    report["promoted"] = [c["spec_hash"] for c in report["candidates"] if c["pass_all"]]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps({"pbo": pbo, "n_candidates": len(cands), "promoted": report["promoted"],
                      "n_trials": report["n_trials_total"]}))


if __name__ == "__main__":
    sys.exit(main())
