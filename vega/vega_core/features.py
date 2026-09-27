"""Causal 5m feature library, stored in POOL layout [T, POOL] (float32, memory-mapped).

Every feature at step t uses only 5m bars with close ≤ close of bar t (rolling windows are
trailing, ≤ 7 days; no full-period statistics). Missing bars stay NaN (no price forward-fill).
Higher-TF context uses EMAs / returns over 1h-4h spans of CLOSED bars.

Build: python -m vega_core.features --zone dev
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import numpy as np
import pandas as pd

from . import kernel as K
from .universe import Panel, panel_dir

FEATURES = ["r1", "z3", "z6", "z12", "z48", "z288", "vol48", "volr", "bbz", "rsi14", "brk48", "brk288",
            "relv", "tbr3", "emag1h", "emag4h", "fund", "rvratio_h", "zmove_h"]
MARKET = ["btc_z12", "btc_emag4h", "breadth_z12", "btc_volregime"]


def instrument_features(c: np.ndarray, hgh: np.ndarray, low: np.ndarray, qv: np.ndarray, tbq: np.ndarray) -> dict:
    s = pd.Series(c.astype(np.float64))
    lc = np.log(s)
    lr = lc.diff()
    vol12 = lr.rolling(12, min_periods=9).std()
    vol48 = lr.rolling(48, min_periods=36).std()
    vol288 = lr.rolling(288, min_periods=200).std()
    f = {}
    f["r1"] = lr
    for k, v in ((3, vol48), (6, vol48), (12, vol48), (48, vol288), (288, vol288)):
        f[f"z{k}"] = (lc - lc.shift(k)) / (v * np.sqrt(k))
    f["vol48"] = vol48
    f["volr"] = vol12 / vol288
    m48 = s.rolling(48, min_periods=36).mean()
    sd48 = s.rolling(48, min_periods=36).std()
    f["bbz"] = (s - m48) / sd48
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    f["rsi14"] = 100 - 100 / (1 + up / dn)
    H = pd.Series(hgh.astype(np.float64)); L = pd.Series(low.astype(np.float64))
    for k, v in ((48, vol48), (288, vol288)):
        hh = H.rolling(k, min_periods=int(k * 0.75)).max().shift(1)
        ll = L.rolling(k, min_periods=int(k * 0.75)).min().shift(1)
        up_b = (s / hh - 1.0) / v
        dn_b = (s / ll - 1.0) / v
        # signed breakout distance: >0 above prior high, <0 below prior low, 0 inside
        f[f"brk{k}"] = np.where(up_b > 0, up_b, np.where(dn_b < 0, dn_b, 0.0))
        f[f"brk{k}"] = pd.Series(f[f"brk{k}"]).where(hh.notna() & ll.notna() & v.notna())
    q = pd.Series(qv.astype(np.float64))
    f["relv"] = q / q.rolling(288, min_periods=200).mean()
    tb = pd.Series(tbq.astype(np.float64))
    f["tbr3"] = tb.rolling(3).sum() / q.rolling(3).sum().replace(0, np.nan) - 0.5
    e12 = s.ewm(span=12, adjust=False, min_periods=12).mean()
    e48 = s.ewm(span=48, adjust=False, min_periods=48).mean()
    e192 = s.ewm(span=192, adjust=False, min_periods=192).mean()
    f["emag1h"] = (e12 - e48) / (s * vol288 * np.sqrt(48))
    f["emag4h"] = (e48 - e192) / (s * vol288 * np.sqrt(192))
    return {k: np.asarray(v, dtype=np.float32) for k, v in f.items()}


def build(zone: str) -> dict:
    p = Panel(zone)
    T, H, N, P = p.T, p.H, p.N, p.meta["pool"]
    out = panel_dir(zone)
    pool = p.pool
    F = {k: np.lib.format.open_memmap(out / f"F_{k}.npy", mode="w+", dtype=np.float32, shape=(T, P)) for k in FEATURES}
    for k in FEATURES:
        F[k][:] = np.nan
    # which (hour, slot) holds instrument i
    t_idx = np.arange(T)
    btc = p.names.index("BTCUSDT") if "BTCUSDT" in p.names else -1
    mkt = {k: np.full(T, np.nan, np.float32) for k in MARKET}
    rvr_prev = np.vstack([np.full((1, N), np.nan, np.float32), np.asarray(p.h["rv_ratio"])[:-1]])
    zm_prev = np.vstack([np.full((1, N), np.nan, np.float32), np.asarray(p.h["zmove1h"])[:-1]])
    fund_prev = np.vstack([np.full((1, N), np.nan, np.float32), np.asarray(p.h["funding"])[:-1]])
    for i in range(N):
        a, b = p.r_off[i], p.r_off[i + 1]
        if b <= a:
            continue
        hs, sl = np.nonzero(pool == i)
        if len(hs) == 0 and i != btc:
            continue
        st = p.r_start[i]
        f = instrument_features(p.r["close"][a:b], p.r["high"][a:b], p.r["low"][a:b], p.r["qv"][a:b], p.r["tbq"][a:b])
        if i == btc:
            idx = np.arange(b - a) + st
            mkt["btc_z12"][idx] = f["z12"]
            mkt["btc_emag4h"][idx] = f["emag4h"]
            v = pd.Series(f["vol48"].astype(np.float64))
            mkt["btc_volregime"][idx] = (v / v.rolling(2016, min_periods=288).median()).to_numpy()
        for h, s_ in zip(hs, sl):
            t0, t1 = h * 12, h * 12 + 12
            k0, k1 = t0 - st, t1 - st
            if k1 <= 0 or k0 >= b - a:
                continue
            kk = np.arange(max(k0, 0), min(k1, b - a))
            tt = kk + st
            for name, arr in f.items():
                F[name][tt, s_] = arr[kk]
            F["fund"][tt, s_] = fund_prev[h, i]
            F["rvratio_h"][tt, s_] = rvr_prev[h, i]
            F["zmove_h"][tt, s_] = zm_prev[h, i]
    # breadth: mean z12 across the pool (available at bar close)
    with np.errstate(all="ignore"):
        mkt["breadth_z12"] = np.nanmean(np.asarray(F["z12"]), axis=1).astype(np.float32)
    for k, v in mkt.items():
        np.save(out / f"M_{k}.npy", v)
    for k in FEATURES:
        F[k].flush()
    meta = json.loads((out / "meta.json").read_text())
    meta["features"] = FEATURES
    meta["market"] = MARKET
    (out / "meta.json").write_text(json.dumps(meta))
    return {"T": T, "P": P, "features": len(FEATURES)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--zone", default="dev")
    a = ap.parse_args()
    t0 = time.time()
    print(build(a.zone), f"{time.time()-t0:.0f}s")
    sys.exit(0)
