"""Verify a migrated VEGA checkpoint against migration/CHECKPOINT_HASHES.json.

usage:
  python -m vega_core.migration_verify restore   # restore meta + ledger from migration/*.gz, check hashes
  python -m vega_core.migration_verify data      # re-downloaded zips == original sha256 (per file)
  python -m vega_core.migration_verify panel     # rebuilt panel npy files bit-identical to source
"""
from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import sys

from . import kernel as K

R = K.VEGA_ROOT
MIG = R / "migration"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def ref():
    return json.loads((MIG / "CHECKPOINT_HASHES.json").read_text())


def restore():
    (R / "data" / "meta").mkdir(parents=True, exist_ok=True)
    (R / "data" / "derived" / "dev").mkdir(parents=True, exist_ok=True)
    for src, dst in (("archive_listing.json.gz", "data/meta/archive_listing.json"),
                     ("download_manifest.jsonl.gz", "data/meta/download_manifest.jsonl"),
                     ("instruments_dev.json.gz", "data/derived/dev/instruments.reference.json")):
        with gzip.open(MIG / src, "rb") as f, open(R / dst, "wb") as g:
            shutil.copyfileobj(f, g)
    shutil.copy(MIG / "exchange_info.json", R / "data/meta/exchange_info.json")
    lj = R / "ledger" / "trials.jsonl"
    if not lj.exists():
        with gzip.open(R / "ledger/trials.jsonl.gz", "rb") as f, open(lj, "wb") as g:
            shutil.copyfileobj(f, g)
    bad = {f: (sha(R / f), h) for f, h in ref()["critical"].items() if sha(R / f) != h}
    from .evolution import ledger as L
    ok = not bad and L.verify()
    print(json.dumps({"critical_mismatch": bad, "ledger_rows": len(L.read()), "n_trials": L.n_trials(),
                      "chain_ok": L.verify(), "RESTORE_OK": ok}, indent=1))
    return 0 if ok else 1


def data():
    orig = {}
    with gzip.open(MIG / "download_manifest.jsonl.gz", "rt") as f:
        for l in f:
            r = json.loads(l)
            if r.get("status") == "ok":
                orig[r["url"]] = r["sha256_zip"]
    new = {}
    for l in open(R / "data/meta/download_manifest.jsonl"):
        r = json.loads(l)
        if r.get("status") == "ok":
            new[r["url"]] = r["sha256_zip"]
    dev = {u: h for u, h in orig.items() if "-2025-" not in u and "-2026-" not in u}
    missing = [u for u in dev if u not in new]
    diff = [u for u in dev if u in new and new[u] != dev[u]]
    hold = [u for u in new if "-2026-" in u]
    ok = not missing and not diff and not hold
    print(json.dumps({"files_ref": len(dev), "missing": len(missing), "sha_mismatch": len(diff),
                      "holdout_files": len(hold), "DATA_OK": ok, "examples": (missing + diff)[:5]}, indent=1))
    return 0 if ok else 1


def panel():
    rf = ref()["panel"]
    d = R / "data/derived/dev/panel"
    bad = [n for n, h in rf.items() if h and (not (d / n).exists() or sha(d / n) != h)]
    print(json.dumps({"panel_files": len(rf), "mismatch": bad, "PANEL_OK": not bad}, indent=1))
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit({"restore": restore, "data": data, "panel": panel}[sys.argv[1]]())
