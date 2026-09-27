#!/usr/bin/env bash
# derive → universe panel → features for one zone (dev|inner). Low priority; run via run_bg.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
zone="${1:-dev}"
python3 - "$zone" <<'PY'
import json, sys
z = sys.argv[1]
last = {}
for l in open("data/meta/download_manifest.jsonl"):
    r = json.loads(l)
    if r.get("zone") == z:
        last[r["url"]] = r["status"]
bad = [u for u, s in last.items() if s != "ok"]
print(f"manifest check {z}: {len(last)} files, {len(bad)} not ok")
sys.exit(1 if bad else 0)
PY
echo "[$(date -u +%FT%TZ)] derive $zone"
python3 -m vega_core.data.derive --zone "$zone" --workers 3
python3 -m vega_core.data.manifest "$zone"
if [ "${KEEP_1M:-0}" != "1" ]; then
  # D-012: free disk — raw 1m parquet is re-downloadable/verifiable from the manifest.
  # Keep dev 2024-12 (warm-up month for the inner zone).
  echo "[$(date -u +%FT%TZ)] removing raw 1m parquet of $zone (manifest keeps checksums)"
  find "data/k1m/$zone" -name '*.parquet' ! -name '2024-12.parquet' -delete
fi
echo "[$(date -u +%FT%TZ)] universe $zone"
python3 -m vega_core.universe --zone "$zone"
echo "[$(date -u +%FT%TZ)] features $zone"
python3 -m vega_core.features --zone "$zone"
echo "[$(date -u +%FT%TZ)] BUILD DONE $zone"
