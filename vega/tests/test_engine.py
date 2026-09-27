import numpy as np
import pytest

from vega_core import backtest as B
from vega_core import kernel as K
from tests.synth import SynthPanel

FAR = 2 ** 61


def _run(p, sel, sig, sc, sl, tp, **kw):
    kw.setdefault("size_frac", 0.1)
    kw.setdefault("max_hold", 10)
    kw.setdefault("trade_end_ms", FAR)
    kw.setdefault("force_close_ms", FAR)
    return B.run(p, sel, sig, sc, sl, tp, **kw)


def test_numba_slip_matches_kernel():
    for notional, adv, rv, rr, st in [(1000, 1e7, 0.001, 1.0, 1.0), (5e4, 3e9, 0.0004, 5.0, 2.0),
                                      (100, 5e5, 0.01, 0.5, 3.0), (3000, np.nan, np.nan, np.nan, 1.0)]:
        assert B._slip(notional, adv, rv, rr, st) == pytest.approx(float(K.slippage_frac(notional, adv, rv, rr, st)))


def test_next_bar_execution_and_costs():
    p = SynthPanel(N=1)
    p.set_bar(0, 11, exec_open=101.0)   # fill bar
    sel, sig, sc, sl, tp = p.blank_signals()
    sig[10, 0] = 1                       # signal on closed bar 10
    res = _run(p, sel, sig, sc, sl, tp, max_hold=3)
    tr = res.trades
    assert len(tr["pnl"]) == 1
    assert tr["t_entry"][0] == 11        # never the signal bar itself
    s = float(K.slippage_frac(1000, 5e8, 0.001, 1.0))
    assert tr["entry_px"][0] == pytest.approx(101.0 * (1 + s), rel=1e-6)
    assert tr["t_exit"][0] == 14 and tr["reason"][0] == 0   # time stop after 3 bars
    # fees: both sides taker on notional
    assert tr["fee"][0] == pytest.approx(K.TAKER_FEE * (tr["notional"][0] + abs(tr["notional"][0] / tr["entry_px"][0] * tr["exit_px"][0])), rel=1e-6)
    # equity conservation: final equity = start + sum pnl
    assert res.equity[-1] == pytest.approx(K.START_CAPITAL + tr["pnl"].sum(), rel=1e-9)


def test_stop_before_tp_same_bar():
    p = SynthPanel(N=1)
    p.set_bar(0, 12, high=110.0, low=90.0, open=100.0)
    sel, sig, sc, sl, tp = p.blank_signals()
    sig[10, 0] = 1
    sl[10, 0] = 0.05
    tp[10, 0] = 0.05
    res = _run(p, sel, sig, sc, sl, tp)
    assert res.trades["reason"][0] == 1          # stop
    assert res.trades["pnl"][0] < 0


def test_stop_gap_fills_at_open():
    p = SynthPanel(N=1)
    p.set_bar(0, 12, open=88.0, high=89.0, low=87.0, close=88.0)
    sel, sig, sc, sl, tp = p.blank_signals()
    sig[10, 0] = 1
    sl[10, 0] = 0.05
    res = _run(p, sel, sig, sc, sl, tp)
    assert res.trades["reason"][0] == 1
    assert res.trades["exit_px"][0] < 88.0        # worse than the 95 stop: gapped open minus slippage


def test_entry_bar_uses_after_fill_extremes():
    p = SynthPanel(N=1)
    p.set_bar(0, 11, high=120.0, low=80.0, h_after=100.5, l_after=99.5)
    sel, sig, sc, sl, tp = p.blank_signals()
    sig[10, 0] = 1
    sl[10, 0] = 0.05
    tp[10, 0] = 0.05
    res = _run(p, sel, sig, sc, sl, tp, max_hold=2)
    assert res.trades["reason"][0] == 0           # neither pre-fill extreme counts


def test_liquidation_without_stop():
    p = SynthPanel(N=1)
    p.set_bar(0, 12, low=70.0, close=75.0)
    sel, sig, sc, sl, tp = p.blank_signals()
    sig[10, 0] = 1
    res = _run(p, sel, sig, sc, sl, tp)
    tr = res.trades
    assert tr["reason"][0] == 3
    n = tr["notional"][0]
    # lost the whole isolated margin + liquidation fee (+ entry fee)
    assert tr["pnl"][0] == pytest.approx(-(n / K.POSITION_LEVERAGE + K.LIQUIDATION_FEE * n) - tr["fee"][0] + K.LIQUIDATION_FEE * n, rel=1e-6)


def test_funding_long_pays_short_receives():
    for side in (1, -1):
        p = SynthPanel(N=1)
        ev_t = K.DEV_START + 13 * 300000   # settles at close of bar 12
        p.set_funding([(0, ev_t, 0.001)])
        sel, sig, sc, sl, tp = p.blank_signals()
        sig[10, 0] = side
        res = _run(p, sel, sig, sc, sl, tp, max_hold=5)
        f = res.trades["funding"][0]
        qty = res.trades["notional"][0] / res.trades["entry_px"][0]
        assert f == pytest.approx(-side * qty * 100.0 * 0.001, rel=1e-6)


