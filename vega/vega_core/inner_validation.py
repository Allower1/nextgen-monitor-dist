"""INNER VALIDATION 2025 (G14). Limited: ≤ 3 sessions × ≤ 10 frozen candidates, all logged.

Candidates must already have passed every evolution-zone gate (results/promotion_report.json).
A candidate evaluated here can never be modified; failures are retired permanently.

usage: python -m vega_core.inner_validation --session-note "..."
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time

from . import kernel as K
from .evaluate import Context, evaluate, spec_hash
from .evolution import ledger as L
from .evolution.engine import compact
from .gates import all_pass, g14_inner

LOG = K.VEGA_ROOT / "ledger" / "inner_validation.jsonl"
PROMO = K.VEGA_ROOT / "results" / "promotion_report.json"


def sessions_used() -> int:
    return len(LOG.read_text().splitlines()) if LOG.exists() else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-note", default="")
    a = ap.parse_args(argv)
    G = K.GATES
    used = sessions_used()
    if used >= G.inner_max_sessions:
        print(f"REFUSED: {used} inner-validation sessions already used (max {G.inner_max_sessions})")
        return 2
    promo = json.loads(PROMO.read_text())
    promoted = promo.get("promoted", [])
    if not promoted:
        print("No candidate passed the evolution-zone gates → nothing to validate (PROMOTE NONE).")
        return 0
    retired = set()
    if LOG.exists():
        for line in LOG.read_text().splitlines():
            retired |= set(json.loads(line)["evaluated"])
    todo = [h for h in promoted if h not in retired][: G.inner_max_candidates]
    specs = {r["spec_hash"]: r["spec"] for r in L.read() if r.get("spec_hash") in todo}
    ctx = Context("inner", mode="inner_validation")
    out = {"session": used + 1, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "note": a.session_note,
           "evaluated": todo, "results": {}}
    rows = []
    for h in todo:
        spec = specs[h]
        assert spec_hash(spec) == h
        _, s1, _ = evaluate(spec, ctx, 1.0)
        _, s15, _ = evaluate(spec, ctx, 1.5)
        g = g14_inner(s1, s15)
        out["results"][h] = {"gates": {k: [bool(v[0]), v[1]] for k, v in g.items()}, "pass": all_pass(g),
                             "metrics_1x": compact(s1), "metrics_1.5x": compact(s15)}
        rows += [{"spec_hash": h, "spec": spec, "stage": "inner", "stress": st, "metrics": compact(s),
                  "sr_daily": s["sharpe"] / math.sqrt(365), "status": "ok"} for st, s in ((1.0, s1), (1.5, s15))]
    L.append(rows)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(json.dumps({"session": out["session"], "ts": out["ts"], "evaluated": todo,
                            "passed": [h for h, r in out["results"].items() if r["pass"]]}) + "\n")
    (K.VEGA_ROOT / "results" / f"inner_validation_session_{out['session']}.json").write_text(json.dumps(out, indent=1, default=str))
    print(json.dumps({h: r["pass"] for h, r in out["results"].items()}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
