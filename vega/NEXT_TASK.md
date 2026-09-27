# NEXT_TASK.md

State: Phase B data for 2020–2024 downloaded (19 399 files, all checksums OK). Building derived
panel (`logs/build_dev.log`). Phase C/D/E code done + tested.

Next exact actions:
1. Wait for `BUILD DONE dev` in logs/build_dev.log; commit DATA_MANIFEST_dev.{json,md}.
2. Sanity baselines on real data (random/placebo candidates → expected cost drag).
3. `scripts/run_bg.sh evo_R1 scripts/evolve.sh R1 <gens> 3 16` (resumable).
4. `python -m vega_core.promote` → results/promotion_report.json.
5. If a candidate passes all G1–G13: download 2025 (`python -m vega_core.data.download --zone inner`),
   `scripts/build_zone.sh inner`, `python -m vega_core.inner_validation`.
   If none passes: PROMOTE NONE (report), keep evolving within budget.
