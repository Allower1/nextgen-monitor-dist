"""Evolution loop: GENERATE → TEST → FALSIFY → REJECT MOST → MUTATE → PROMOTE RARELY → REMEMBER.

Resumable: population/generation state in results/evo_state.json; every evaluation appended to the
trial ledger. Deterministic given (master seed, generation, index) and the worker count does not
change results (each candidate is evaluated independently; ordering by index).

usage: python -m vega_core.evolution.engine --run-id R1 --generations 50 --workers 3
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import os
import sys
import time
import traceback
from multiprocessing import get_context
from pathlib import Path

import numpy as np

from .. import kernel as K
from ..evaluate import Context, spec_hash
from ..strategies.families import COMMON_SPACE, FAMILIES, FAMILY_SPACE, SCANNER_SPACE
from . import ledger as L

STATE = K.VEGA_ROOT / "results" / "evo_state.json"
MEMORY = K.VEGA_ROOT / "ledger" / "memory.json"
DEFAULT_SCANNER = {"w_rv_ratio": 1.0, "w_rel_vol": 1.0, "w_absret1h": 0.0, "w_absret4h": 1.0,
                   "w_range_exp": 0.0, "w_logqv24h": 1.0, "w_absfunding": 0.0, "w_abszmove": 0.0,
                   "anomaly_boost": 0.2, "th_rv": 3.0, "th_vol": 4.0, "th_z": 4.0}

SUMMARY_KEYS = ["n_trades", "trades_per_day_mean", "trades_per_day_median", "net_pnl", "total_return",
                "expectancy_bps", "gross_expectancy_bps", "fees", "slippage", "funding", "sharpe", "sortino",
                "max_dd", "profit_factor", "win_rate", "payoff", "top1_share", "top3_share", "long_pnl",
                "short_pnl", "years", "blocks", "skewness", "kurtosis", "n_days", "reasons"]


# ---------------------------------------------------------------------------------- spec ops
def _sample(rng, spec):
    kind = spec[0]
    if kind == "choice":
        v = spec[1][rng.integers(len(spec[1]))]
        return v.item() if hasattr(v, "item") else v
    if kind == "int":
        return int(rng.integers(spec[1], spec[2] + 1))
    return float(round(rng.uniform(spec[1], spec[2]), 4))


def _mutate_val(rng, spec, v, strength=0.15):
    kind = spec[0]
    if kind == "choice":
        return _sample(rng, spec)
    lo, hi = spec[1], spec[2]
    if kind == "int":
        step = max(1, int(round((hi - lo) * strength * abs(rng.normal()))))
        return int(np.clip(v + (step if rng.random() < 0.5 else -step), lo, hi))
    return float(round(np.clip(v + rng.normal() * strength * (hi - lo), lo, hi), 4))


def random_spec(rng, family=None):
    family = family or FAMILIES[rng.integers(len(FAMILIES))]
    sc = dict(DEFAULT_SCANNER)
    if rng.random() < 0.5:
        sc = {k: _sample(rng, s) for k, s in SCANNER_SPACE.items()}
    return {"family": family,
            "params": {k: _sample(rng, s) for k, s in FAMILY_SPACE[family].items()},
            "exec": {k: _sample(rng, s) for k, s in COMMON_SPACE.items()},
            "scanner": sc}


def mutate(rng, spec, p_param=0.3, p_scanner=0.2):
    s = copy.deepcopy(spec)
    changed = False
    for grp, space in (("params", FAMILY_SPACE[s["family"]]), ("exec", COMMON_SPACE)):
        for k, sp in space.items():
            if rng.random() < p_param:
                s[grp][k] = _mutate_val(rng, sp, s[grp][k])
                changed = True
    if rng.random() < p_scanner:
        for k, sp in SCANNER_SPACE.items():
            if rng.random() < p_param:
                s["scanner"][k] = _mutate_val(rng, sp, s["scanner"][k])
                changed = True
    if not changed:
        k = list(FAMILY_SPACE[s["family"]])[rng.integers(len(FAMILY_SPACE[s["family"]]))]
        s["params"][k] = _mutate_val(rng, FAMILY_SPACE[s["family"]][k], s["params"][k])
    return s


def crossover(rng, a, b):
    """Uniform parameter crossover, same family only (shared parameter semantics)."""
    assert a["family"] == b["family"]
    c = copy.deepcopy(a)
    for grp in ("params", "exec", "scanner"):
        for k in c[grp]:
            if rng.random() < 0.5:
                c[grp][k] = copy.deepcopy(b[grp][k])
    return c


def perturb(rng, spec, lo=0.8, hi=1.2):
    """Parameter-neighbourhood perturbation (G8): numeric ×U[0.8,1.2], ints ±1 step; choices kept."""
    s = copy.deepcopy(spec)
    for grp, space in (("params", FAMILY_SPACE[s["family"]]), ("exec", COMMON_SPACE)):
        for k, sp in space.items():
            if sp[0] == "float":
                s[grp][k] = float(round(np.clip(s[grp][k] * rng.uniform(lo, hi), sp[1], sp[2]), 4))
            elif sp[0] == "int":
                s[grp][k] = int(np.clip(s[grp][k] + rng.integers(-1, 2), sp[1], sp[2]))
    for k, sp in SCANNER_SPACE.items():
        s["scanner"][k] = float(round(np.clip(s["scanner"][k] * rng.uniform(lo, hi), sp[1], sp[2]), 4))
    return s


# ---------------------------------------------------------------------------------- fitness
def soft_fitness(summ: dict) -> float:
    if summ["n_trades"] < 200:
        return -5.0 + summ["n_trades"] / 200.0
    bs = np.array([b["sharpe"] for b in summ["blocks"].values()]) if summ["blocks"] else np.zeros(1)
    f = float(np.median(bs) - 0.5 * np.std(bs))
    tpd = summ["trades_per_day_median"]
    if tpd < 10:
        f -= 0.5 * math.log(10 / max(tpd, 0.1))
    elif tpd > 40:
        f -= 0.5 * math.log(tpd / 40)
    return f


def screen_pass(summ: dict) -> bool:
    pos_blocks = sum(1 for b in summ["blocks"].values() if b["ret"] > 0)
    return (5 <= summ["trades_per_day_median"] <= 60 and pos_blocks >= 6 and summ["expectancy_bps"] > 0)


def compact(summ: dict) -> dict:
    return {k: summ[k] for k in SUMMARY_KEYS if k in summ}


# ---------------------------------------------------------------------------------- workers
_CTX = None


def _init_worker(zone):
    global _CTX
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    _CTX = Context(zone)


def _eval_job(job):
    """job: dict(spec, stage, stress). Returns ledger row (never raises)."""
    from ..evaluate import evaluate
    spec = job["spec"]
    t0 = time.time()
    row = {"spec_hash": spec_hash(spec), "spec": spec, "stage": job["stage"], "stress": job.get("stress", 1.0),
           "latency_stress": job.get("latency", False), "run_id": job["run_id"], "gen": job["gen"],
           "idx": job["idx"], "seed": job["seed"], "parents": job.get("parents", []), "op": job.get("op", "")}
    try:
        _, summ, _ = evaluate(spec, _CTX, cost_stress=row["stress"], latency_stress=row["latency_stress"])
        row["metrics"] = compact(summ)
        rd = summ["sharpe"] / math.sqrt(365.0)
        row["sr_daily"] = rd
        row["fitness"] = soft_fitness(summ)
        row["status"] = "ok"
    except Exception as e:  # failures are recorded too
        row["status"] = f"error:{type(e).__name__}:{e}"[:500]
        row["trace"] = traceback.format_exc()[-2000:]
        row["fitness"] = -10.0
    row["elapsed_s"] = round(time.time() - t0, 2)
    return row


# ---------------------------------------------------------------------------------- main loop
def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return None


def save_state(st):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, default=str))
    tmp.replace(STATE)


def run(run_id: str, generations: int, workers: int, pop_per_family: int, seed: int, zone: str = "dev",
        max_hours: float = 1e9):
    t_start = time.time()
    st = load_state()
    if st is None or st.get("run_id") != run_id:
        st = {"run_id": run_id, "seed": seed, "gen": 0, "population": {f: [] for f in FAMILIES},
              "family_best": {f: -99.0 for f in FAMILIES}, "family_stale": {f: 0 for f in FAMILIES},
              "promotion_queue": [], "seen": []}
    seen = set(st["seen"])
    ctxm = get_context("fork")
    with ctxm.Pool(workers, initializer=_init_worker, initargs=(zone,)) as pool:
        while st["gen"] < generations and (time.time() - t_start) / 3600 < max_hours:
            gen = st["gen"]
            rng = np.random.default_rng([seed, gen])
            jobs = []
            # slot budget per family: stale families shrink, min 1/3 of base
            for fam in FAMILIES:
                popn = st["population"][fam]
                n = max(pop_per_family // 3, pop_per_family - 4 * st["family_stale"][fam])
                children = []
                if not popn:
                    children = [(random_spec(rng, fam), [], "random") for _ in range(n)]
                else:
                    ranked = sorted(popn, key=lambda r: -r["fitness"])
                    elite = ranked[: max(1, len(ranked) // 10)]
                    while len(children) < n:
                        u = rng.random()
                        if u < 0.1:
                            children.append((random_spec(rng, fam), [], "immigrant"))
                            continue
                        def tourn():
                            cand = [ranked[rng.integers(len(ranked))] for _ in range(4)]
                            return max(cand, key=lambda r: r["fitness"])
                        if u < 0.3 and len(ranked) > 1:
                            a, b = tourn(), tourn()
                            children.append((mutate(rng, crossover(rng, a["spec"], b["spec"]), p_param=0.1),
                                             [a["spec_hash"], b["spec_hash"]], "crossover"))
                        else:
                            a = tourn() if rng.random() < 0.7 else elite[rng.integers(len(elite))]
                            children.append((mutate(rng, a["spec"]), [a["spec_hash"]], "mutate"))
                for spec, parents, op in children:
                    h = spec_hash(spec)
                    if h in seen:
                        continue
                    seen.add(h)
                    jobs.append({"spec": spec, "stage": "screen", "stress": 1.0, "run_id": run_id, "gen": gen,
                                 "idx": len(jobs), "seed": [seed, gen], "parents": parents, "op": op})
            rows = pool.map(_eval_job, jobs, chunksize=1)
            # stress stage for screen passes (1.5x costs)
            stress_jobs = []
            for r in rows:
                if r["status"] == "ok" and screen_pass(r["metrics"]):
                    stress_jobs.append({**{k: r[k] for k in ("spec", "run_id", "gen", "idx", "seed", "parents", "op")},
                                        "stage": "stress", "stress": 1.5})
            srows = pool.map(_eval_job, stress_jobs, chunksize=1) if stress_jobs else []
            L.append(rows + srows)
            passed15 = {r["spec_hash"] for r in srows if r["status"] == "ok" and r["metrics"]["expectancy_bps"] > 0}
            # update populations (keep best 3×pop per family, fitness-sorted)
            for r in rows:
                if r["status"] != "ok":
                    continue
                r2 = {"spec_hash": r["spec_hash"], "spec": r["spec"], "fitness": r["fitness"],
                      "screen_pass": r["spec_hash"] in passed15}
                st["population"][r["spec"]["family"]].append(r2)
                if r2["screen_pass"]:
                    st["promotion_queue"].append(r["spec_hash"])
            for fam in FAMILIES:
                popn = sorted(st["population"][fam], key=lambda r: -r["fitness"])[: 3 * pop_per_family]
                st["population"][fam] = popn
                best = popn[0]["fitness"] if popn else -99
                if best > st["family_best"][fam] + 1e-3:
                    st["family_best"][fam] = best
                    st["family_stale"][fam] = 0
                else:
                    st["family_stale"][fam] += 1
            st["gen"] = gen + 1
            st["seen"] = sorted(seen)
            save_state(st)
            MEMORY.write_text(json.dumps({"run_id": run_id, "gen": st["gen"], "family_best": st["family_best"],
                                          "family_stale": st["family_stale"],
                                          "n_promotion_queue": len(st["promotion_queue"]),
                                          "top": {f: [(r["spec_hash"], round(r["fitness"], 3)) for r in st["population"][f][:3]]
                                                  for f in FAMILIES}}, indent=1))
            ok = [r for r in rows if r["status"] == "ok"]
            errs = len(rows) - len(ok)
            bestr = max(ok, key=lambda r: r["fitness"]) if ok else None
            print(f"[gen {gen}] evals={len(rows)} stress={len(srows)} pass1.5x={len(passed15)} errors={errs} "
                  f"best={bestr['fitness']:.3f} {bestr['spec']['family']} tpd={bestr['metrics']['trades_per_day_median']:.1f} "
                  f"exp={bestr['metrics']['expectancy_bps']:.2f}bps sh={bestr['metrics']['sharpe']:.2f} "
                  f"elapsed={(time.time()-t_start)/60:.1f}m", flush=True) if bestr else print(f"[gen {gen}] no ok evals", flush=True)
    return st


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", default="R1")
    ap.add_argument("--generations", type=int, default=50)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--pop", type=int, default=16)
    ap.add_argument("--seed", type=int, default=20260927)
    ap.add_argument("--max-hours", type=float, default=1e9)
    a = ap.parse_args()
    run(a.run_id, a.generations, a.workers, a.pop, a.seed, max_hours=a.max_hours)
    sys.exit(0)
