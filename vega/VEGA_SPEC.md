# VEGA_SPEC.md

## Purpose
VEGA is a MARKET EVOLUTION SYSTEM, not one model:

MARKET → SCAN → RANK OPPORTUNITIES → SELECT SYMBOLS → GENERATE CANDIDATES → TEST → FALSIFY →
MUTATE → REJECT MOST → FREEZE RARE SURVIVORS → UNTOUCHED TEST → PAPER → (only later) MICRO-LIVE.

Goal: find an intraday candidate (≈20 completed trades/day portfolio-wide, 10–40 allowed as
daily median) whose edge survives realistic costs (fees + slippage + funding) and can be
falsified within days of paper trading. Not a pretty backtest.

## Components
| Module | Responsibility |
|---|---|
| `vega_core/kernel.py` | SAFETY KERNEL: frozen constants, cost/slippage model, funding cash flow, liquidation price, gates, ZoneGuard (holdout/inner lock) |
| `vega_core/data/discover.py` | archive symbol discovery (incl. delisted) from data.binance.vision, ≤ 2025-12 only |
| `vega_core/data/download.py` | resumable downloader, CHECKSUM + own SHA256, disk guard |
| `vega_core/data/store.py` | canonical 1m parquet store per instrument, zone-guarded readers |
| `vega_core/data/audit.py` | duplicates, gaps, timestamps, corrupt files, segmenting (relists/reuse) |
| `vega_core/universe.py` | listing/delisting, eligibility, hourly metrics table |
| `vega_core/scanner.py` | MarketActivityScore, Opportunity/Crisis mode, dynamic TOP-20 |
| `vega_core/panel.py` | 5m trading panel for shortlisted instruments (execution prices, features) |
| `vega_core/backtest.py` | event-driven portfolio backtester (numba), next-bar execution, costs, funding, liquidation, caps |
| `vega_core/metrics.py` | all metrics in the spec incl. DSR, PBO, bootstrap |
| `vega_core/strategies/` | model families (rule-based first) as parameterised CandidateSpec |
| `vega_core/evolution/` | registry, mutation, tournament, trial ledger, experiment memory |
| `vega_core/paper/` | public-data paper trader (Phase I) |

## Timeframes
Canonical 1m. 5m / 15m / 30m / 1h by deterministic resampling of 1m (a resampled bar is usable
only at its close_time). Entry decisions on 5m (v1), context from closed 15m/30m/1h bars.

## Honest expectation
Round-trip costs 0.12–0.30 % × 20 trades/day is a high hurdle. PROMOTE NONE is the most likely
and fully acceptable outcome.
