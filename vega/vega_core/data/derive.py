"""Audit + instrument segmentation + deterministic derived series (5m bars, hourly metrics).

For every archive symbol (zone-guarded):
  1. load 1m parquet months, audit (duplicates, misaligned timestamps, non-positive prices,
     high<low, gaps), drop duplicates (keep first) — audit counts recorded;
  2. split into instruments (SYMBOL#k) on gaps ≥ 7 d or ≥ 1 d gaps with > 70 % price jump;
  3. per instrument, dense 1m grid (NaN = missing, never forward-filled), then
     * 5m bars (usable at close_time = open_time + 5 min): o,h,l,c,qv,n1m, exec_open (open of the
       1m bar at bar open + 60 s = fill price for a signal from the previous bar), exec_open3
       (bar open + 180 s: latency-stress fill), h_after/l_after
       (extremes of minutes 2..5 = intrabar path after an entry fill), rv60 (std of the last 60
       1m log returns at bar close), qv24h and cov24h (trailing 1440 minutes at bar close);
     * hourly metrics (usable at hour close).
Outputs: data/derived/<zone>/{bars5m,hourly}/<inst>.parquet and data/derived/<zone>/instruments.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .. import kernel as K
from .download import DATA, ZONE_MONTHS

M = K.MIN_MS


def _rolling_std_valid(x: np.ndarray, w: int, minp: int) -> np.ndarray:
    s = pd.Series(x)
    return s.rolling(w, min_periods=minp).std().to_numpy()


def load_symbol_1m(zone: str, sym: str, guard: K.ZoneGuard, months_back: list[str] | None = None) -> pd.DataFrame:
    """Load a symbol's 1m bars of `zone` (plus optional warm-up months of other zones)."""
    parts = []
    dirs = [(zone, DATA / "k1m" / zone / sym)]
    for zb, m in (months_back or []):
        dirs.append((zb, DATA / "k1m" / zb / sym / f"{m}.parquet"))
    for z, d in dirs:
        files = sorted(d.glob("*.parquet")) if d.is_dir() else ([d] if d.exists() else [])
        for f in files:
            guard.check_month(f.stem)
            parts.append(pq.read_table(f).to_pandas())
    if not parts:
        return pd.DataFrame()
    df = pd.concat(parts, ignore_index=True)
    return df


def audit_and_clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    a = {"rows_raw": int(len(df))}
    df = df.sort_values("open_time", kind="stable")
    dup = df.duplicated("open_time", keep="first")
    a["duplicates"] = int(dup.sum())
    df = df[~dup]
    mis = (df["open_time"] % M) != 0
    a["misaligned"] = int(mis.sum())
    df = df[~mis]
    bad = ~((df["low"] > 0) & (df["high"] >= df["low"]) & (df["open"] > 0) & (df["close"] > 0)
            & (df["high"] >= df[["open", "close"]].max(axis=1) * 0.999999)
            & (df["low"] <= df[["open", "close"]].min(axis=1) * 1.000001))
    a["bad_ohlc"] = int(bad.sum())
    df = df[~bad]
    # zero-trade flat bars = the archive's forward-filled prices (maintenance/halts) → missing
    flat = (df["count"] == 0) & (df["open"] == df["close"]) & (df["high"] == df["low"]) & (df["open"] == df["high"])
    a["zero_trade_flat"] = int(flat.sum())
    df = df[~flat].reset_index(drop=True)
    a["rows_clean"] = int(len(df))
    return df, a


def segment(df: pd.DataFrame) -> list[tuple[int, int]]:
    """Return [start_idx, end_idx) row ranges of continuous instruments."""
    if df.empty:
        return []
    t = df["open_time"].to_numpy()
    c = df["close"].to_numpy().astype(np.float64)
    o = df["open"].to_numpy().astype(np.float64)
    gaps = np.diff(t)
    cuts = []
    for i in np.nonzero(gaps >= K.SEGMENT_JUMP_GAP_MS)[0]:
        jump = abs(o[i + 1] / c[i] - 1.0)
        if gaps[i] >= K.SEGMENT_GAP_MS or jump > K.SEGMENT_JUMP_RATIO:
            cuts.append(i + 1)
    b = [0] + cuts + [len(t)]
    return [(b[k], b[k + 1]) for k in range(len(b) - 1)]


