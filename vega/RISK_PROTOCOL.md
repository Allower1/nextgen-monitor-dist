# RISK_PROTOCOL.md

Frozen numbers: see VEGA_PROTOCOL.md §5–§7 (and `vega_core/kernel.py`).

Conservative crisis assumptions (Binance does not publish a convenient history of leverage
reductions, reduce-only switches and halts):
1. Slippage multiplier up to 4x when trailing-1h realised vol is ≥ 2x its 7-day median.
2. Per-position leverage fixed at 5x isolated; liquidation modelled on bar extremes (high/low),
   whole margin lost + 1 % liquidation fee.
3. Missing bars while holding a position = trading halt: exit at first available open with 2x
   slippage; no entries on a bar whose 1m coverage is incomplete.
4. Last 48 h before delisting: no new entries; open positions closed at the 48 h mark.
5. Funding: charged at each archive funding timestamp; missing funding record → conservative
   rate max(|last|, 0.01 %) against the position.
6. Stop/TP both touched in one bar → stop. Stop gapped → fill at bar open (worse).
7. Historical tick/step/min-notional unknown → current exchangeInfo for live contracts,
   conservative defaults (1 USDT notional step, 5/100 USDT min notional) for delisted.
8. Portfolio: gross ≤ 3x, position ≤ 0.30x, symbol ≤ 0.30x, ≤ 12 positions,
   |net BTC-beta| ≤ 1.5x, max hold 12 h.

Micro-live canary (document only, NOT to be run without separate explicit permission) will be
written in `MICRO_LIVE_CANARY_PROTOCOL.md` after paper.
