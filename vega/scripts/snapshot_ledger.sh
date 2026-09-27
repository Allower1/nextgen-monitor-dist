#!/usr/bin/env bash
# Compressed, hash-stamped snapshot of the append-only trial ledger for git (raw jsonl is ignored).
set -euo pipefail
cd "$(dirname "$0")/.."
gzip -9 -c ledger/trials.jsonl > ledger/trials.jsonl.gz
python3 - <<'PY'
import hashlib, json
from vega_core.evolution import ledger as L
rows = L.read()
info = {"rows": len(rows), "n_trials_counted": L.n_trials(), "chain_ok": L.verify(),
        "last_row_hash": rows[-1]["row_hash"] if rows else None,
        "sha256_jsonl": hashlib.sha256(open("ledger/trials.jsonl", "rb").read()).hexdigest()}
open("ledger/LEDGER_SNAPSHOT.json", "w").write(json.dumps(info, indent=1))
print(info)
PY
