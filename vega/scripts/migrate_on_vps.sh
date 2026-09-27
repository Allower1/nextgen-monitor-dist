#!/usr/bin/env bash
# VEGA migration to the Contabo VPS (run ON THE VPS as user ubuntu).
# Clones the exact checkpoint, restores ledger/state/meta, re-downloads 2020-2024 from the same
# archive with per-file SHA256 verification, rebuilds the panel and checks it is bit-identical,
# runs tests, then resumes R1 from results/evo_state.json (never from generation 0).
# The 2026 holdout is never listed or downloaded (the restored archive listing ends at 2025-12).
set -euo pipefail
REPO=https://github.com/Allower1/nextgen-monitor-dist.git
BRANCH=claude/vega-intraday-evolution-gyfsac
CHECKPOINT=${CHECKPOINT:?set CHECKPOINT=<expected HEAD sha>}
TARGET=/home/ubuntu/vega
WORKERS=${WORKERS:-$(( $(nproc) - 2 ))}
echo "== resources"; nproc; free -h; df -h /home/ubuntu; uptime
if [ -d "$TARGET" ] && [ -n "$(ls -A "$TARGET")" ] && [ ! -d "$TARGET/.git" ]; then
  echo "REFUSING: $TARGET exists and is not empty"; exit 2; fi
[ -d "$TARGET/.git" ] || git clone --branch "$BRANCH" "$REPO" "$TARGET"
cd "$TARGET"; git fetch origin "$BRANCH"; git checkout -q "$CHECKPOINT"
test "$(git rev-parse HEAD)" = "$CHECKPOINT"; git status --short
cd vega
python3 -m venv .venv; . .venv/bin/activate; pip install -q -r requirements.txt
python -m vega_core.migration_verify restore
python -m pytest -q tests
echo "== re-download 2020-2024 (same archive, checksums verified)"
nice -n 10 ionice -c3 python -m vega_core.data.download --zone dev --workers 24
python -m vega_core.migration_verify data
KEEP_1M=1 nice -n 10 ionice -c3 scripts/build_zone.sh dev
python -m vega_core.migration_verify panel
git -C "$TARGET" checkout -q -B "$BRANCH" "$CHECKPOINT"
echo "MIGRATION VERIFIED — resuming R1 with $WORKERS workers"
scripts/run_bg.sh evo_R1 scripts/evolve.sh R1 400 "$WORKERS" 16
sleep 30; grep "^\[start\]" logs/evo_R1.log
