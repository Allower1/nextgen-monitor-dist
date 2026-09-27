# HOLDOUT_PROTOCOL.md

Holdout: 2026-01-01 00:00 UTC → 2026-09-20 00:00 UTC (exclusive). Status: **LOCKED, not downloaded**.

Before opening:
1. Freeze code, finalist specs, universe rules, execution/accounting, costs, gates.
2. `git tag vega-holdout-freeze-vN`; `FINALISTS_MANIFEST.json` with SHA256 of every source file,
   the finalist specs, the kernel hash, and k (≤ 3) with Bonferroni α_i = 0.05/k.
3. Write "HOLDOUT READY" to PROGRESS.md (+ notifier) and STOP.
4. Only after the user writes `UNLOCK`: create `HOLDOUT_UNLOCKED` (contains user's UNLOCK text,
   date, finalist manifest hash), download 2025-12-24 → 2026-09-20 data, run ONCE
   (`scripts/run_holdout.py`), write results, commit.

Pass criteria: VEGA_PROTOCOL.md §10. Failure ⇒ "edge not confirmed". Re-testing a modified
candidate on this holdout is forbidden; the next honest test is forward paper / data after
2026-09-20.