def test_missing_funding_charged_against_position():
    for side in (1, -1):
        p = SynthPanel(N=1)
        p.set_funding([(0, K.DEV_START + 2 * 300000, 0.0003), (0, K.DEV_START + 13 * 300000, np.nan)])
        sel, sig, sc, sl, tp = p.blank_signals()
        sig[10, 0] = side
        res = _run(p, sel, sig, sc, sl, tp, max_hold=5)
        assert res.trades["funding"][0] < 0


def test_position_caps_and_deterministic_order():
    p = SynthPanel(N=20)
    sel, sig, sc, sl, tp = p.blank_signals()
    sig[20, :] = 1
    sc[20, :] = np.arange(20)
    p.h["beta7d"][:] = 0.0      # isolate the position-count cap from the beta cap
    res = _run(p, sel, sig, sc, sl, tp, size_frac=0.2, max_hold=3)
    tr = res.trades
    # gross cap 3x at 0.2 → 15 but max positions 12 → 12 ... gross binds first at 15? min → 12
    assert len(tr["pnl"]) == min(K.MAX_POSITIONS, int(K.MAX_GROSS_LEVERAGE / 0.2))
    # highest scores chosen
    assert set(tr["inst"].tolist()) == set(range(20 - len(tr["pnl"]), 20))
    res2 = _run(p, sel, sig, sc, sl, tp, size_frac=0.2, max_hold=3)
    assert np.array_equal(res.equity, res2.equity)          # deterministic replay


def test_net_beta_cap():
    p = SynthPanel(N=20)
    sel, sig, sc, sl, tp = p.blank_signals()
    sig[10, :] = 1
    res = _run(p, sel, sig, sc, sl, tp, size_frac=0.2, max_hold=3)
    # beta 1 → net long ≤ 1.5x equity at 0.2 each → 7 positions
    assert len(res.trades["pnl"]) == 7


def test_gross_cap():
    p = SynthPanel(N=20)
    sel, sig, sc, sl, tp = p.blank_signals()
    sig[10, ::2] = 1
    sig[10, 1::2] = -1
    res = _run(p, sel, sig, sc, sl, tp, size_frac=0.3, max_hold=3)
    assert len(res.trades["pnl"]) == 10     # 10 × 0.3 = 3.0x gross


def test_delisting_blocks_entries_and_closes():
    p = SynthPanel(N=1, T=12 * 100)
    p.known_delist[:] = K.DEV_START + 60 * K.HOUR_MS
    sel, sig, sc, sl, tp = p.blank_signals()
    sig[12 * 13, 0] = 1        # 13h: allowed (delist-48h = 12h? no: 60-48 = 12h → blocked)
    sig[12 * 11, 0] = 1        # 11h → allowed, must be closed at 12h mark
    res = _run(p, sel, sig, sc, sl, tp, max_hold=100)
    tr = res.trades
    assert len(tr["pnl"]) == 1
    assert tr["reason"][0] == 5
    assert (K.DEV_START + int(tr["t_exit"][0]) * 300000) <= K.DEV_START + 12 * K.HOUR_MS + 600000


def test_zone_trade_end_and_force_close():
    p = SynthPanel(N=1, T=12 * 30)
    sel, sig, sc, sl, tp = p.blank_signals()
    sig[12 * 9, 0] = 1
    sig[12 * 11, 0] = 1
    res = _run(p, sel, sig, sc, sl, tp, max_hold=144, trade_end_ms=K.DEV_START + 10 * K.HOUR_MS,
               force_close_ms=K.DEV_START + 10 * K.HOUR_MS + 30 * 60000)
    tr = res.trades
    assert len(tr["pnl"]) == 1 and tr["reason"][0] == 5


def test_halt_missing_bars_exit_with_penalty():
    p = SynthPanel(N=1)
    for t in range(12, 20):
        p.set_bar(0, t, n1m=0, exec_open=np.nan, close=np.nan, high=np.nan, low=np.nan, open=np.nan)
    sel, sig, sc, sl, tp = p.blank_signals()
    sig[10, 0] = 1
    res = _run(p, sel, sig, sc, sl, tp, max_hold=50)
    tr = res.trades
    assert tr["reason"][0] == 6 and tr["t_exit"][0] == 20


def test_cost_stress_scales():
    p = SynthPanel(N=1)
    sel, sig, sc, sl, tp = p.blank_signals()
    sig[10, 0] = 1
    a = _run(p, sel, sig, sc, sl, tp, max_hold=3, cost_stress=1.0).trades
    b = _run(p, sel, sig, sc, sl, tp, max_hold=3, cost_stress=2.0).trades
    assert b["fee"][0] == pytest.approx(2 * a["fee"][0], rel=1e-3)
    assert b["pnl"][0] < a["pnl"][0] < 0     # flat price → pure cost


def test_short_side_pnl():
    p = SynthPanel(N=1)
    for t in range(12, 40):
        p.set_bar(0, t, exec_open=90.0, open=90.0, high=90.0, low=90.0, close=90.0, h_after=90.0, l_after=90.0)
    sel, sig, sc, sl, tp = p.blank_signals()
    sig[10, 0] = -1
    res = _run(p, sel, sig, sc, sl, tp, max_hold=3)
    assert res.trades["pnl"][0] > 0
