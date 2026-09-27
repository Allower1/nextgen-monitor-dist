"""Frozen promotion gates G1–G13 (evolution zone) and G14 (inner validation), plus the
falsification suite (neighbourhood, placebo, leave-out, latency, bootstrap, PBO, DSR)."""
from __future__ import annotations

import math

import numpy as np

from . import kernel as K
from . import metrics as MX
from .evaluate import Context, evaluate, spec_hash

G = K.GATES


def basic_gates(s1: dict, s2: dict) -> dict:
    """G1–G6, G11 from the 1.0x (s1) and 2.0x (s2) summaries."""
    years = [s1["years"].get(y, s1["years"].get(str(y), -1.0)) for y in (2020, 2021, 2022, 2023, 2024)]
    pos_years = sum(1 for v in years if v > 0)
    pos_blocks = sum(1 for b in s1["blocks"].values() if b["ret"] > 0)
    lo, hi = G.g2_trades_per_day
    res = {
        "G1_expectancy_2x": (s2["expectancy_bps"] > G.g1_min_expectancy_2x, s2["expectancy_bps"]),
        "G2_trades_per_day": (lo <= s1["trades_per_day_median"] <= hi and lo <= s1["trades_per_day_mean"] <= hi,
                              (s1["trades_per_day_median"], s1["trades_per_day_mean"])),
        "G3_positive_years": (pos_years >= G.g3_min_positive_years, pos_years),
        "G4_concentration": (s1["net_pnl"] > 0 and s1["top1_share"] <= G.g4_max_symbol_share
                             and s1["top3_share"] <= G.g4_max_top3_share, (s1["top1_share"], s1["top3_share"])),
        "G5_drawdown": (s1["max_dd"] <= G.g5_max_dd_1x and s2["max_dd"] <= G.g5_max_dd_2x, (s1["max_dd"], s2["max_dd"])),
        "G6_sharpe": (s1["sharpe"] >= G.g6_min_sharpe, s1["sharpe"]),
        "G11_positive_blocks": (pos_blocks >= G.g11_min_positive_blocks, pos_blocks),
    }
    return res


def placebo_signals(sig, rng):
    """Random timing + random direction with identical per-slot trade-entry count."""
    T, S = sig.shape
    out = np.zeros_like(sig)
    for s in range(S):
        n = int((sig[:, s] != 0).sum())
        if n:
            idx = rng.choice(T, size=min(n, T), replace=False)
            out[idx, s] = rng.choice(np.array([-1, 1], np.int8), size=len(idx))
    return out


def falsify(spec: dict, ctx: Context, s1: dict, n_trials: int, var_sr_daily: float, seed: int = 0,
            n_perturb: int | None = None, n_placebo: int | None = None, log_rows: list | None = None) -> dict:
    """G7, G8, G10, G12, G13 (+ bootstrap CI). Perturbation evaluations are appended to log_rows
    (they are genuine new trials and must enter the ledger)."""
    from .evolution.engine import compact, perturb
    rng = np.random.default_rng(seed)
    out = {}
    # G7 deflated Sharpe (daily units) with the full trial count
    sr_d = s1["sharpe"] / math.sqrt(365.0)
    dsr = MX.deflated_sharpe(sr_d, s1["n_days"], s1["skewness"], s1["kurtosis"], n_trials, var_sr_daily)
    out["G7_dsr"] = (dsr >= G.g7_min_dsr, dsr)
    # G8 neighbourhood
    n_perturb = n_perturb or G.g8_n_perturb
    ok, shs = 0, []
    for k in range(n_perturb):
        ps = perturb(rng, spec)
        _, sp, _ = evaluate(ps, ctx)
        shs.append(sp["sharpe"])
        ok += sp["expectancy_bps"] > 0
        if log_rows is not None:
            log_rows.append({"spec_hash": spec_hash(ps), "spec": ps, "stage": "falsify", "op": "perturb",
                             "parents": [spec_hash(spec)], "stress": 1.0, "metrics": compact(sp),
                             "sr_daily": sp["sharpe"] / math.sqrt(365.0), "status": "ok"})
    frac = ok / n_perturb
    med_ratio = float(np.median(shs) / s1["sharpe"]) if s1["sharpe"] > 0 else 0.0
    out["G8_neighbourhood"] = (frac >= G.g8_min_frac_positive and med_ratio >= G.g8_min_sharpe_ratio, (frac, med_ratio))
    # G10 placebo
    n_placebo = n_placebo or G.g10_n_placebo
    res0, _, (sig, score, sl, tp) = evaluate(spec, ctx)
    pl = []
    for k in range(n_placebo):
        psig = placebo_signals(sig, rng)
        _, sp, _ = evaluate(spec, ctx, sig_override=(psig, score, sl, tp))
        pl.append(sp["sharpe"])
    p95 = float(np.percentile(pl, G.g10_percentile))
    out["G10_placebo"] = (s1["sharpe"] > p95, (s1["sharpe"], p95))
    # G12 leave top-1 / top-3 instruments out
    top = MX.top_instruments(res0, ctx.panel.names, 3)
    lo_ok = []
    for kk in (1, 3):
        mask = np.ones(ctx.panel.N, bool)
        mask[top[:kk]] = False
        _, sp, _ = evaluate(spec, ctx, inst_mask=mask)
        lo_ok.append(sp["net_pnl"])
    out["G12_leave_out"] = (all(v > 0 for v in lo_ok), lo_ok)
    # G13 latency stress (+120 s)
    _, sl_, _ = evaluate(spec, ctx, latency_stress=True)
    out["G13_latency"] = (sl_["expectancy_bps"] > 0, sl_["expectancy_bps"])
    # informational: 3.0x cost, bootstrap CI
    _, s3, _ = evaluate(spec, ctx, cost_stress=3.0)
    out["info_3x_expectancy_bps"] = s3["expectancy_bps"]
    dr = MX.daily_returns(res0.equity)[ctx.active_days[: len(MX.daily_returns(res0.equity))]]
    out["info_bootstrap_sharpe_p5_p50"] = MX.stationary_bootstrap_sharpe(dr, 300, 10, seed)
    return out


def g14_inner(s1: dict, s15: dict) -> dict:
    lo, hi = G.g2_trades_per_day
    return {
        "G14_pnl_1.5x": (s15["net_pnl"] > 0, s15["net_pnl"]),
        "G14_sharpe": (s1["sharpe"] >= G.g14_min_sharpe, s1["sharpe"]),
        "G14_dd": (s1["max_dd"] <= G.g14_max_dd, s1["max_dd"]),
        "G14_tpd": (lo <= s1["trades_per_day_median"] <= hi, s1["trades_per_day_median"]),
        "G14_share": (s1["net_pnl"] > 0 and s1["top1_share"] <= G.g14_max_symbol_share, s1["top1_share"]),
    }


def all_pass(d: dict) -> bool:
    return all(v[0] for k, v in d.items() if k.startswith("G"))
