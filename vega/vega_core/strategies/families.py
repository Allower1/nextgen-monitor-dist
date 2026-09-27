"""Model families as parameterised rule sets over the causal feature panels.

A candidate is a CandidateSpec dict:
  {"family": str, "params": {...}, "scanner": {...}, "exec": {...}}
``signals(spec, ctx)`` returns sig/score/sl/tp panels [T, S] for the candidate's TOP-S selection.
All thresholds act on features that are known at the close of the signal bar.
"""
from __future__ import annotations

import numpy as np

from ..scanner import SCORE_METRICS

# (kind, lo, hi) for floats/ints, ("choice", [...]) for categoricals
COMMON_SPACE = {
    "direction": ("choice", ["both", "long", "short"]),
    "regime": ("choice", ["none", "btc_trend", "btc_counter", "high_vol", "low_vol", "breadth"]),
    "sl_k": ("float", 0.5, 4.0),
    "tp_k": ("float", 0.0, 6.0),
    "max_hold": ("int", 3, 144),
    "cooldown": ("int", 0, 48),
    "exit_on_opp": ("choice", [False, True]),
    "size_frac": ("float", 0.05, 0.30),
    "entry_tf": ("choice", [5, 15, 30]),   # decisions only at closes of this timeframe (minutes)
}

SCANNER_SPACE = {**{f"w_{k}": ("float", 0.0, 1.0) for k in SCORE_METRICS},
                 "anomaly_boost": ("float", 0.0, 1.0),
                 "th_rv": ("float", 2.0, 6.0), "th_vol": ("float", 2.0, 6.0), "th_z": ("float", 2.0, 6.0)}

FAMILY_SPACE = {
    "momentum_breakout": {
        "L": ("choice", [48, 288]), "k": ("choice", [3, 6, 12, 48]),
        "b_th": ("float", 0.0, 3.0), "z_th": ("float", 0.3, 4.0),
        "v_th": ("float", 0.3, 3.0), "rv_th": ("float", 0.3, 4.0)},
    "mean_reversion": {
        "k": ("choice", [3, 6, 12, 48]), "z_th": ("float", 0.5, 5.0), "bb_th": ("float", 0.0, 3.5),
        "rsi_lo": ("float", 5.0, 45.0), "v_max": ("float", 0.5, 5.0)},
    "vol_expansion": {
        "v_th": ("float", 1.0, 5.0), "rv_th": ("float", 1.0, 6.0), "z_th": ("float", 0.5, 4.0),
        "cont": ("choice", [True, False])},
    "xs_momentum": {
        "k": ("choice", [3, 6, 12, 48, 288]), "m": ("int", 3, 48), "q": ("int", 1, 4),
        "z_th": ("float", 0.0, 3.0), "cont": ("choice", [True, False])},
    "opportunity": {
        "k": ("choice", [3, 6, 12]), "z_th": ("float", 0.5, 4.0), "align": ("choice", [True, False]),
        "cont": ("choice", [True, False])},
    "flow_imbalance": {
        "tbr_th": ("float", 0.02, 0.3), "z_th": ("float", 0.0, 3.0), "rv_th": ("float", 0.5, 4.0),
        "cont": ("choice", [True, False])},
    "ridge_wf": {
        **{f"f_{k}": ("choice", [False, True]) for k in
           ["z3", "z12", "z48", "z288", "volr", "bbz", "rsi14", "brk48", "brk288", "relv", "tbr3", "emag1h", "emag4h", "fund"]},
        "h": ("choice", [3, 6, 12, 24, 48]), "lam": ("float", 0.1, 100.0), "th": ("float", 0.5, 4.0)},
}
FAMILIES = list(FAMILY_SPACE)
RIDGE_FEATS = [k[2:] for k in FAMILY_SPACE["ridge_wf"] if k.startswith("f_")]
PURGE_STEPS = 7 * 288          # 7-day purge + embargo between training data and predicted block


