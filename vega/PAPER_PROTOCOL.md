# PAPER_PROTOCOL.md

Only after a finalist passes the holdout. Public Binance market data only (no keys).
Same frozen cost/execution model as the backtest; in addition, record real best bid/ask at each
signal (bookTicker) to measure realised vs modelled slippage.
Each finalist (≤ 3) runs 7 days in parallel. Checkpoints: 24 h (~20 trades, smoke test),
72 h (~60 trades), 7 d (~140 trades).
Kill rules: DD > 15 %; 0 trades in any 24 h; > 60 trades in 24 h; 3 crashes in 24 h.
Paper is NOT proof of edge: ~140 trades can falsify but not prove a small edge.
