# DECISIONS.md

D-001 (Phase A) Location. The requested path `/home/ubuntu/vega` is on a shared server that is not
this host. This session runs in an ephemeral cloud container where only git pushes persist.
VEGA therefore lives at `vega/` on branch `claude/vega-intraday-evolution-gyfsac` of the only
repository available to the session; `/home/ubuntu/vega` is a symlink to it. VEGA shares no code,
config or data with the host repo's iOS files. On the shared server: `git clone` + `ln -s`.

D-002 Protected projects (Nova, Nova Evo, ADAM, Luna, bot-nextgen, M30/M32 collectors) do not
exist on this host → nothing to protect locally; the path deny-list is still enforced in
`scripts/run_bg.sh` and documented.

D-003 Fee = 0.050 % taker per side for the whole period (VIP0, no BNB). Maker not used (v1
market orders only → no unfilled-limit modelling needed). Simpler and conservative.

D-004 Slippage: volatility + liquidity + square-root impact proxy with crisis multiplier (formula
in VEGA_PROTOCOL.md §6). Historical spread data does not exist for 2020–2025 1m.

D-005 Holdout blindness at the listing level: archive keys dated > 2025-12 are discarded inside
the listing parser before they are stored or printed. (The S3 listing API returns them in the
same XML page; they are filtered in memory.)

D-006 Validation: 2020–2024 evolution with 10 half-year blocks (fitness + CSCV/PBO), 7-day
embargo at the end of each zone (trading stops 2024-12-24 / 2025-12-24), 2025 inner validation
(≤ 3 sessions × ≤ 10 candidates), 2026 holdout once, after UNLOCK.

D-007 Execution granularity: decisions on closed 5m bars; fills at the open of the 1m bar at
T+60 s; intrabar stop/TP from 5m high/low (entry bar: only 1m bars after the fill). Chosen over a
full 1m event loop for speed; conservative (stop-first rule).

D-008 Isolated 5x margin per position for liquidation modelling (simpler than cross-margin,
conservative: a liquidation loses the full isolated margin + 1 % fee).

D-009 Open interest / long-short metrics (archive only from ~late 2021) and liquidation data are
NOT used in v1 (partial-period features could reward "data appearance").

D-010 Background jobs: `setsid nohup nice -n 10 ionice -c3` (systemd user units are not usable in
this container). Jobs checkpoint to disk and resume; the container itself is ephemeral, so the
authoritative state is what is committed and pushed (code, ledger, manifests, summaries).
