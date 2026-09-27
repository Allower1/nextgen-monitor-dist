# DATA_MANIFEST (dev)

Created 2026-09-27T07:36:20Z · schema vega-data-1 · UTC (all timestamps ms since epoch, bar usable at close_time = open_time + interval)

* Source: https://data.binance.vision/data/futures/um/monthly/{klines/<SYM>/1m,fundingRate/<SYM>}
* Archive symbols (≤ 2025-12): 638
* 1m kline files OK: 9706 (13.80 GB zip, 416,033,480 rows); funding files OK: 9693
* File status counts: {'ok': 19399}
* Combined SHA256 of all zip hashes: `2c055c852a1106e71bc740772c50962702cb53fa6ab7cf1c15d2c12c3075949c`
* Instruments after segmentation: 399; ended before zone end (delisted or halted): 59
* Audit totals: {'rows_raw': 421101335, 'duplicates': 0, 'misaligned': 0, 'bad_ohlc': 0, 'zero_trade_flat': 18223940, 'rows_clean': 402877395}

## Availability

* klines_1m: 2020-01 → 2025-12 (USDT-M perps, all archive symbols incl. delisted)
* funding: full history per symbol (8h or symbol-specific interval_h)
* open_interest_long_short: archive metrics only from ~2020-09 (BTC) / late 2021 for most → NOT USED
* bid_ask_spread_1m: not available historically → slippage proxy (VEGA_PROTOCOL §6)
* liquidations: incomplete → NOT USED
* holdout_2026: NOT downloaded, NOT listed

## Segmented tickers (relist / reuse)

* BNXUSDT#1: 2022-04-01 03:30 → 2023-01-31 23:59
* BNXUSDT#2: 2023-02-22 14:45 → 2024-12-31 23:59
* ICPUSDT#1: 2021-05-11 03:00 → 2022-06-10 09:00
* ICPUSDT#2: 2022-09-27 02:30 → 2024-12-31 23:59
* TLMUSDT#1: 2021-07-16 03:30 → 2022-06-09 08:59
* TLMUSDT#2: 2023-03-30 12:30 → 2024-12-31 23:59

Full per-instrument listing/delisting/coverage table: `DATA_MANIFEST_dev.json`.
