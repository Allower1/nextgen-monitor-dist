# NEXT_TASK.md — MIGRATE TO CONTABO VPS, THEN RESUME R1

Cloud checkpoint: see PROGRESS.md "Final cloud checkpoint" (R1 stopped after generation 16; state gen 17).

On the VPS (user ubuntu):
    curl -fsSL https://raw.githubusercontent.com/Allower1/nextgen-monitor-dist/<HEAD>/vega/scripts/migrate_on_vps.sh -o /tmp/m.sh
    CHECKPOINT=<HEAD> bash /tmp/m.sh
(or clone the branch and run `CHECKPOINT=<HEAD> vega/scripts/migrate_on_vps.sh`).
It stops with a non-zero exit at the first failed verification (restore hashes, ledger chain,
tests, per-file data SHA256, bit-identical panel). Only after all pass does it resume R1 from gen 17.

Then: finish R1 → `python -m vega_core.promote` → PROMOTE NONE or falsification / 2025 contaminated
stress test → HOLDOUT READY stop. Holdout 2026-01-01 → 2026-09-20 stays LOCKED until explicit UNLOCK.
