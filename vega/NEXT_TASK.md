# NEXT_TASK.md

Phase B — data engineering:
1. `python -m vega_core.data.discover` → archive symbol list incl. delisted (≤ 2025-12 keys only),
   file sizes → size estimate → DATA_MANIFEST.json skeleton.
2. `scripts/run_bg.sh download python -m vega_core.data.download` (resumable) → 1m klines +
   funding for 2020-01 … 2024-12 (evolution) and 2025 (inner, stored under a zone-guarded path).
3. Audit + segmentation + listing/delisting manifest.
