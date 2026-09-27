# SCANNER_SPEC.md

Question answered: "WHERE IS THERE OPPORTUNITY NOW?"

Hourly metrics per instrument (computed from closed 1m bars only, `vega_core/universe.py`):
`qv1h, qv24h` (quote volume), `ret1h, ret4h, ret24h`, `rv1h` (std 1m log-ret, last 60 min),
`rv24h`, `range1h` ((H−L)/C), `trades1h`, `taker_buy_ratio1h`, `funding_last` (last settled rate),
`beta7d` (1h beta to BTC, 7 days).

Relative features (causal, no full-period statistics):
* time-series: value / trailing-7-day median of the same instrument (e.g. `rel_vol = qv1h / med7d(qv1h)`,
  `rv_ratio = rv1h / med7d(rv1h)`), and expanding-window percentiles capped at 7 days.
* cross-sectional: rank percentile among instruments eligible at the same hour.

MarketActivityScore (mutable composition, CandidateSpec.scanner):
`score = Σ w_k · xrank_k` over k ∈ {rv_ratio, rel_vol, |ret1h|, |ret4h|, range_exp, qv24h,
|funding|, accel}; weights evolve (non-negative, normalised); default weights equal on
{rv_ratio, rel_vol, |ret4h|, qv24h}.

Opportunity / Crisis Mode: an instrument is flagged ANOMALY when rv_ratio ≥ 3 or rel_vol ≥ 4 or
|ret1h| ≥ 4 × rv1h×sqrt(60) (thresholds mutable within [2, 6]). Flag adds a priority boost to the
score; it is NOT an entry signal. Entry still needs the strategy's own signal; exits/stops apply.
Flag decays automatically when the ratios fall back. In crisis the frozen slippage multiplier
(kernel.crisis_mult) makes execution up to 4x worse. Open interest / long-short ratio exist only
from late 2021 in the archive → NOT used in v1 (would create "data-appearance" advantage).
Liquidations: not used. Spread: modelled via the slippage proxy, never invented.

TOP-20: the 20 highest-scoring eligible instruments at hour H (tie-break instrument id); held
fixed for the hour [H, H+1h). Positions opened earlier are managed even if the symbol drops out
of the TOP-20 (no new entries).

Frozen POOL (DECISIONS D-013): each hour the universe layer forms a pool of ≤ 50 eligible
instruments (top-40 by trailing-24h quote volume + ≤ 10 anomaly instruments by xs-rank of
rv_ratio/rel_vol). The candidate's scanner ranks only inside this pool.