def dense_grid(seg: pd.DataFrame) -> dict:
    t0 = int(seg["open_time"].iloc[0])
    # align grid start to a 5-minute boundary so 5m bars are clock-aligned
    t0 -= t0 % (5 * M)
    t1 = int(seg["open_time"].iloc[-1]) + M
    t1 += (-t1) % (5 * M)
    n = (t1 - t0) // M
    idx = ((seg["open_time"].to_numpy() - t0) // M).astype(np.int64)
    g = {"t0": t0, "n": n}
    for col in ["open", "high", "low", "close", "quote_volume", "taker_buy_quote_volume"]:
        a = np.full(n, np.nan, np.float64)
        a[idx] = seg[col].to_numpy().astype(np.float64)
        g[col] = a
    cnt = np.zeros(n, np.float64)
    cnt[idx] = seg["count"].to_numpy()
    g["count"] = cnt
    valid = np.zeros(n, bool)
    valid[idx] = True
    g["valid"] = valid
    return g


def derive_instrument(g: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    n, t0 = g["n"], g["t0"]
    o, h, l, c = g["open"], g["high"], g["low"], g["close"]
    qv = np.nan_to_num(g["quote_volume"])
    tb = np.nan_to_num(g["taker_buy_quote_volume"])
    valid = g["valid"]
    lr = np.full(n, np.nan)
    lr[1:] = np.log(c[1:] / c[:-1])  # NaN if either side missing
    rv60 = _rolling_std_valid(lr, 60, 45)
    qv24 = pd.Series(qv).rolling(1440, min_periods=1).sum().to_numpy()
    cov24 = pd.Series(valid.astype(np.float64)).rolling(1440, min_periods=1).sum().to_numpy() / 1440.0
    # ---------------------------------------------------------------- 5m bars
    nb = n // 5
    O = o.reshape(nb, 5); H = h.reshape(nb, 5); L = l.reshape(nb, 5); C = c.reshape(nb, 5)
    V = valid.reshape(nb, 5)
    with np.errstate(all="ignore"):
        b = pd.DataFrame({
            "open_time": t0 + np.arange(nb, dtype=np.int64) * 5 * M,
            "open": O[:, 0],
            "high": np.nanmax(np.where(V, H, np.nan), axis=1),
            "low": np.nanmin(np.where(V, L, np.nan), axis=1),
            "close": C[:, 4],
            "qv": qv.reshape(nb, 5).sum(1),
            "tbq": tb.reshape(nb, 5).sum(1),
            "n1m": V.sum(1).astype(np.int8),
            "exec_open": O[:, 1],
            "exec_open3": O[:, 3],
            "h_after": np.nanmax(np.where(V[:, 1:], H[:, 1:], np.nan), axis=1),
            "l_after": np.nanmin(np.where(V[:, 1:], L[:, 1:], np.nan), axis=1),
            "rv60": rv60.reshape(nb, 5)[:, 4],
            "qv24h": qv24.reshape(nb, 5)[:, 4],
            "cov24h": cov24.reshape(nb, 5)[:, 4],
        })
    # ---------------------------------------------------------------- hourly (aligned to hour)
    h0 = t0 + ((-t0) % K.HOUR_MS)
    off = (h0 - t0) // M
    nh = (n - off) // 60
    if nh <= 0:
        return b, pd.DataFrame()
    sl = slice(off, off + nh * 60)
    Hh = h[sl].reshape(nh, 60); Lh = l[sl].reshape(nh, 60); Ch = c[sl].reshape(nh, 60)
    Oh = o[sl].reshape(nh, 60); Vh = valid[sl].reshape(nh, 60)
    with np.errstate(all="ignore"):
        hr = pd.DataFrame({
            "hour": h0 + np.arange(nh, dtype=np.int64) * K.HOUR_MS,
            "open": Oh[:, 0],
            "high": np.nanmax(np.where(Vh, Hh, np.nan), axis=1),
            "low": np.nanmin(np.where(Vh, Lh, np.nan), axis=1),
            "close": Ch[:, -1],
            "qv1h": qv[sl].reshape(nh, 60).sum(1),
            "tbq1h": tb[sl].reshape(nh, 60).sum(1),
            "trades1h": g["count"][sl].reshape(nh, 60).sum(1),
            "n1m": Vh.sum(1).astype(np.int16),
            "rv1h": np.nanstd(np.where(np.isfinite(lr[sl].reshape(nh, 60)), lr[sl].reshape(nh, 60), np.nan), axis=1, ddof=1),
            "qv24h": qv24[sl].reshape(nh, 60)[:, -1],
            "cov24h": cov24[sl].reshape(nh, 60)[:, -1],
        })
    return b, hr


def process_symbol(args) -> list[dict]:
    zone, sym = args
    guard = K.ZoneGuard("evolution" if zone == "dev" else "inner_validation")
    # inner zone: December 2024 is read as warm-up so trailing windows are complete on 2025-01-01
    df = load_symbol_1m(zone, sym, guard, months_back=[("dev", "2024-12")] if zone == "inner" else None)
    if df.empty:
        return []
    df, aud = audit_and_clean(df)
    out = []
    segs = segment(df)
    for k, (s, e) in enumerate(segs, 1):
        seg = df.iloc[s:e]
        if len(seg) < 60:
            continue
        inst = sym if len(segs) == 1 else f"{sym}#{k}"
        g = dense_grid(seg)
        b, hr = derive_instrument(g)
        od = DATA / "derived" / zone
        (od / "bars5m").mkdir(parents=True, exist_ok=True)
        (od / "hourly").mkdir(parents=True, exist_ok=True)
        f32 = {c: np.float32 for c in b.columns if b[c].dtype == np.float64}
        pq.write_table(pa.Table.from_pandas(b.astype(f32), preserve_index=False), od / "bars5m" / f"{inst}.parquet", compression="zstd")
        pq.write_table(pa.Table.from_pandas(hr, preserve_index=False), od / "hourly" / f"{inst}.parquet", compression="zstd")
        t = seg["open_time"].to_numpy()
        gaps = np.diff(t)
        out.append({"inst": inst, "symbol": sym, "segment": k, "n_segments": len(segs),
                    "first_bar": int(t[0]), "last_bar": int(t[-1]), "rows": int(len(seg)),
                    "missing_1m": int(g["n"] - g["valid"].sum()),
                    "coverage": float(g["valid"].sum() / g["n"]),
                    "max_gap_min": int(gaps.max() // M) if len(gaps) else 0,
                    "n_gaps_gt_5min": int((gaps > 5 * M).sum()), "audit": aud})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--zone", default="dev", choices=list(ZONE_MONTHS))
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--symbols", nargs="*")
    a = ap.parse_args(argv)
    syms = a.symbols or sorted(p.name for p in (DATA / "k1m" / a.zone).iterdir() if p.is_dir())
    t0 = time.time()
    res = []
    with ProcessPoolExecutor(a.workers) as ex:
        for i, r in enumerate(ex.map(process_symbol, [(a.zone, s) for s in syms], chunksize=1)):
            res += r
            if i % 50 == 0:
                print(f"{i}/{len(syms)} {time.time()-t0:.0f}s", flush=True)
    meta = {"zone": a.zone, "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "n_symbols": len(syms), "n_instruments": len(res), "instruments": res}
    if not a.symbols:
        (DATA / "derived" / a.zone / "instruments.json").write_text(json.dumps(meta, indent=0))
    print(f"DONE {len(res)} instruments from {len(syms)} symbols in {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
