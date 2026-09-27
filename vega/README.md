# VEGA — autonomous evolutionary intraday research system (research + paper only)

Separate project (not Nova / Nova Evo). Binance USDT-M perpetuals, 1m data, dynamic TOP-20,
evolutionary candidate search with heavy falsification. Honest expected result: PROMOTE NONE.

Start here: `VEGA_SPEC.md` → `VEGA_PROTOCOL.md` (frozen numbers) → `PROGRESS.md` → `NEXT_TASK.md`.

Layout: `vega_core/` (code; `kernel.py` = frozen safety kernel), `tests/`, `scripts/`,
`ledger/` (append-only trial ledger, committed), `data/` (git-ignored; rebuilt from
`DATA_MANIFEST.json`), `results/` (summaries committed, caches ignored).

No API keys, no live orders. Ever — without explicit separate user permission.