def block_starts(ctx):
    """Step indices where half-year blocks start (UTC Jan 1 / Jul 1) inside the zone."""
    t0 = np.datetime64(int(ctx.panel.t_start), "ms")
    days = (np.arange(ctx.T // 288) * np.timedelta64(1, "D")) + t0.astype("datetime64[D]")
    m = days.astype("datetime64[M]").astype(int) % 12
    first = (days.astype("datetime64[D]") == days.astype("datetime64[M]").astype("datetime64[D]")) & ((m == 0) | (m == 6))
    return [0] + [int(i * 288) for i in np.nonzero(first)[0] if i > 0] + [ctx.T]


def ridge_target(ctx, h):
    """Vol-normalised forward return from the next-bar fill to close h bars later (TRAINING ONLY)."""
    P = ctx.panel
    sel_t = ctx.cur["sel_inst"][np.arange(ctx.T) // 12]
    t = np.arange(ctx.T)[:, None]
    i = np.maximum(sel_t, 0)
    def rows(tt):
        k = tt - P.r_start[i]
        ln = P.r_off[i + 1] - P.r_off[i]
        ok = (sel_t >= 0) & (k >= 0) & (k < ln)
        return np.where(ok, P.r_off[i] + np.clip(k, 0, None), 0), ok
    r1, ok1 = rows(t + 1)
    rh, okh = rows(t + h)
    ex = np.asarray(P.r["exec_open"])[r1]
    cl = np.asarray(P.r["close"])[rh]
    with np.errstate(all="ignore"):
        y = np.log(cl / ex) / (ctx.gather("vol48") * np.sqrt(h))
    y = np.where(ok1 & okh, y, np.nan)
    return np.clip(y, -10, 10)


def ridge_predict(spec, ctx):
    p = spec["params"]
    feats = [k for k in RIDGE_FEATS if p.get(f"f_{k}")] or ["z12"]
    X = np.stack([ctx.gather(k) for k in feats], -1)          # [T, S, F]
    y = ridge_target(ctx, int(p["h"]))
    pred = np.full(y.shape, np.nan, np.float32)
    thr = np.full(y.shape, np.inf, np.float32)
    bs = block_starts(ctx)
    for b in range(1, len(bs) - 1):
        s0, s1 = bs[b], bs[b + 1]
        tr_end = s0 - PURGE_STEPS - int(p["h"])               # label horizon fully before purge
        if tr_end <= 288 * 30:
            continue
        Xt = X[:tr_end:3].reshape(-1, len(feats)); yt = y[:tr_end:3].reshape(-1)
        ok = np.isfinite(Xt).all(1) & np.isfinite(yt)
        if ok.sum() < 5000:
            continue
        Xt, yt = Xt[ok].astype(np.float64), yt[ok].astype(np.float64)
        mu, sd = Xt.mean(0), Xt.std(0) + 1e-9
        Z = (Xt - mu) / sd
        w = np.linalg.solve(Z.T @ Z + p["lam"] * np.eye(len(feats)), Z.T @ (yt - yt.mean()))
        ptr = Z @ w
        Xb = (X[s0:s1].astype(np.float64) - mu) / sd
        pred[s0:s1] = (Xb @ w).astype(np.float32)
        thr[s0:s1] = p["th"] * ptr.std()
    return pred, thr


def _nz(a):
    return np.nan_to_num(a, nan=0.0)


def regime_mask(regime: str, ctx, side: int) -> np.ndarray:
    """Bool [T, 1] mask allowing entries of `side` under the regime filter."""
    m = ctx.market
    with np.errstate(invalid="ignore"):
        if regime == "none":
            return np.ones((ctx.T, 1), bool)
        if regime == "btc_trend":
            x = (m["btc_emag4h"] * side) > 0
        elif regime == "btc_counter":
            x = (m["btc_emag4h"] * side) < 0
        elif regime == "high_vol":
            x = m["btc_volregime"] > 1.0
        elif regime == "low_vol":
            x = m["btc_volregime"] <= 1.0
        elif regime == "breadth":
            x = (m["breadth_z12"] * side) > 0
        else:
            raise ValueError(regime)
    return x[:, None]


def raw_direction(spec, ctx):
    """Return (long_cond, short_cond, strength) bool/float [T, S]."""
    fam, p = spec["family"], spec["params"]
    G = ctx.gather
    with np.errstate(invalid="ignore"):
        if fam == "momentum_breakout":
            z = G(f"z{p['k']}"); b = G(f"brk{p['L']}"); v = G("volr"); rv = G("relv")
            base = (v > p["v_th"]) & (rv > p["rv_th"])
            lc = base & (b > p["b_th"]) & (z > p["z_th"])
            sc = base & (b < -p["b_th"]) & (z < -p["z_th"])
            strength = np.abs(z)
        elif fam == "mean_reversion":
            z = G(f"z{p['k']}"); bb = G("bbz"); rsi = G("rsi14"); v = G("volr")
            calm = v < p["v_max"]
            lc = calm & (z < -p["z_th"]) & (bb < -p["bb_th"]) & (rsi < p["rsi_lo"])
            sc = calm & (z > p["z_th"]) & (bb > p["bb_th"]) & (rsi > 100 - p["rsi_lo"])
            strength = np.abs(z)
        elif fam == "vol_expansion":
            z = G("z3"); v = G("volr"); rv = G("relv")
            base = (v > p["v_th"]) & (rv > p["rv_th"]) & (np.abs(z) > p["z_th"])
            d = np.sign(_nz(z)) * (1 if p["cont"] else -1)
            lc = base & (d > 0); sc = base & (d < 0)
            strength = _nz(v) * np.abs(_nz(z))
        elif fam == "xs_momentum":
            z = G(f"z{p['k']}")
            zz = np.where(np.isfinite(z), z, np.nan)
            reb = (np.arange(ctx.T) % p["m"]) == 0
            q = p["q"]
            with np.errstate(all="ignore"):
                order = np.argsort(np.where(np.isfinite(zz), -zz, np.inf), axis=1)
                ranks = np.empty_like(order); np.put_along_axis(ranks, order, np.arange(zz.shape[1])[None, :], axis=1)
                nvalid = np.isfinite(zz).sum(1, keepdims=True)
            top = (ranks < q) & (zz > p["z_th"])
            bot = (ranks >= nvalid - q) & (zz < -p["z_th"]) & np.isfinite(zz)
            if not p["cont"]:
                top, bot = bot, top
            lc = top & reb[:, None]; sc = bot & reb[:, None]
            strength = np.abs(_nz(zz))
        elif fam == "opportunity":
            flag = ctx.flag_ts                     # [T, S] anomaly flag (previous hour, causal)
            z = G(f"z{p['k']}"); z48 = G("z48")
            base = flag & (np.abs(z) > p["z_th"])
            if p["align"]:
                base &= (np.sign(_nz(z)) == np.sign(_nz(z48)))
            d = np.sign(_nz(z)) * (1 if p["cont"] else -1)
            lc = base & (d > 0); sc = base & (d < 0)
            strength = np.abs(_nz(z))
        elif fam == "ridge_wf":
            pred, thr = ridge_predict(spec, ctx)
            lc = pred > thr
            sc = pred < -thr
            strength = np.abs(_nz(pred))
        elif fam == "flow_imbalance":
            t = G("tbr3"); z = G("z3"); rv = G("relv")
            base = (np.abs(t) > p["tbr_th"]) & (rv > p["rv_th"]) & (np.sign(_nz(t)) * _nz(z) > p["z_th"])
            d = np.sign(_nz(t)) * (1 if p["cont"] else -1)
            lc = base & (d > 0); sc = base & (d < 0)
            strength = np.abs(_nz(t))
        else:
            raise ValueError(fam)
    return lc, sc, strength


def signals(spec, ctx):
    p, e = spec["params"], spec["exec"]
    lc, sc, strength = raw_direction(spec, ctx)
    if e["direction"] == "long":
        sc = np.zeros_like(sc)
    elif e["direction"] == "short":
        lc = np.zeros_like(lc)
    lc = lc & regime_mask(e["regime"], ctx, +1)
    sc = sc & regime_mask(e["regime"], ctx, -1)
    valid = ctx.valid_ts
    tf = int(e.get("entry_tf", 5)) // 5
    if tf > 1:  # a resampled 15m/30m bar is usable only at its close
        valid = valid & (((np.arange(ctx.T) + 1) % tf) == 0)[:, None]
    sig = np.where(lc & valid, 1, np.where(sc & valid, -1, 0)).astype(np.int8)
    vol = ctx.gather("vol48")
    unit = _nz(vol) * np.sqrt(max(int(e["max_hold"]), 1))
    sl = np.clip(e["sl_k"] * unit, 0.002, 0.15).astype(np.float32)
    tp = (np.clip(e["tp_k"] * unit, 0.002, 0.30) if e["tp_k"] > 0.05 else np.zeros_like(unit)).astype(np.float32)
    score = np.nan_to_num(strength, nan=0.0).astype(np.float32)
    return sig, score, sl, tp
