# VEGA_PROTOCOL.md — FROZEN RESEARCH PROTOCOL

Status: **FROZEN** at git tag `vega-protocol-freeze-v1` (Phase A, 2026-09-27, before any data
download and before any backtest). Every number below is also encoded in
`vega_core/kernel.py` (the SAFETY KERNEL); `tests/test_kernel_frozen.py` asserts that the two agree
and the kernel SHA256 is recorded in `PROTOCOL_MANIFEST.json`.

Changing anything in this file after `vega-protocol-freeze-v1` is FORBIDDEN, except
(a) typo fixes that do not change a number or a rule, (b) adding a *more conservative* rule,
each logged in DECISIONS.md with reason. Gates may never be loosened.

---------------------------------------------------------------------------------------------
## 1. Resources and isolation (VEGA hard limits)

Host at freeze time: cloud container, 4 vCPU (Xeon 2.1 GHz), 15.7 GiB RAM, ~31 GB writable disk
allowance, load avg 0.05. No Nova / Nova Evo / ADAM / Luna / bot-nextgen processes or paths exist
on this host (audited in PROGRESS.md). The same limits apply unchanged if VEGA is moved to the
shared server.

| Limit | Value |
|---|---|
| CPU | max workers = `max(1, n_cpu - 2)` when other projects run, `n_cpu - 1` on a dedicated host (here: 3). Never all cores. |
| Priority | every heavy job: `nice -n 10 ionice -c3` (`scripts/run_bg.sh` enforces it) |
| RAM ceiling | 60 % of MemAvailable at job start (here ≈ 9.0 GiB); workers × per-worker estimate must fit |
| Disk | estimate size before every bulk download; downloader aborts when free disk < 15 % of the allowance at freeze time (hard floor **5.0 GB free**) |
| Foreign processes | never stopped, restarted, reniced. If one dies while VEGA runs: halve VEGA workers, log in PROGRESS.md |
| Paths VEGA must never write | `/home/ubuntu/nextgen-market-lab`, `/home/ubuntu/worktrees/nova-v2-evolution`, `/home/ubuntu/worktrees/nova-v3-evolution`, `/home/ubuntu/bot-nextgen` |

## 2. Secrets
Public endpoints only (data.binance.vision archive; Binance public REST/websocket). No API keys of
any kind are used or stored. `.env*` is git-ignored. A Telegram token, if ever used, is read from
the environment variable `VEGA_TG_TOKEN`/`VEGA_TG_CHAT` only, never written to disk by VEGA.

## 3. Data zones (UTC, end exclusive)

| Zone | Period | Access |
|---|---|---|
| EVOLUTION (development) | 2020-01-01 00:00 → 2025-01-01 00:00 | generation, mutation, walk-forward, falsification |
| EVOLUTION trade window | entries 2020-01-01 → **2024-12-24 00:00**; every position force-closed by 2024-12-24 12:00 | last 7 days = embargo buffer |
| INNER VALIDATION | trading 2025-01-01 00:00 → 2025-12-24 00:00 (feature warm-up may read 2024-12-24 → 2025-01-01) | only in `mode="inner_validation"`, only for frozen candidates, ≤ 3 logged sessions |
| FINAL HOLDOUT | trading 2026-01-01 00:00 → 2026-09-20 00:00 (warm-up may read 2025-12-24 → 2026-01-01) | NOT downloaded, NOT listed, NOT read before an explicit user `UNLOCK` |

* `EMBARGO = 7 days` = `MAX_LOOKBACK` (the longest lookback any candidate / scanner feature may
  use) and ≥ `MAX_HOLD` (12 h). Nothing in one zone's trade window depends on the next zone.
* Code guard: `kernel.ZoneGuard` raises `LeakageError` when evolution-mode code requests any
  timestamp ≥ 2025-01-01, or any mode requests ≥ 2026-01-01 without the unlock file
  `HOLDOUT_UNLOCKED` containing the user's UNLOCK confirmation and the frozen finalist hash.
* The archive discovery code drops every archive key dated ≥ 2026-01 *before* storing or
  printing anything (symbol listing, listing/delisting dates are computed only from ≤ 2025-12
  files; evolution mode additionally clamps them at 2024-12-31).

## 4. Universe
* Binance USDT-M perpetual contracts only (symbol ends with `USDT`, no `_YYMMDD` delivery
  contracts, no USDC/BUSD margined). Spot data: disabled.
* Symbol list from the data.binance.vision archive (includes delisted contracts), never from the
  current exchangeInfo.
