#!/usr/bin/env bash
# Evolution run (resumable: re-running with the same run id continues from results/evo_state.json)
# usage: scripts/run_bg.sh evo_R1 scripts/evolve.sh R1 <generations> [workers] [pop]
set -euo pipefail
cd "$(dirname "$0")/.."
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1
python3 -m vega_core.evolution.engine --run-id "$1" --generations "$2" --workers "${3:-3}" --pop "${4:-16}"
echo "EVOLUTION DONE $1"
