"""PHASE H — FINAL HOLDOUT (2026-01-01 → 2026-09-20). ONE run, no tuning.

This module refuses to do anything unless:
  1. `HOLDOUT_UNLOCKED` exists and contains the user's explicit "UNLOCK" (written only after the
     user types UNLOCK in the conversation), and
  2. `FINALISTS_MANIFEST.json` exists, its SHA256 is referenced inside HOLDOUT_UNLOCKED, and every
     source-file hash in it matches the working tree (frozen code), and
  3. `results/holdout_result.json` does NOT exist yet (single run).
Data for the holdout is downloaded only by `prepare_data()` after these checks.
"""
from __future__ import annotations

import hashlib
import json
import sys

from . import kernel as K

MANIFEST = K.VEGA_ROOT / "FINALISTS_MANIFEST.json"
RESULT = K.VEGA_ROOT / "results" / "holdout_result.json"


def preflight() -> dict:
    if not K.holdout_unlocked():
        raise K.LeakageError("HOLDOUT LOCKED: waiting for explicit user UNLOCK")
    if RESULT.exists():
        raise K.LeakageError("holdout already run once — re-running is forbidden")
    if not MANIFEST.exists():
        raise K.LeakageError("no FINALISTS_MANIFEST.json — nothing frozen")
    raw = MANIFEST.read_bytes()
    mh = hashlib.sha256(raw).hexdigest()
    if mh not in K.UNLOCK_FILE.read_text():
        raise K.LeakageError("UNLOCK file does not reference the frozen finalist manifest hash")
    man = json.loads(raw)
    for rel, h in man["files"].items():
        if hashlib.sha256((K.VEGA_ROOT / rel).read_bytes()).hexdigest() != h:
            raise K.LeakageError(f"frozen file changed after freeze: {rel}")
    if not 1 <= len(man["finalists"]) <= K.GATES.holdout_max_finalists:
        raise K.LeakageError("finalist count outside 1..3")
    return man


if __name__ == "__main__":
    try:
        preflight()
    except K.LeakageError as e:
        print(f"REFUSED: {e}")
        sys.exit(2)
    print("preflight OK — holdout run implementation is executed only after UNLOCK")
