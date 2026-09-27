"""ridge_wf must not use labels that reach into (or past) the purge window of the predicted block."""
import numpy as np

from vega_core.strategies import families as FAM
from tests.synth import SynthPanel


class FakeCtx:
    def __init__(self, panel, feats):
        self.panel = panel
        self.T = panel.T
        S = panel.N
        self.cur = {"sel_inst": np.tile(np.arange(S, dtype=np.int32), (panel.H, 1))}
        self._f = feats

    def gather(self, name):
        return self._f[name]


def _mk(seed=0, bump_from=None):
    T = 288 * 400
    p = SynthPanel(N=2, T=T)
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, (T, 2)), 0))
    if bump_from is not None:
        c[bump_from:] *= np.exp(np.cumsum(rng.normal(0.01, 0.01, (T - bump_from, 2)), 0))
    for i in range(2):
        a, b = p.r_off[i], p.r_off[i + 1]
        p.r["close"][a:b] = c[:, i]
        p.r["exec_open"][a:b] = c[:, i]
    feats = {k: np.random.default_rng(1).normal(size=(T, 2)).astype(np.float32) for k in FAM.RIDGE_FEATS}
    feats["vol48"] = np.full((T, 2), 0.002, np.float32)
    return FakeCtx(p, feats)


def test_ridge_no_future_labels():
    spec = {"params": {**{f"f_{k}": k in ("z3", "z12", "bbz") for k in FAM.RIDGE_FEATS}, "h": 12, "lam": 1.0, "th": 1.0}}
    ctx = _mk()
    bs = FAM.block_starts(ctx)
    assert len(bs) >= 3
    s0 = bs[1]
    pred1, _ = FAM.ridge_predict(spec, ctx)
    # change every price from (s0 - purge) onwards: predictions for block 1 must not change
    ctx2 = _mk(bump_from=s0 - FAM.PURGE_STEPS)
    pred2, _ = FAM.ridge_predict(spec, ctx2)
    np.testing.assert_array_equal(pred1[s0:bs[2]], pred2[s0:bs[2]])


def test_ridge_negative_control_training_data_matters():
    spec = {"params": {**{f"f_{k}": k in ("z3", "z12", "bbz") for k in FAM.RIDGE_FEATS}, "h": 12, "lam": 1.0, "th": 1.0}}
    ctx = _mk()
    bs = FAM.block_starts(ctx)
    pred1, _ = FAM.ridge_predict(spec, ctx)
    ctx2 = _mk(bump_from=bs[1] // 2)
    pred2, _ = FAM.ridge_predict(spec, ctx2)
    assert not np.array_equal(pred1[bs[1]:bs[2]], pred2[bs[1]:bs[2]])