* Instrument = (symbol, continuous segment). A gap ≥ 7 days without bars, or a >70 % price
  discontinuity across a gap ≥ 1 day, starts a new instrument id `SYMBOL#k`. Different tickers
  (LUNA / LUNA2, SHIB / 1000SHIB) are always different instruments.
* listing time = first real bar; delisting time = last real bar (within the accessible zone).
* Eligible at hour H iff: ≥ 7 full days (10 080 1m bars span) since listing, ≥ 95 % of 1m bars
  present in the last 24 h, the last closed hour fully present (no forward-filled prices), and
  H is more than 48 h before the known delisting time.
* Dynamic shortlist: every hour, `TOP_N = 20` instruments ranked by the candidate's (mutable)
  scanner score, computed only from data closed before H. Pre-filter (frozen): trailing-24 h
  quote volume ≥ 5 000 000 USDT.

## 5. Capital, accounting, margin (frozen)

| Item | Value |
|---|---|
| Starting capital | 10 000 USDT |
| Max gross leverage (sum |notional| / equity) | 3.0x |
| Max per-position notional | 0.30 × equity |
| Max per-symbol notional | 0.30 × equity |
| Max concurrent positions | 12 |
| Net BTC-beta exposure cap | |Σ βᵢ·notionalᵢ| ≤ 1.5 × equity (β: trailing 7-day 1h beta to BTCUSDT, clipped [0, 3], default 1.0) |
| Max holding time | 12 h (forced market exit) |
| Margin mode | isolated, per-position leverage 5x (margin = notional / 5) |
| Maintenance margin rate | 0.5 % BTC/ETH, 1.0 % others |
| Liquidation | if the adverse extreme of a bar reaches the isolated liquidation price the position is closed at the liquidation price and the whole margin is lost plus a 1.0 % liquidation fee on notional |
| Mark-to-market | every 5m bar (close price) |
| Funding | every historical funding event (exact archive timestamp, symbol-specific interval): cash −= side × notional_at_funding_price × rate (long pays positive rate). Mandatory in PnL. Missing funding record → the conservative rate `max(|last known rate|, 0.01 %)` charged against the position |
| Rounding | quantity rounded *down* to the exchange step size (current exchangeInfo for live contracts); delisted contracts (no exchangeInfo): notional rounded down to a multiple of 1 USDT. Min notional: exchangeInfo value if known, else 5 USDT (100 USDT BTC/ETH). Orders below min notional are skipped |

## 6. Costs (frozen, SAFETY KERNEL)

* Taker fee: **0.050 % per side** (Binance USDT-M VIP0, no BNB discount; applied to every fill,
  including stop/TP and forced exits). Historical 2020 fee was 0.040 %: using 0.050 % throughout
  is conservative. Maker fee (0.020 %) is NOT used: v1 strategies use market orders only.
* Slippage per side (bps of price, applied adversely to every fill):

      slip = mult_crisis × ( floor(ADV) + 0.10 × rv1m_bps + 10 000 × σ_day × sqrt(Q / ADV) )

  - `ADV` = trailing-24h quote volume (USDT) of the instrument, closed data only;
  - `floor(ADV)` = 1 bps if ADV ≥ 1e9; 2 bps if ≥ 1e8; 4 bps if ≥ 2e7; 8 bps otherwise;
  - `rv1m_bps` = std of 1m log returns over the trailing 60 minutes, in bps;
  - `σ_day` = rv1m × sqrt(1440) (fraction);
  - `Q` = order notional (USDT);
  - `mult_crisis` = clip(rv_ratio / 2, 1, 4) where rv_ratio = trailing-1h rv1m / median hourly
    rv1m of the trailing 7 days (crisis execution degrades).
  - Stop orders additionally fill at the worse of (stop price, bar open) when the bar gaps
    through the stop.
* Spread is not observable historically; it is absorbed in the slippage proxy above.
* Stress levels: 1.0x, 1.5x, 2.0x, 3.0x applied to (fee + slippage). Funding is never scaled.
* Base-case round trip ≈ 0.12 % (BTC) … 0.30 %+ (small alts).

## 7. Execution (frozen)
* Signals are computed on CLOSED bars only. Bar with close_time T is usable at T.
* Market orders fill at the open of the 1m bar starting at T + 60 s (60 s latency), plus slippage
  and fee. No same-bar fill.
* Intrabar stop / take-profit on 5m high/low; the entry bar uses only the 1m bars after the fill.
  If stop and TP are both touched in one bar → STOP.
