# PROGRESS.md

## Phase A — isolation, environment, resource audit, protocol freeze  ✅ (2026-09-27)

Resource audit at start (2026-09-27 06:56 UTC):
* Host: ephemeral cloud container (Firecracker VM), Linux 6.18, Python 3.11.15
* CPU: 4 vCPU Intel Xeon @ 2.10 GHz; load average 0.05 0.06 0.02
* RAM: 15.7 GiB total, 15.2 GiB available; no swap
* Disk: 31.3 GB free (allowance), `/` 22 % used
* Foreign processes: none besides container infrastructure (process_api, environment-manager,
  sbx-telemetry-collector, claude agent). **No Nova / Nova Evo / ADAM / Luna / bot-nextgen /
  M30/M32 collectors exist on this host**; `/home/ubuntu` contained only dotfiles.
* Network: data.binance.vision ✅ (S3 listing + files); fapi.binance.com ❌ HTTP 451 (geo);
  www.binance.com/fapi/v1/exchangeInfo ✅ (public, used for current tick/step/min-notional).
* VEGA limits: 3 workers max (1 core free), RAM ceiling ≈ 9.0 GiB, disk floor 5.0 GB free,
  `nice -n 10 ionice -c3` for heavy jobs (`scripts/run_bg.sh`).
* Python deps installed: numpy 2.4.6, pandas 3.0.6, pyarrow 25.0.1, numba 0.67.0, scipy 1.17.1,
  pytest 9.1.1.

Protocol frozen: VEGA_PROTOCOL.md + vega_core/kernel.py, hashes in PROTOCOL_MANIFEST.json,
tag `vega-protocol-freeze-v1`. Tests: 7 passed / 0 failed.

Untouched-data status: 2025 inner validation — not downloaded; 2026 holdout — not downloaded,
not listed.

## Phase B — data engineering (in progress, 2026-09-27)
* Archive discovery (`vega_core/data/discover.py`, 257 s): **638 USDT-M perpetual symbols** in the
  archive with 1m files ≤ 2025-12 (incl. delisted); keys dated ≥ 2026-01 dropped unseen.
  1m zip volume: 2020–2024 = 13.80 GB (9 706 files), 2025 = 8.03 GB (5 980 files).
  Symbols by first month (≥ 2020): 2020: 81, 2021: 59, 2022: 26, 2023: 99, 2024: 131, 2025: 242.
* Funding history 2020–2024: 9 633 monthly files downloaded, all checksums OK.
* 1m klines 2020–2024 downloading (resumable; parquet zstd; Binance CHECKSUM + own SHA256 per
  file in `data/meta/download_manifest.jsonl`).
* Current exchangeInfo (www.binance.com/fapi, public) stored for step/minNotional only.

## Phase C/D/E code (written + unit-tested before any real-data backtest)
universe panel, frozen pool, scanner, feature library, numba engine, metrics (DSR, PBO/CSCV,
bootstrap), 7 strategy families (6 rule-based + ridge walk-forward), evolution engine,
hash-chained trial ledger, gates G1–G14, falsification suite. Tests: 44 passed / 0 failed.

## Phase B complete (2026-09-27 07:41 UTC)
* 2020–2024: 9 706 kline files (13.80 GB zip, 416 033 480 1m rows) + 9 693 funding files; 19 399/19 399
  checksums OK. Audit: 0 duplicates, 0 misaligned, 0 bad OHLC, 18 223 940 zero-trade flat bars → missing (D-015).
* 396 symbols → 399 instruments (BNX, ICP, TLM split into two segments); 59 ended before 2024-12-31.
* Eligible instruments per hour (median): 2020 17 · 2021 113 · 2022 135 · 2023 150 · 2024 229.
  Distinct instruments that entered the pool: 2020 80 · 2021 136 · 2022 163 · 2023 245 · 2024 362.
* Panel: T = 526 176 5m steps, H = 43 848 h, 80.1 M ragged 5m rows, 951 831 funding events.
* Build times: download 2×~10 min, derive 143 s, panel 95 s, features 218 s. Raw 1m dev parquet deleted
  after derive (D-012), except 2024-12 (inner warm-up).

## Phase E/F — evolution R1 started 07:42 UTC
`scripts/run_bg.sh evo_R1 scripts/evolve.sh R1 400 3 16` (PID in logs/evo_R1.pid). 7 families × 16/gen,
~1.4 min/generation, ~4 GB RAM, 3 workers (1 core free).
Random candidates (gen 0): all negative after costs (e.g. −23 … −67 bps/trade) — costs dominate as expected.
