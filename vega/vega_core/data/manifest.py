"""Build DATA_MANIFEST.json + DATA_MANIFEST.md from the download manifest and derive metadata."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from collections import Counter

from .. import kernel as K
from .download import DATA, MANIFEST

ROOT = K.VEGA_ROOT


def _d(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


def build(zone: str = "dev") -> dict:
    rows = [json.loads(l) for l in MANIFEST.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if r.get("zone") == zone]
    last = {}
    for r in rows:
        last[r["url"]] = r   # latest record per file wins (resume re-downloads)
    rows = list(last.values())
    st = Counter(r["status"].split(":")[0] for r in rows)
    inst = json.loads((DATA / "derived" / zone / "instruments.json").read_text())
    listing = json.loads((DATA / "meta" / "archive_listing.json").read_text())
    k = [r for r in rows if r["kind"] == "k1m" and r["status"] == "ok"]
    f = [r for r in rows if r["kind"] == "funding" and r["status"] == "ok"]
    files_hash = hashlib.sha256("".join(sorted(r["sha256_zip"] for r in k + f)).encode()).hexdigest()
    audit_tot = Counter()
    for r in inst["instruments"]:
        audit_tot.update({a: v for a, v in r["audit"].items() if isinstance(v, int)})
    man = {
        "schema_version": "vega-data-1",
        "zone": zone, "created_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timezone": "UTC (all timestamps ms since epoch, bar usable at close_time = open_time + interval)",
        "source": "https://data.binance.vision/data/futures/um/monthly/{klines/<SYM>/1m,fundingRate/<SYM>}",
        "archive_listing_created": listing["created_utc"], "archive_max_month": listing["archive_max_month"],
        "n_archive_symbols_total": listing["n_symbols"],
        "files": {"klines_1m_ok": len(k), "funding_ok": len(f), "status_counts": dict(st),
                  "bytes_zip_klines": sum(r["size"] for r in k), "rows_klines": sum(r.get("rows", 0) for r in k)},
        "combined_sha256_of_zip_hashes": files_hash,
        "checksum_policy": "Binance .CHECKSUM (sha256) verified per file; own sha256 of zip and parquet stored per file in data/meta/download_manifest.jsonl",
        "audit_totals": dict(audit_tot),
        "n_instruments": inst["n_instruments"],
        "data_availability": {
            "klines_1m": "2020-01 → 2025-12 (USDT-M perps, all archive symbols incl. delisted)",
            "funding": "full history per symbol (8h or symbol-specific interval_h)",
            "open_interest_long_short": "archive metrics only from ~2020-09 (BTC) / late 2021 for most → NOT USED",
            "bid_ask_spread_1m": "not available historically → slippage proxy (VEGA_PROTOCOL §6)",
            "liquidations": "incomplete → NOT USED",
            "holdout_2026": "NOT downloaded, NOT listed",
        },
        "instruments": [{"inst": r["inst"], "symbol": r["symbol"], "segment": r["segment"],
                         "listing_utc": _d(r["first_bar"]), "last_bar_utc": _d(r["last_bar"]),
                         "coverage": round(r["coverage"], 5), "missing_1m": r["missing_1m"],
                         "max_gap_min": r["max_gap_min"], "audit": r["audit"]} for r in inst["instruments"]],
    }
    (ROOT / f"DATA_MANIFEST_{zone}.json").write_text(json.dumps(man, indent=1))
    return man


def write_md(man: dict):
    z = man["zone"]
    ins = man["instruments"]
    boundary = "2024-12-31" if z == "dev" else "2025-12-31"
    ended = [r for r in ins if r["last_bar_utc"][:10] < boundary]
    multi = [r for r in ins if r["segment"] > 1 or r["inst"].endswith("#1")]
    lines = [f"# DATA_MANIFEST ({z})", "",
             f"Created {man['created_utc']} · schema {man['schema_version']} · {man['timezone']}", "",
             f"* Source: {man['source']}", f"* Archive symbols (≤ {man['archive_max_month']}): {man['n_archive_symbols_total']}",
             f"* 1m kline files OK: {man['files']['klines_1m_ok']} ({man['files']['bytes_zip_klines']/1e9:.2f} GB zip, "
             f"{man['files']['rows_klines']:,} rows); funding files OK: {man['files']['funding_ok']}",
             f"* File status counts: {man['files']['status_counts']}",
             f"* Combined SHA256 of all zip hashes: `{man['combined_sha256_of_zip_hashes']}`",
             f"* Instruments after segmentation: {man['n_instruments']}; ended before zone end (delisted or halted): {len(ended)}",
             f"* Audit totals: {man['audit_totals']}", "",
             "## Availability", ""] + [f"* {k}: {v}" for k, v in man["data_availability"].items()] + [
             "", "## Segmented tickers (relist / reuse)", ""] + [
             f"* {r['inst']}: {r['listing_utc']} → {r['last_bar_utc']}" for r in multi] + [
             "", "Full per-instrument listing/delisting/coverage table: `DATA_MANIFEST_%s.json`." % z]
    (ROOT / f"DATA_MANIFEST_{z}.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    z = sys.argv[1] if len(sys.argv) > 1 else "dev"
    m = build(z)
    write_md(m)
    print(json.dumps({k: m[k] for k in ("n_instruments", "files", "audit_totals")}))
