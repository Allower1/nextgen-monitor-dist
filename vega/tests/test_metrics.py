import numpy as np
import pytest

from vega_core import metrics as MX
from vega_core import gates as GT


def test_sharpe_dd():
    r = np.array([0.01, -0.01] * 50)
    assert MX.sharpe(r) == pytest.approx(0.0, abs=1e-9)
    eq = np.array([100, 120, 90, 130, 65.0])
    assert MX.max_drawdown(eq) == pytest.approx(0.5)


def test_dsr_penalises_many_trials():
    a = MX.deflated_sharpe(0.1, 1000, 0.0, 3.0, 1, 0.001)
    b = MX.deflated_sharpe(0.1, 1000, 0.0, 3.0, 10000, 0.001)
    assert a > 0.99 and b < a
    assert MX.expected_max_sharpe(1000, 0.0025) > MX.expected_max_sharpe(10, 0.0025)


def test_pbo_noise_vs_signal():
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 1, (10, 50))
    assert MX.pbo_cscv(noise) > 0.2
    sig = noise * 0.1
    sig[:, 0] += 3.0
    assert MX.pbo_cscv(sig) < 0.05


def test_placebo_preserves_counts():
    rng = np.random.default_rng(1)
    sig = np.zeros((1000, 4), np.int8)
    sig[rng.choice(1000, 30, replace=False), 1] = 1
    p = GT.placebo_signals(sig, rng)
    assert (p != 0).sum(0).tolist() == (sig != 0).sum(0).tolist()


def test_basic_gates_logic():
    s = {"years": {2020: .1, 2021: .1, 2022: -.1, 2023: .1, 2024: .1}, "blocks": {i: {"ret": 0.01, "sharpe": 1} for i in range(10)},
         "trades_per_day_median": 20, "trades_per_day_mean": 22, "net_pnl": 100, "top1_share": .1, "top3_share": .3,
         "max_dd": .1, "sharpe": 1.5, "expectancy_bps": 3.0}
    g = GT.basic_gates(s, dict(s, expectancy_bps=0.5, max_dd=0.2))
    assert GT.all_pass(g)
    g = GT.basic_gates(s, dict(s, expectancy_bps=-0.1))
    assert not g["G1_expectancy_2x"][0]
