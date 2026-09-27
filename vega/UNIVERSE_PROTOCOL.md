# UNIVERSE_PROTOCOL.md

1. Source of symbols: directory listing of `data/futures/um/monthly/klines/` and
   `data/futures/um/daily/klines/` on data.binance.vision (contains delisted contracts).
   NOT the current exchangeInfo (survivorship bias).
2. Filter: symbol ends with `USDT`, contains no `_` (delivery contracts excluded).
3. Archive keys whose month > 2025-12 are discarded before storage/logging (holdout blindness).
4. Instrument segmentation (`vega_core/data/audit.py`): a gap ≥ 7 days, or a gap ≥ 1 day with a
   >70 % price discontinuity, splits a symbol into `SYMBOL#1`, `SYMBOL#2`, … Each segment has its
   own listing (first bar) and delisting (last bar). Tickers are never merged (LUNA vs LUNA2,
   SHIB vs 1000SHIB). Contract multipliers are already embedded in the quoted price of the
   `1000XXX` tickers; notional = qty × price uses that price consistently.
5. Eligibility at hour H (all causal): ≥ 7 days since first bar; ≥ 95 % 1m coverage over the
   trailing 24 h; previous hour complete; trailing-24h quote volume ≥ 5 M USDT; H < delisting − 48 h.
   Evolution mode clamps delisting knowledge at the evolution boundary (a contract delisted in
   2025 is simply "alive" through 2024).
6. Missing bars are never forward-filled for prices. Resampled bars with missing 1m bars are marked
   incomplete (`n1m < expected`) and an incomplete bar cannot generate a signal.
7. Known limitation: delisting announcement time is approximated by (last bar − 48 h) block;
   Binance usually announces ≥ 7 days ahead, so this is realistic-to-conservative for entries.
