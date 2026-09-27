"""Append-only, hash-chained TRIAL LEDGER. Every evaluation (incl. failures/crashes) is recorded.
Rows are never deleted or rewritten; N_trials for multiple-testing correction = len(evaluations)."""
from __future__ import annotations

import fcntl
import hashlib
import json
import time
from pathlib import Path

from .. import kernel as K

LEDGER = K.VEGA_ROOT / "ledger" / "trials.jsonl"
COUNTED_STAGES = ("screen", "stress", "gate", "falsify", "inner")


def _h(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def last_hash(path: Path = LEDGER) -> str:
    if not path.exists() or path.stat().st_size == 0:
        return "0" * 64
    with open(path, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(max(0, size - 65536))
        tail = f.read().decode().strip().splitlines()
    return json.loads(tail[-1])["row_hash"]


def append(rows: list[dict], path: Path = LEDGER) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        prev = last_hash(path)
        for r in rows:
            r = dict(r)
            r.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
            r["prev_hash"] = prev
            body = json.dumps(r, sort_keys=True, default=str)
            r["row_hash"] = _h(body)
            f.write(json.dumps(r, sort_keys=True, default=str) + "\n")
            prev = r["row_hash"]
        f.flush()
        fcntl.flock(f, fcntl.LOCK_UN)


def read(path: Path = LEDGER) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def verify(path: Path = LEDGER) -> bool:
    prev = "0" * 64
    for r in read(path):
        h = r.pop("row_hash")
        if r["prev_hash"] != prev or _h(json.dumps(r, sort_keys=True, default=str)) != h:
            return False
        prev = h
    return True


def n_trials(path: Path = LEDGER) -> int:
    return sum(1 for r in read(path) if r.get("stage") in COUNTED_STAGES)
