"""VEGA SAFETY KERNEL.

Frozen at tag ``vega-protocol-freeze-v1``. Every constant here mirrors VEGA_PROTOCOL.md.
Nothing in this module may be mutated by the evolution engine: candidates receive read-only
access through the functions below. The SHA256 of this file is recorded in
PROTOCOL_MANIFEST.json and checked by ``tests/test_kernel_frozen.py``.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

KERNEL_VERSION = "1.0.0"

# --------------------------------------------------------------------------- time (ms, UTC)
MIN_MS = 60_000
HOUR_MS = 3_600_000
DAY_MS = 86_400_000


def _utc_ms(y: int, m: int, d: int) -> int:
    import datetime as _dt
    return int(_dt.datetime(y, m, d, tzinfo=_dt.timezone.utc).timestamp() * 1000)


DEV_START = _utc_ms(2020, 1, 1)
EVOLUTION_END = _utc_ms(2025, 1, 1)            # evolution may read data < this
EVOLUTION_TRADE_END = _utc_ms(2024, 12, 24)    # no entries at/after this in evolution
EVOLUTION_FORCE_CLOSE = EVOLUTION_TRADE_END + 12 * HOUR_MS
INNER_START = _utc_ms(2025, 1, 1)
INNER_WARMUP_START = _utc_ms(2024, 12, 24)
INNER_END = _utc_ms(2026, 1, 1)                # inner mode may read data < this
INNER_TRADE_END = _utc_ms(2025, 12, 24)
HOLDOUT_START = _utc_ms(2026, 1, 1)
HOLDOUT_WARMUP_START = _utc_ms(2025, 12, 24)
HOLDOUT_END = _utc_ms(2026, 9, 20)
ARCHIVE_MAX_MONTH = "2025-12"                  # archive keys after this month are dropped unseen

EMBARGO_MS = 7 * DAY_MS
MAX_LOOKBACK_MS = 7 * DAY_MS
MAX_HOLD_MS = 12 * HOUR_MS
LATENCY_MS = 60_000

# --------------------------------------------------------------------------- universe
TOP_N = 20
MIN_HISTORY_MS = 7 * DAY_MS
MIN_COVERAGE_24H = 0.95
PREFILTER_MIN_QV24H = 5_000_000.0
DELIST_NO_ENTRY_MS = 48 * HOUR_MS
SEGMENT_GAP_MS = 7 * DAY_MS
SEGMENT_JUMP_GAP_MS = 1 * DAY_MS
SEGMENT_JUMP_RATIO = 0.70

# --------------------------------------------------------------------------- capital / risk
START_CAPITAL = 10_000.0
MAX_GROSS_LEVERAGE = 3.0
MAX_POSITION_FRAC = 0.30
MAX_SYMBOL_FRAC = 0.30
MAX_POSITIONS = 12
MAX_NET_BETA = 1.5
BETA_CLIP = (0.0, 3.0)
POSITION_LEVERAGE = 5.0
MMR_MAJOR = 0.005
MMR_DEFAULT = 0.010
MAJORS = ("BTCUSDT", "ETHUSDT")
LIQUIDATION_FEE = 0.010
MISSING_FUNDING_MIN_RATE = 0.0001
MIN_NOTIONAL_DEFAULT = 5.0
MIN_NOTIONAL_MAJOR = 100.0

# --------------------------------------------------------------------------- costs
TAKER_FEE = 0.0005
MAKER_FEE = 0.0002          # NOT used by v1 (market orders only)
SLIP_RV_COEF = 0.10
SLIP_IMPACT_COEF = 1.0      # × σ_day × sqrt(Q/ADV)
CRISIS_MULT_MAX = 4.0
GAP_EXIT_SLIP_MULT = 2.0
COST_STRESS_LEVELS = (1.0, 1.5, 2.0, 3.0)


def slip_floor_bps(adv: np.ndarray | float) -> np.ndarray:
    adv = np.asarray(adv, dtype=np.float64)
    return np.where(adv >= 1e9, 1.0, np.where(adv >= 1e8, 2.0, np.where(adv >= 2e7, 4.0, 8.0)))


def crisis_mult(rv_ratio: np.ndarray | float) -> np.ndarray:
    r = np.nan_to_num(np.asarray(rv_ratio, dtype=np.float64), nan=1.0)
    return np.clip(r / 2.0, 1.0, CRISIS_MULT_MAX)


def slippage_frac(notional, adv, rv1m, rv_ratio, stress: float = 1.0) -> np.ndarray:
    """Adverse slippage per side as a FRACTION of price (frozen model).

    rv1m: std of 1m log returns (fraction) over trailing 60 min, closed data only.
    adv:  trailing-24h quote volume in USDT, closed data only.
    """
    notional = np.abs(np.asarray(notional, dtype=np.float64))
    adv = np.maximum(np.nan_to_num(np.asarray(adv, dtype=np.float64), nan=0.0), 1.0)
    rv = np.nan_to_num(np.asarray(rv1m, dtype=np.float64), nan=0.002)
    rv = np.maximum(rv, 0.0)
    sigma_day = rv * math.sqrt(1440.0)
    bps = slip_floor_bps(adv) + SLIP_RV_COEF * rv * 1e4 + 1e4 * SLIP_IMPACT_COEF * sigma_day * np.sqrt(notional / adv)
    return stress * crisis_mult(rv_ratio) * bps * 1e-4


def fee_frac(stress: float = 1.0) -> float:
    return stress * TAKER_FEE


def funding_cash(side: int, notional_at_funding: float, rate: float) -> float:
    """Cash flow to the account from one funding event. side=+1 long, -1 short.
    Long pays when rate > 0."""
    return -side * abs(notional_at_funding) * rate


def mmr_for(symbol: str) -> float:
    return MMR_MAJOR if symbol.split("#")[0] in MAJORS else MMR_DEFAULT


def liquidation_price(side: int, entry: float, symbol: str) -> float:
    """Isolated-margin liquidation price at POSITION_LEVERAGE."""
    m = 1.0 / POSITION_LEVERAGE - mmr_for(symbol)
    return entry * (1.0 - m) if side > 0 else entry * (1.0 + m)


# --------------------------------------------------------------------------- gates
@dataclass(frozen=True)
class Gates:
    g1_min_expectancy_2x: float = 0.0
    g2_trades_per_day: tuple = (10.0, 40.0)
    g3_min_positive_years: int = 4
    g4_max_symbol_share: float = 0.25
    g4_max_top3_share: float = 0.50
    g5_max_dd_1x: float = 0.25
    g5_max_dd_2x: float = 0.35
    g6_min_sharpe: float = 1.0
    g7_min_dsr: float = 0.95
    g8_n_perturb: int = 24
    g8_min_frac_positive: float = 0.80
    g8_min_sharpe_ratio: float = 0.5
    g9_max_pbo: float = 0.20
    g10_n_placebo: int = 100
    g10_percentile: float = 95.0
    g11_min_positive_blocks: int = 7
    g13_extra_latency_ms: int = 120_000
    g14_stress: float = 1.5
    g14_min_sharpe: float = 0.75
    g14_max_dd: float = 0.25
    g14_max_symbol_share: float = 0.35
    inner_max_sessions: int = 3
    inner_max_candidates: int = 10
    holdout_max_finalists: int = 3
    holdout_alpha: float = 0.05
    holdout_stress: float = 1.5
    holdout_max_dd: float = 0.30
    holdout_max_symbol_share: float = 0.35
    paper_kill_dd: float = 0.15
    paper_max_trades_24h: int = 60


GATES = Gates()

# --------------------------------------------------------------------------- zone guard


class LeakageError(RuntimeError):
    pass


VEGA_ROOT = Path(__file__).resolve().parents[1]
UNLOCK_FILE = VEGA_ROOT / "HOLDOUT_UNLOCKED"
MODES = ("evolution", "inner_validation", "holdout", "paper")


class ZoneGuard:
    """Enforces the data-zone boundaries. All data readers must call ``check``."""

    def __init__(self, mode: str):
        if mode not in MODES:
            raise ValueError(f"unknown mode {mode}")
        if mode in ("holdout", "paper") and not holdout_unlocked():
            raise LeakageError(f"mode={mode} requires explicit user UNLOCK ({UNLOCK_FILE})")
        self.mode = mode

    @property
    def max_ts(self) -> int:
        return {"evolution": EVOLUTION_END, "inner_validation": INNER_END,
                "holdout": HOLDOUT_END, "paper": 2**62}[self.mode]

    def check(self, end_ts_exclusive: int) -> None:
        if end_ts_exclusive > self.max_ts:
            raise LeakageError(
                f"mode={self.mode} may not read data >= {self.max_ts} (requested end {end_ts_exclusive})")

    def check_month(self, month: str) -> None:
        y, m = (int(x) for x in month.split("-"))
        self.check(_utc_ms(y, m, 1))  # month start must be allowed …
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        self.check(_utc_ms(ny, nm, 1))  # … and its end


def holdout_unlocked() -> bool:
    if os.environ.get("VEGA_TEST_FAKE_UNLOCK") == "1":
        return True
    return UNLOCK_FILE.exists() and "UNLOCK" in UNLOCK_FILE.read_text()


def archive_month_allowed(month: str) -> bool:
    """Archive keys dated after ARCHIVE_MAX_MONTH are dropped before they are stored/printed."""
    return month <= ARCHIVE_MAX_MONTH
