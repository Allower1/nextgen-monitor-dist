"""Protocol freeze: kernel constants must equal the frozen protocol and its hash the manifest."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from vega_core import kernel as K

ROOT = Path(__file__).resolve().parents[1]


def test_frozen_numbers():
    assert K.START_CAPITAL == 10_000.0
    assert K.MAX_GROSS_LEVERAGE == 3.0 and K.MAX_POSITION_FRAC == 0.30 and K.MAX_POSITIONS == 12
    assert K.TAKER_FEE == 0.0005
    assert K.TOP_N == 20
    assert K.EMBARGO_MS == 7 * K.DAY_MS == K.MAX_LOOKBACK_MS
    assert K.MAX_HOLD_MS == 12 * K.HOUR_MS
    assert K.COST_STRESS_LEVELS == (1.0, 1.5, 2.0, 3.0)
    g = K.GATES
    assert g.g2_trades_per_day == (10.0, 40.0) and g.g3_min_positive_years == 4
    assert g.g4_max_symbol_share == 0.25 and g.g5_max_dd_1x == 0.25 and g.g7_min_dsr == 0.95
    assert g.holdout_max_finalists == 3 and g.inner_max_sessions == 3


def test_zone_dates():
    import datetime as dt
    f = lambda ms: dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")
    assert f(K.EVOLUTION_END) == "2025-01-01" and f(K.EVOLUTION_TRADE_END) == "2024-12-24"
    assert f(K.HOLDOUT_START) == "2026-01-01" and f(K.HOLDOUT_END) == "2026-09-20"


def test_kernel_hash_matches_manifest():
    man = json.loads((ROOT / "PROTOCOL_MANIFEST.json").read_text())
    h = hashlib.sha256((ROOT / "vega_core" / "kernel.py").read_bytes()).hexdigest()
    assert man["files"]["vega_core/kernel.py"] == h, "SAFETY KERNEL modified after freeze"
    for rel, hh in man["files"].items():
        assert hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() == hh, rel


def test_slippage_monotone():
    s_small = K.slippage_frac(1000, 1e7, 0.001, 1.0)
    s_big = K.slippage_frac(1000, 2e9, 0.001, 1.0)
    assert s_small > s_big > 0
    assert K.slippage_frac(1000, 1e8, 0.001, 8.0) == pytest.approx(4 * K.slippage_frac(1000, 1e8, 0.001, 1.0))
    assert K.slippage_frac(1000, 1e8, 0.001, 1.0, stress=2.0) == pytest.approx(2 * K.slippage_frac(1000, 1e8, 0.001, 1.0))
    # BTC-like round trip ≈ 0.12-0.15 %
    rt = 2 * (K.TAKER_FEE + float(K.slippage_frac(3000, 5e9, 0.0006, 1.0)))
    assert 0.0011 < rt < 0.0016


def test_funding_sign():
    assert K.funding_cash(+1, 1000, 0.0001) == pytest.approx(-0.1)
    assert K.funding_cash(-1, 1000, 0.0001) == pytest.approx(0.1)


def test_liq_price():
    assert K.liquidation_price(1, 100.0, "XUSDT") == pytest.approx(81.0)
    assert K.liquidation_price(-1, 100.0, "BTCUSDT") == pytest.approx(119.5)


def test_holdout_lock(monkeypatch):
    monkeypatch.delenv("VEGA_TEST_FAKE_UNLOCK", raising=False)
    g = K.ZoneGuard("evolution")
    g.check(K.EVOLUTION_END)
    with pytest.raises(K.LeakageError):
        g.check(K.EVOLUTION_END + 1)
    with pytest.raises(K.LeakageError):
        g.check_month("2025-01")
    gi = K.ZoneGuard("inner_validation")
    gi.check_month("2025-12")
    with pytest.raises(K.LeakageError):
        gi.check_month("2026-01")
    with pytest.raises(K.LeakageError):
        K.ZoneGuard("holdout")
    assert not K.archive_month_allowed("2026-01") and K.archive_month_allowed("2025-12")
