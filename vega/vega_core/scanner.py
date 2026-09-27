"""MarketActivityScore, Opportunity/Crisis flag and dynamic TOP-N selection (causal).

For trading hour H the scanner only sees hourly rows ≤ H-1 (closed before H) of instruments in the
frozen pool of hour H. Cross-sectional ranks are computed among pool members of that hour only.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import kernel as K

SCORE_METRICS = ["rv_ratio", "rel_vol", "absret1h", "absret4h", "range_exp", "logqv24h", "absfunding", "abszmove"]


def _prev(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a)
    return np.vstack([np.full((1, a.shape[1]), np.nan, np.float32), a[:-1]])


class ScannerInputs:
    """Pool-layout [H, POOL] matrices of previous-hour metrics (built once per zone)."""

    def __init__(self, panel):
        pool = panel.pool
        self.pool = pool
        H, P = pool.shape
        valid = pool >= 0
        pi = np.where(valid, pool, 0)
        rows = np.arange(H)[:, None]
        g = lambda name: np.where(valid, _prev(panel.h[name])[rows, pi], np.nan).astype(np.float32)
        raw = {
            "rv_ratio": g("rv_ratio"), "rel_vol": g("rel_vol"),
            "absret1h": np.abs(g("ret1h")), "absret4h": np.abs(g("ret4h")),
            "range_exp": g("range_exp"), "logqv24h": np.log(np.maximum(g("qv24h"), 1.0)),
            "absfunding": np.abs(g("funding")), "abszmove": np.abs(g("zmove1h")),
        }
        self.raw = raw
        self.valid = valid
        self.rank = {k: self._xs_rank(v, valid) for k, v in raw.items()}

    @staticmethod
    def _xs_rank(a, valid):
        x = np.where(valid & np.isfinite(a), a, np.nan).astype(np.float64)
        r = pd.DataFrame(x).rank(axis=1, pct=True).to_numpy()
        return np.where(valid, np.nan_to_num(r, nan=0.0), -1.0).astype(np.float32)


def anomaly_flag(si: ScannerInputs, th_rv: float, th_vol: float, th_z: float) -> np.ndarray:
    r = si.raw
    with np.errstate(invalid="ignore"):
        f = (r["rv_ratio"] >= th_rv) | (r["rel_vol"] >= th_vol) | (r["abszmove"] >= th_z)
    return f & si.valid


def select_top(si: ScannerInputs, weights: dict, anomaly_boost: float, th_rv: float, th_vol: float, th_z: float,
               top_n: int = K.TOP_N):
    """Return (sel_slot [H, top_n] pool-slot idx or -1, sel_inst [H, top_n] instrument id or -1,
    flag [H, POOL])."""
    H, P = si.pool.shape
    w = np.array([max(0.0, float(weights.get(k, 0.0))) for k in SCORE_METRICS])
    if w.sum() <= 0:
        w[:] = 1.0
    w = w / w.sum()
    score = np.zeros((H, P), np.float64)
    for wk, k in zip(w, SCORE_METRICS):
        if wk:
            score += wk * si.rank[k]
    flag = anomaly_flag(si, th_rv, th_vol, th_z)
    score += anomaly_boost * flag
    score = np.where(si.valid, score, -np.inf)
    # deterministic: score desc, then instrument id asc
    inst_key = np.where(si.valid, si.pool, np.iinfo(np.int32).max).astype(np.float64)
    order = np.lexsort((inst_key, -score), axis=1)[:, :top_n]
    ok = np.take_along_axis(si.valid, order, axis=1)
    sel_slot = np.where(ok, order, -1).astype(np.int32)
    sel_inst = np.where(ok, np.take_along_axis(si.pool, order, axis=1), -1).astype(np.int32)
    return sel_slot, sel_inst, flag
