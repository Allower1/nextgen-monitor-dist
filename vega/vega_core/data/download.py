"""Resumable archive downloader: 1m klines + funding → canonical parquet.

* verifies Binance .CHECKSUM (sha256) and records our own sha256 of the zip and of the parquet;
* zips are deleted after successful conversion (only parquet kept; git never sees either);
* resume: files already recorded as ok in the manifest (and present on disk) are skipped;
* disk guard: aborts when free disk < kernel-protocol floor (5 GB).

usage: python -m vega_core.data.download --zone dev|inner [--workers 8] [--limit N]
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import sys
import threading
import time
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from .. import kernel as K
from .discover import BASE_URL, OUT as LISTING, month_of

DATA = K.VEGA_ROOT / "data"
MANIFEST = DATA / "meta" / "download_manifest.jsonl"
DISK_FLOOR = 5.0e9
ZONE_MONTHS = {"dev": ("2020-01", "2024-12"), "inner": ("2025-01", "2025-12")}

KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
              "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"]
KLINE_SCHEMA = pa.schema([("open_time", pa.int64()), ("open", pa.float32()), ("high", pa.float32()),
                          ("low", pa.float32()), ("close", pa.float32()), ("volume", pa.float32()),
                          ("quote_volume", pa.float32()), ("count", pa.int32()),
                          ("taker_buy_quote_volume", pa.float32())])

_lock = threading.Lock()


class DiskFull(RuntimeError):
    pass


def kline_path(zone: str, sym: str, month: str) -> Path:
    return DATA / "k1m" / zone / sym / f"{month}.parquet"


def funding_path(sym: str, month: str) -> Path:
    return DATA / "funding" / sym / f"{month}.parquet"


def _fetch(url: str, tries: int = 6) -> bytes:
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                return r.read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(min(2 ** (i + 1), 30))
    raise RuntimeError


def _read_csv(raw: bytes, names: list[str]) -> pa.Table:
    first = raw[:64].split(b"\n", 1)[0]
    has_header = not first[:1].isdigit()
    opts = pacsv.ReadOptions(column_names=None if has_header else names, autogenerate_column_names=False)
    return pacsv.read_csv(io.BytesIO(raw), read_options=opts)


def parse_klines(raw: bytes) -> pa.Table:
    t = _read_csv(raw, KLINE_COLS)
    ot = t.column("open_time").to_numpy().astype(np.int64)
    if len(ot) and ot.max() > 10 ** 14:  # microseconds → ms
        ot = ot // 1000
    cols = {"open_time": ot}
    for c in ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_quote_volume"]:
        cols[c] = t.column(c).to_numpy().astype(np.float32)
    cols["count"] = t.column("count").to_numpy().astype(np.int32)
    tbl = pa.table(cols, schema=KLINE_SCHEMA)
    return tbl


def parse_funding(raw: bytes) -> pa.Table:
    t = _read_csv(raw, ["calc_time", "funding_interval_hours", "last_funding_rate"])
    ct = t.column("calc_time").to_numpy().astype(np.int64)
    if len(ct) and ct.max() > 10 ** 14:
        ct = ct // 1000
    iv = t.column("funding_interval_hours").to_numpy().astype(np.int16) if "funding_interval_hours" in t.column_names \
        else np.full(len(ct), 8, np.int16)
    return pa.table({"calc_time": ct, "interval_h": iv,
                     "rate": t.column("last_funding_rate").to_numpy().astype(np.float64)})


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def process(kind: str, zone: str, sym: str, key: str, size: int) -> dict:
    month = month_of(key)
    out = kline_path(zone, sym, month) if kind == "k1m" else funding_path(sym, month)
    if shutil.disk_usage(DATA).free < DISK_FLOOR:
        raise DiskFull("free disk below 5 GB floor")
    url = BASE_URL + key
    raw_zip = _fetch(url)
    rec = {"kind": kind, "zone": zone, "symbol": sym, "month": month, "url": url, "size": len(raw_zip),
           "listed_size": size, "sha256_zip": _sha(raw_zip)}
    try:
        cs = _fetch(url + ".CHECKSUM").decode().split()[0]
    except Exception:
        cs = None
    rec["binance_checksum"] = cs
    if cs is not None and cs != rec["sha256_zip"]:
        rec["status"] = "checksum_mismatch"
        return rec
    try:
        with zipfile.ZipFile(io.BytesIO(raw_zip)) as z:
            raw = z.read(z.namelist()[0])
        tbl = parse_klines(raw) if kind == "k1m" else parse_funding(raw)
    except Exception as e:  # corrupt file
        rec["status"] = f"corrupt:{type(e).__name__}:{e}"[:300]
        return rec
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    pq.write_table(tbl, tmp, compression="zstd", compression_level=6)
    tmp.replace(out)
    rec.update(rows=tbl.num_rows, sha256_parquet=_sha(out.read_bytes()), status="ok",
               ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    return rec


def load_manifest() -> dict:
    done = {}
    if MANIFEST.exists():
        for line in MANIFEST.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done[r["url"]] = r
    return done


def jobs_for(zone: str) -> list[tuple]:
    lo, hi = ZONE_MONTHS[zone]
    # zone guard: dev jobs must be readable in evolution mode, inner jobs in inner mode
    guard = K.ZoneGuard("evolution" if zone == "dev" else "inner_validation")
    listing = json.loads(LISTING.read_text())
    jobs = []
    for sym, d in listing["symbols"].items():
        for kind, keys in (("k1m", d["klines_1m_monthly"]), ("funding", d["funding_monthly"])):
            for k, s in keys:
                m = month_of(k)
                if lo <= m <= hi:
                    guard.check_month(m)
                    jobs.append((kind, zone, sym, k, s))
        # short-lived symbols with daily-only files are recorded but not downloaded in v1
    return jobs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--zone", required=True, choices=list(ZONE_MONTHS))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args(argv)
    done = load_manifest()
    jobs = [j for j in jobs_for(a.zone)
            if not (BASE_URL + j[3] in done and done[BASE_URL + j[3]]["status"] == "ok"
                    and (kline_path(j[1], j[2], month_of(j[3])) if j[0] == "k1m"
                         else funding_path(j[2], month_of(j[3]))).exists())]
    # funding first (tiny), then klines by month so early history completes first
    jobs.sort(key=lambda j: (j[0] != "funding", month_of(j[3]), j[2]))
    if a.limit:
        jobs = jobs[: a.limit]
    est = sum(j[4] for j in jobs)
    free = shutil.disk_usage(DATA).free
    print(f"zone={a.zone} jobs={len(jobs)} zip_bytes={est/1e9:.2f}GB est_parquet≈{0.6*est/1e9:.2f}GB free={free/1e9:.1f}GB", flush=True)
    if free - 0.7 * est < DISK_FLOOR:
        print("ABORT: estimated size would breach disk floor", flush=True)
        return 2
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    t0, nbytes, n = time.time(), 0, 0
    with ThreadPoolExecutor(a.workers) as ex, open(MANIFEST, "a") as mf:
        futs = {ex.submit(process, *j): j for j in jobs}
        for f in as_completed(futs):
            j = futs[f]
            try:
                rec = f.result()
            except DiskFull as e:
                print(f"ABORT {e}", flush=True)
                ex.shutdown(wait=False, cancel_futures=True)
                return 3
            except Exception as e:
                rec = {"kind": j[0], "zone": j[1], "symbol": j[2], "month": month_of(j[3]),
                       "url": BASE_URL + j[3], "status": f"error:{type(e).__name__}:{e}"[:300]}
            with _lock:
                mf.write(json.dumps(rec) + "\n")
                mf.flush()
            n += 1
            nbytes += rec.get("size", 0)
            if n % 200 == 0:
                el = time.time() - t0
                print(f"{n}/{len(jobs)} {nbytes/1e9:.2f}GB {nbytes/el/1e6:.1f}MB/s free={shutil.disk_usage(DATA).free/1e9:.1f}GB", flush=True)
    print(f"DONE {n} files {nbytes/1e9:.2f}GB in {time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