* Simultaneous signals: processed in deterministic order (score desc, then instrument id asc);
  caps applied greedily; the rest skipped (logged).
* Delisting: no entries during the last 48 h before delisting; open positions closed at 48 h.
  Data gaps (missing bars) while in position → exit at the first available bar open with 2x
  slippage (conservative "halt" assumption).

## 8. Validation, overfitting control, multiple testing

* Evolution fitness: 2020-01-01 → 2024-12-24 split in 10 half-year blocks (B1..B10); fitted
  model families (ridge / logistic / trees / MLP) use purged expanding walk-forward: train on
  blocks < k with a 7-day purge+embargo, predict block k (B1 is warm-up only for fitted models).
* Trial ledger (`ledger/trials.jsonl`, append-only, hash chained): every evaluated candidate,
  including failures/crashes, counts in N_trials for Deflated Sharpe.
* Falsification suite for any candidate reaching the promotion stage: cost stress, parameter
  neighbourhood, block bootstrap, 100 placebo runs, symbol leave-one-out, year leave-one-out,
  regime split, latency stress (+2 min).

## 9. PROMOTION GATES (frozen numbers; all must pass; else PROMOTE NONE)

All on the evolution trade window 2020-01-01 → 2024-12-24 (walk-forward OOS for fitted models),
unless stated. "Costs 1.0x" = base model above.

| # | Gate | Threshold |
|---|---|---|
| G1 | Net expectancy per trade at 2.0x costs | > 0 |
| G2 | Completed trades/day (calendar days with an eligible universe) | median ∈ [10, 40] AND mean ∈ [10, 40] |
| G3 | Positive calendar years (net, 1.0x) among 2020, 2021, 2022, 2023, 2024 | ≥ 4 of 5 |
| G4 | Max single-instrument share of total net PnL (1.0x) | ≤ 25 %; top-3 ≤ 50 % |
| G5 | Max drawdown of compounded equity | ≤ 25 % at 1.0x; ≤ 35 % at 2.0x |
| G6 | Annualised Sharpe of daily net returns (1.0x) | ≥ 1.0 |
| G7 | Deflated Sharpe Ratio probability with N = total trial-ledger count at evaluation time | ≥ 0.95 |
| G8 | Parameter neighbourhood: 24 perturbations (each numeric param ×U[0.8,1.2], ints ±1 step) | ≥ 80 % have net expectancy > 0 at 1.0x AND median Sharpe ≥ 0.5 × candidate Sharpe |
| G9 | PBO (CSCV over the 10 blocks, candidate pool of the final tournament) | ≤ 0.20 |
| G10 | Placebo: 100 random-timing/random-direction runs with identical trade count and holding-time distribution | candidate Sharpe > 95th percentile |
| G11 | Half-year blocks with positive net PnL (1.0x) | ≥ 7 of 10 |
| G12 | Symbol leave-top-1-out and leave-top-3-out | net PnL > 0 at 1.0x |
| G13 | Latency stress (+120 s extra latency) | net expectancy > 0 at 1.0x |
| G14 | INNER VALIDATION 2025 (1.0x) | net PnL > 0 at 1.5x costs, Sharpe ≥ 0.75, MDD ≤ 25 %, median trades/day ∈ [10, 40], max instrument share ≤ 35 % |

Inner validation: at most **3 sessions**, each evaluating at most **10 frozen candidates**; every
session is logged in `ledger/inner_validation.jsonl` and every evaluated candidate increments
N_trials. Candidates may not be modified after seeing 2025 results; a candidate that fails G14 is
retired permanently.

## 10. Holdout (Phase H)
* Max **3 finalists**, decided and recorded before UNLOCK. Family-wise α = 0.05, Bonferroni:
  α_i = 0.05 / k (k = number of finalists).
* Holdout PASS for a finalist requires ALL of: one-sided t-test of daily net returns (1.0x
  costs) mean > 0 with p < α_i; net PnL > 0 at 1.5x costs; MDD ≤ 30 %; median trades/day
  ∈ [10, 40]; max instrument share ≤ 35 %; zero crashes.
* One run only. No tuning. A failure ⇒ "edge not confirmed"; re-testing a modified candidate on
  this holdout is FORBIDDEN.

## 11. Paper (Phase I) kill rules
Per track: kill if drawdown > 15 % of paper equity, or 0 completed trades in any 24 h window,
or > 60 trades in any 24 h window, or 3 process crashes in 24 h. Checkpoints at 24 h / 72 h / 7 d.

## 12. Honest expectation
The most likely outcome is **PROMOTE NONE**. That is a valid scientific result.
