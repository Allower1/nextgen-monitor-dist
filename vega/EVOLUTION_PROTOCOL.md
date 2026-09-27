# EVOLUTION_PROTOCOL.md

Loop: GENERATE → TEST → FALSIFY → REJECT MOST → MUTATE → PROMOTE RARELY → REMEMBER → REPEAT.

* CandidateSpec (JSON, canonical sorted keys) = {family, params, scanner weights, timeframe,
  exits, sizing}. spec_hash = sha256(canonical JSON)[:16]. Immutable once evaluated.
* Lineage: parent hashes, generation, mutation op, seed. Crossover only between candidates of
  the same family (parameter-wise uniform crossover) — justified because params share semantics.
* Seeds: master seed per run; each child seed = hash(master, generation, index). Deterministic.
* Fitness (evolution zone only, trades 2020-01-01 → 2024-12-24): computed on 10 half-year
  blocks. fitness = median block Sharpe (1.0x costs) − 0.5·std(block Sharpe) with hard
  rejections: net expectancy ≤ 0 at 1.5x costs, trades/day median outside [5, 60] (looser than
  the gate — search corridor), fewer than 6 positive blocks.
* Screening is done on a stratified subsample first (every other month: "screen set");
  survivors get the full evolution window. Both evaluations go to the ledger.
* Tournament: size 4, elitism top 5 %, retirement after 3 generations without improvement of a
  lineage, population ≈ 64 per generation per family.
* Trial ledger `ledger/trials.jsonl`: append-only; each row {ts, run_id, spec_hash, spec, seed,
  stage, metrics, status, prev_hash, row_hash}. Failed/crashed evaluations are recorded too.
  N_trials for DSR = number of rows with stage in {screen, full} (conservative: counts every
  evaluated configuration).
* Experiment memory: `ledger/memory.json` summarises which families/regions failed, so the
  generator de-prioritises exhausted regions (novelty ≥ minimal param distance).
* Promotion stage: candidates passing G1–G6/G11 on the full window enter the falsification suite
  (G7–G13). Only full passes become inner-validation candidates (≤ 10 per session).
* MUTABLE: feature subset, lookbacks (≤ 7 d), thresholds, horizons/holding (≤ 12 h),
  entry/exit/stop/TP logic, regime routing, timeframe, model family, sizing within kernel caps,
  scanner score composition, anomaly thresholds.
* IMMUTABLE (kernel): fees, slippage, funding, accounting, zones, future-data rules, next-bar
  execution, caps, gates, data source, leakage protections, capital/leverage.

## Implemented families (v1)
rule-based: `momentum_breakout`, `mean_reversion`, `vol_expansion`, `xs_momentum` (cross-sectional
ranking inside the TOP-20), `opportunity` (anomaly-flagged instruments only), `flow_imbalance`
(taker-buy imbalance); fitted: `ridge_wf` (ridge regression on an evolved feature subset,
purged expanding walk-forward over half-year blocks, 7-day purge + label horizon, block 2020H1 =
training only). Common evolvable execution genes: direction, regime filter, SL/TP in volatility
units, max hold (≤ 144 bars = 12 h), cooldown, exit-on-opposite, size (≤ 0.30), entry timeframe
(5m / 15m / 30m closes). Scanner genes: weights of 8 activity metrics, anomaly boost, anomaly
thresholds.
