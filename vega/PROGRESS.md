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
