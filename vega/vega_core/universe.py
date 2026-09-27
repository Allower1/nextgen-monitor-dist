"""Dynamic universe: global time grid, hourly metric panels, eligibility, frozen candidate POOL,
ragged 5m execution arrays and funding events.

Everything here is causal:
* hourly row h describes hour [h, h+1) and is usable only at its close (h+1);
* eligibility / pool for hour H uses hourly row H-1 and earlier;
* rolling statistics are trailing windows (≤ 7 days = 168 h), never full-period.

Build: python -m vega_core.universe --zone dev
Output: data/derived/<zone>/panel/*.npy + meta.json (memory-mappable).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from . import kernel as K
from .data.download import DATA

POOL_LIQ = 40
POOL_ANOM = 10
POOL = POOL_LIQ + POOL_ANOM
W7D = 168  # hours

ZONE_SPAN = {
    "dev": (K.DEV_START, K.EVOLUTION_END, "evolution"),
    "inner": (K.INNER_WARMUP_START, K.INNER_END, "inner_validation"),
}

HOURLY_METRICS = ["close", "qv1h", "qv24h", "cov24h", "n1m", "rv1h", "ret1h", "ret4h", "ret24h",
                  "range1h", "tbr1h", "rel_vol", "rv_ratio", "range_exp", "zmove1h", "funding",
                  "beta7d", "age_h"]


def panel_dir(zone: str) -> Path:
    return DATA / "derived" / zone / "panel"


def _roll_med(a: np.ndarray, w: int = W7D, minp: int = 24) -> np.ndarray:
    return pd.DataFrame(a).rolling(w, min_periods=minp).median().to_numpy()


def load_funding(symbol: str, guard: K.ZoneGuard) -> pd.DataFrame:
    d = DATA / "funding" / symbol
    parts = []
    for f in sorted(d.glob("*.parquet")) if d.is_dir() else []:
        try:
            guard.check_month(f.stem)
        except K.LeakageError:
            continue  # funding months beyond the zone are simply not read
        parts.append(pq.read_table(f).to_pandas())
    if not parts:
        return pd.DataFrame(columns=["calc_time", "interval_h", "rate"])
    df = pd.concat(parts).drop_duplicates("calc_time").sort_values("calc_time")
    return df


def build(zone: str) -> dict:
    t_start, t_end, mode = ZONE_SPAN[zone]
    guard = K.ZoneGuard(mode)
    guard.check(t_end)
    src_zones = ["dev"] if zone == "dev" else ["dev", "inner"]
    insts = []
    for z in src_zones:
        insts += json.loads((DATA / "derived" / z / "instruments.json").read_text())["instruments"]
    # inner zone: instruments continuing from dev are concatenated by name (same symbol+segment
    # continuity is re-checked by the derive step of the inner zone; v1 keeps dev and inner
    # instruments separate and uses dev rows only as warm-up).
    names = sorted({r["inst"] for r in insts})
    N = len(names)
    H = (t_end - t_start) // K.HOUR_MS
    T = (t_end - t_start) // (5 * K.MIN_MS)
    out = panel_dir(zone)
    out.mkdir(parents=True, exist_ok=True)
    hp = {m: np.full((H, N), np.nan, np.float32) for m in HOURLY_METRICS}
    first_bar = np.full(N, np.iinfo(np.int64).max, np.int64)
    last_bar = np.zeros(N, np.int64)
    # ragged 5m arrays
    rag_cols = ["open", "high", "low", "close", "exec_open", "exec_open3", "h_after", "l_after", "rv60", "qv24h", "n1m", "qv", "tbq"]
    rag = {c: [] for c in rag_cols}
    r_off = np.zeros(N + 1, np.int64)
    r_start = np.zeros(N, np.int64)
    fund_t, fund_r, f_off = [], [], np.zeros(N + 1, np.int64)
    btc_idx = names.index("BTCUSDT") if "BTCUSDT" in names else -1
    for i, name in enumerate(names):
        bars, hrs = [], []
        for z in src_zones:
            fb = DATA / "derived" / z / "bars5m" / f"{name}.parquet"
            fh = DATA / "derived" / z / "hourly" / f"{name}.parquet"
            if fb.exists():
                bars.append(pq.read_table(fb).to_pandas())
                hrs.append(pq.read_table(fh).to_pandas())
        b = pd.concat(bars).drop_duplicates("open_time").sort_values("open_time")
        hr = pd.concat(hrs).drop_duplicates("hour").sort_values("hour")
        b = b[(b.open_time >= t_start) & (b.open_time < t_end)]
        hr = hr[(hr.hour >= t_start) & (hr.hour < t_end)]
        meta = [r for r in insts if r["inst"] == name]
        first_bar[i] = min(r["first_bar"] for r in meta)
        last_bar[i] = max(r["last_bar"] for r in meta)
        # ---- ragged 5m (dense over [first, last] inside the zone)
        if len(b):
            s = (int(b.open_time.iloc[0]) - t_start) // (5 * K.MIN_MS)
            e = (int(b.open_time.iloc[-1]) - t_start) // (5 * K.MIN_MS) + 1
            idx = ((b.open_time.to_numpy() - t_start) // (5 * K.MIN_MS) - s).astype(np.int64)
            for c in rag_cols:
                a = np.full(e - s, np.nan if c != "n1m" else 0, np.float32)
                a[idx] = b[c].to_numpy().astype(np.float32)
                rag[c].append(a)
            r_start[i] = s
            r_off[i + 1] = r_off[i] + (e - s)
        else:
            r_off[i + 1] = r_off[i]
        # ---- hourly panel
        if len(hr):
            hi = ((hr.hour.to_numpy() - t_start) // K.HOUR_MS).astype(np.int64)
            c = hr.close.to_numpy().astype(np.float64)
            dense_c = np.full(H, np.nan); dense_c[hi] = c
            def put(m, v):
                hp[m][hi, i] = v
            put("close", c)
            put("qv1h", hr.qv1h.to_numpy())
            put("qv24h", hr.qv24h.to_numpy())
            put("cov24h", hr.cov24h.to_numpy())
            put("n1m", hr.n1m.to_numpy())
            put("rv1h", hr.rv1h.to_numpy())
            put("range1h", ((hr.high - hr.low) / hr.close).to_numpy())
            put("tbr1h", (hr.tbq1h / hr.qv1h.replace(0, np.nan)).to_numpy())
            with np.errstate(all="ignore"):
                lc = np.log(dense_c)
                for m, k in (("ret1h", 1), ("ret4h", 4), ("ret24h", 24)):
                    r = np.full(H, np.nan); r[k:] = lc[k:] - lc[:-k]
                    hp[m][:, i] = r
            hp["age_h"][:, i] = (t_start + np.arange(H) * K.HOUR_MS + K.HOUR_MS - first_bar[i]) / K.HOUR_MS
        # ---- funding events (only for the instrument's lifetime)
        f = load_funding(name.split("#")[0], guard)
        f = f[(f.calc_time >= max(first_bar[i], t_start)) & (f.calc_time <= min(last_bar[i] + K.MIN_MS, t_end))]
        ft, fr = fill_missing_funding(f)
        fund_t.append(ft)
        fund_r.append(fr)
        f_off[i + 1] = f_off[i] + len(ft)
        # funding panel (last settled rate known at hour close)
        if len(f):
            fh = np.full(H, np.nan)
            fi = ((f.calc_time.to_numpy() - t_start) // K.HOUR_MS).astype(np.int64)
            ok = (fi >= 0) & (fi < H)
            fh[fi[ok]] = f.rate.to_numpy()[ok]
            hp["funding"][:, i] = pd.Series(fh).ffill(limit=24).to_numpy()
    # ---- relative (trailing 7d) metrics
    with np.errstate(all="ignore"):
        hp["rel_vol"] = (hp["qv1h"] / _roll_med(hp["qv1h"])).astype(np.float32)
        hp["rv_ratio"] = (hp["rv1h"] / _roll_med(hp["rv1h"])).astype(np.float32)
        hp["range_exp"] = (hp["range1h"] / _roll_med(hp["range1h"])).astype(np.float32)
        hp["zmove1h"] = (hp["ret1h"] / (hp["rv1h"] * np.sqrt(60.0))).astype(np.float32)
        if btc_idx >= 0:
            hp["beta7d"] = rolling_beta(hp["ret1h"], btc_idx)
    # ---- eligibility for hour H (uses row H-1) and delisting rule
    hour_start = t_start + np.arange(H, dtype=np.int64) * K.HOUR_MS
    prev = lambda a: np.vstack([np.full((1, N), np.nan, np.float32), a[:-1]])
    boundary_last = t_end - K.MIN_MS
    known_delist = np.where(last_bar >= boundary_last - K.HOUR_MS, np.iinfo(np.int64).max // 2, last_bar + K.MIN_MS)
    with np.errstate(invalid="ignore"):
        elig = ((hour_start[:, None] - first_bar[None, :] >= K.MIN_HISTORY_MS)
                & (prev(hp["cov24h"]) >= K.MIN_COVERAGE_24H)
                & (prev(hp["n1m"]) == 60)
                & (prev(hp["qv24h"]) >= K.PREFILTER_MIN_QV24H)
                & (hour_start[:, None] < known_delist[None, :] - K.DELIST_NO_ENTRY_MS))
    if zone == "dev":
        elig &= (hour_start[:, None] < K.EVOLUTION_TRADE_END)
    else:
        elig &= (hour_start[:, None] >= K.INNER_START) & (hour_start[:, None] < K.INNER_TRADE_END)
    # ---- frozen pool: top-40 by prev qv24h + 10 anomalies (max of rv_ratio / rel_vol xs-rank)
    pq24 = np.where(elig, prev(hp["qv24h"]), -np.inf)
    anom = np.where(elig, np.fmax(_xs_rank(prev(hp["rv_ratio"]), elig), _xs_rank(prev(hp["rel_vol"]), elig)), -np.inf)
    pool = np.full((H, POOL), -1, np.int32)
    for h in range(H):
        e = np.nonzero(elig[h])[0]
        if len(e) == 0:
            continue
        o = e[np.lexsort((e, -pq24[h, e]))][:POOL_LIQ]
        rest = np.setdiff1d(e, o)
        if len(rest):
            a = rest[np.lexsort((rest, -anom[h, rest]))][:POOL_ANOM]
            o = np.concatenate([o, a])
        o = np.sort(o)
        pool[h, :len(o)] = o
    # ---- save
    for m, a in hp.items():
        np.save(out / f"h_{m}.npy", a.astype(np.float32))
    np.save(out / "elig.npy", elig)
    np.save(out / "pool.npy", pool)
    for c in rag_cols:
        np.save(out / f"r_{c}.npy", np.concatenate(rag[c]) if rag[c] else np.zeros(0, np.float32))
    np.save(out / "r_off.npy", r_off); np.save(out / "r_start.npy", r_start)
    np.save(out / "f_time.npy", np.concatenate(fund_t) if fund_t else np.zeros(0, np.int64))
    np.save(out / "f_rate.npy", np.concatenate(fund_r) if fund_r else np.zeros(0))
    np.save(out / "f_off.npy", f_off)
    np.save(out / "first_bar.npy", first_bar); np.save(out / "last_bar.npy", last_bar)
    np.save(out / "known_delist.npy", known_delist)
    meta = {"zone": zone, "t_start": t_start, "t_end": t_end, "H": int(H), "T": int(T), "N": N,
            "names": names, "pool": POOL, "hourly_metrics": HOURLY_METRICS, "rag_cols": rag_cols,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rows_ragged": int(r_off[-1]), "n_funding": int(f_off[-1])}
    (out / "meta.json").write_text(json.dumps(meta))
    return meta


def fill_missing_funding(f: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Insert synthetic events (rate = NaN → engine charges the conservative rate against the
    position) where the archive skips an expected funding settlement."""
    t = f.calc_time.to_numpy().astype(np.int64)
    r = f.rate.to_numpy().astype(np.float64)
    if len(t) < 2:
        return t, r
    iv = f.interval_h.to_numpy().astype(np.int64) * K.HOUR_MS
    ts, rs = [t[:1]], [r[:1]]
    for k in range(1, len(t)):
        step = max(iv[k - 1], iv[k]) if max(iv[k - 1], iv[k]) > 0 else 8 * K.HOUR_MS
        gap = t[k] - t[k - 1]
        if gap > 1.5 * step:
            extra = np.arange(t[k - 1] + step, t[k] - step // 2, step, dtype=np.int64)
            ts.append(extra); rs.append(np.full(len(extra), np.nan))
        ts.append(t[k:k + 1]); rs.append(r[k:k + 1])
    return np.concatenate(ts), np.concatenate(rs)


def rolling_beta(ret: np.ndarray, btc_idx: int, w: int = W7D, minp: int = 72) -> np.ndarray:
    """Trailing w-hour beta of each column to column btc_idx (pairwise-complete, causal)."""
    x = ret.astype(np.float64)
    y = np.repeat(x[:, btc_idx:btc_idx + 1], x.shape[1], axis=1)
    m = np.isfinite(x) & np.isfinite(y)
    x0, y0 = np.where(m, x, 0.0), np.where(m, y, 0.0)
    roll = lambda a: pd.DataFrame(a).rolling(w, min_periods=1).sum().to_numpy()
    n = roll(m.astype(np.float64)); sx = roll(x0); sy = roll(y0); sxy = roll(x0 * y0); syy = roll(y0 * y0)
    with np.errstate(all="ignore"):
        cov = sxy / n - sx * sy / n ** 2
        var = syy / n - (sy / n) ** 2
        beta = np.where((n >= minp) & (var > 0), cov / var, np.nan)
    return np.clip(beta, *K.BETA_CLIP).astype(np.float32)


def _xs_rank(a: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Cross-sectional rank percentile per row among masked entries (0..1)."""
    x = np.where(mask & np.isfinite(a), a, np.nan).astype(np.float64)
    r = pd.DataFrame(x).rank(axis=1, pct=True).to_numpy()
    return np.nan_to_num(r, nan=0.0)


class Panel:
    """Memory-mapped read access to a built zone panel (zone-guarded)."""

    def __init__(self, zone: str, mode: str | None = None):
        t_start, t_end, zmode = ZONE_SPAN[zone]
        K.ZoneGuard(mode or zmode).check(t_end)
        d = panel_dir(zone)
        self.dir = d
        self.meta = json.loads((d / "meta.json").read_text())
        mm = lambda n: np.load(d / f"{n}.npy", mmap_mode="r")
        self.h = {m: mm(f"h_{m}") for m in self.meta["hourly_metrics"]}
        self.elig = mm("elig"); self.pool = np.asarray(mm("pool"))
        self.r = {c: mm(f"r_{c}") for c in self.meta["rag_cols"]}
        self.r_off = np.asarray(mm("r_off")); self.r_start = np.asarray(mm("r_start"))
        self.f_time = np.asarray(mm("f_time")); self.f_rate = np.asarray(mm("f_rate")); self.f_off = np.asarray(mm("f_off"))
        self.first_bar = np.asarray(mm("first_bar")); self.last_bar = np.asarray(mm("last_bar"))
        self.known_delist = np.asarray(mm("known_delist"))
        self.names = self.meta["names"]
        self.t_start = self.meta["t_start"]; self.T = self.meta["T"]; self.H = self.meta["H"]; self.N = self.meta["N"]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--zone", default="dev")
    a = ap.parse_args()
    t0 = time.time()
    m = build(a.zone)
    print(json.dumps({k: v for k, v in m.items() if k != "names"}), f"{time.time()-t0:.0f}s")
    sys.exit(0)
