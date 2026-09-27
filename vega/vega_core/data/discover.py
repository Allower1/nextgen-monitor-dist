"""Historical symbol discovery from the data.binance.vision archive (includes delisted contracts).

Holdout blindness: every archive key dated after kernel.ARCHIVE_MAX_MONTH is discarded inside
``_list`` before anything is stored, returned or printed.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import kernel as K

S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
BASE_URL = "https://data.binance.vision/"
ROOT = K.VEGA_ROOT
OUT = ROOT / "data" / "meta" / "archive_listing.json"

_KEY_RE = re.compile(r"<Key>(.*?)</Key>.*?<Size>(\d+)</Size>", re.S)
_PFX_RE = re.compile(r"<CommonPrefixes><Prefix>(.*?)</Prefix></CommonPrefixes>")
_DATE_RE = re.compile(r"-(\d{4}-\d{2})(?:-\d{2})?\.zip")


def _get(url: str, tries: int = 5) -> str:
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read().decode()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** (i + 1))
    raise RuntimeError


def _list(prefix: str, delimiter: bool = False):
    """Yield (key, size) or common prefixes. Keys after ARCHIVE_MAX_MONTH are dropped unseen."""
    marker, keys, pfx = "", [], []
    while True:
        q = {"prefix": prefix, "marker": marker}
        if delimiter:
            q["delimiter"] = "/"
        t = _get(S3 + "?" + urllib.parse.urlencode(q))
        page_keys = _KEY_RE.findall(t)
        page_pfx = _PFX_RE.findall(t)
        for k, s in page_keys:
            m = _DATE_RE.search(k)
            if m and not K.archive_month_allowed(m.group(1)):
                continue  # holdout-period key: discarded before storage
            keys.append((k, int(s)))
        pfx += page_pfx
        if "<IsTruncated>true</IsTruncated>" not in t:
            break
        nm = re.search(r"<NextMarker>(.*?)</NextMarker>", t)
        marker = nm.group(1) if nm else (page_keys[-1][0] if page_keys else page_pfx[-1])
    return pfx if delimiter else keys


def is_usdt_perp(sym: str) -> bool:
    return sym.endswith("USDT") and "_" not in sym


def discover(workers: int = 6) -> dict:
    t0 = time.time()
    monthly = [p.rstrip("/").split("/")[-1] for p in _list("data/futures/um/monthly/klines/", True)]
    daily = [p.rstrip("/").split("/")[-1] for p in _list("data/futures/um/daily/klines/", True)]
    syms = sorted({s for s in monthly + daily if is_usdt_perp(s)})

    def one(sym):
        kl = [(k, s) for k, s in _list(f"data/futures/um/monthly/klines/{sym}/1m/") if k.endswith(".zip")]
        fr = [(k, s) for k, s in _list(f"data/futures/um/monthly/fundingRate/{sym}/") if k.endswith(".zip")]
        dkl = []
        if not kl:  # symbol without monthly files (short-lived) → daily files
            dkl = [(k, s) for k, s in _list(f"data/futures/um/daily/klines/{sym}/1m/") if k.endswith(".zip")]
        return sym, {"klines_1m_monthly": kl, "funding_monthly": fr, "klines_1m_daily": dkl}

    out = {}
    with ThreadPoolExecutor(workers) as ex:
        for sym, d in ex.map(one, syms):
            if d["klines_1m_monthly"] or d["klines_1m_daily"]:
                out[sym] = d
    res = {"created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "archive_max_month": K.ARCHIVE_MAX_MONTH, "source": S3, "n_symbols": len(out),
           "symbols": out, "elapsed_s": round(time.time() - t0, 1)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res))
    return res


def month_of(key: str) -> str:
    return _DATE_RE.search(key).group(1)


def summarize(res: dict) -> dict:
    tot = {"2020-2024": 0, "2025": 0}
    n_files = {"2020-2024": 0, "2025": 0}
    first = {}
    for sym, d in res["symbols"].items():
        for k, s in d["klines_1m_monthly"] + d["klines_1m_daily"]:
            m = month_of(k)
            if m < "2020-01":
                continue
            z = "2025" if m >= "2025-01" else "2020-2024"
            tot[z] += s
            n_files[z] += 1
            first[sym] = min(first.get(sym, m), m)
    per_year = {}
    for m in first.values():
        per_year[m[:4]] = per_year.get(m[:4], 0) + 1
    return {"bytes": tot, "files": n_files, "first_month_per_year": dict(sorted(per_year.items()))}


if __name__ == "__main__":
    r = discover()
    print(json.dumps({"n_symbols": r["n_symbols"], "elapsed_s": r["elapsed_s"], **summarize(r)}, indent=1))
    sys.exit(0)
