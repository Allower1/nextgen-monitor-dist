"""Evaluation context (zone-guarded panels + features) and candidate evaluation."""
from __future__ import annotations

import hashlib
import json
from collections import OrderedDict

import numpy as np

from . import backtest as B
from . import kernel as K
from . import metrics as MX
from .scanner import SCORE_METRICS, ScannerInputs, select_top
from .strategies import families as FAM
from .universe import Panel


def canonical(spec: dict) -> str:
    return json.dumps(spec, sort_keys=True, separators=(",", ":"), default=lambda o: o.item() if hasattr(o, "item") else str(o))


def spec_hash(spec: dict) -> str:
    return hashlib.sha256(canonical(spec).encode()).hexdigest()[:16]


def exchange_filters(names):
    """Current exchangeInfo step/minNotional for listed symbols; conservative defaults otherwise."""
    f = K.VEGA_ROOT / "data" / "meta" / "exchange_info.json"
    info = json.loads(f.read_text())["symbols"] if f.exists() else {}
    step = np.full(len(names), np.nan)
    mn = np.array([K.MIN_NOTIONAL_MAJOR if n.split("#")[0] in K.MAJORS else K.MIN_NOTIONAL_DEFAULT for n in names])
    for i, n in enumerate(names):
        s = info.get(n.split("#")[0])
        if s:
            step[i] = s["stepSize"]
            mn[i] = s["minNotional"]
    return step, mn


class Context:
    def __init__(self, zone: str = "dev", mode: str | None = None, cache_scanners: int = 2):
        self.zone = zone
        self.panel = Panel(zone, mode)
        p = self.panel
        self.T, self.H = p.T, p.H
        d = p.dir
        self.F = {k: np.load(d / f"F_{k}.npy", mmap_mode="r") for k in p.meta["features"]}
        self.market = {k: np.load(d / f"M_{k}.npy") for k in p.meta["market"]}
        self.si = ScannerInputs(p)
        self._cache: OrderedDict = OrderedDict()
        self.cache_scanners = cache_scanners
        # active days: days with at least one eligible instrument at some hour
        el = np.asarray(p.elig).any(1)
        nd = self.T // 288
        self.active_days = el[: nd * 24].reshape(nd, 24).any(1)
        self.cur = None
        self.step_size, self.min_notional = exchange_filters(p.names)

    # ------------------------------------------------------------------ scanner selection
    def use_scanner(self, sc: dict):
        key = canonical(sc)
        if key in self._cache:
            self._cache.move_to_end(key)
            self.cur = self._cache[key]
            return
        w = {k: sc.get(f"w_{k}", 0.0) for k in SCORE_METRICS}
        sel_slot, sel_inst, flag = select_top(self.si, w, sc["anomaly_boost"], sc["th_rv"], sc["th_vol"], sc["th_z"])
        hour_of_t = np.arange(self.T) // 12
        slot_t = sel_slot[hour_of_t]                      # [T, S]
        valid_t = slot_t >= 0
        flag_h = np.take_along_axis(flag, np.maximum(sel_slot, 0), axis=1) & (sel_slot >= 0)
        entry = {"sel_slot": sel_slot, "sel_inst": sel_inst, "slot_t": np.maximum(slot_t, 0), "valid_t": valid_t,
                 "flag_ts": flag_h[hour_of_t], "g": {}}
        self._cache[key] = entry
        while len(self._cache) > self.cache_scanners:
            self._cache.popitem(last=False)
        self.cur = entry

    @property
    def valid_ts(self):
        return self.cur["valid_t"]

    @property
    def flag_ts(self):
        return self.cur["flag_ts"]

    def gather(self, name: str) -> np.ndarray:
        g = self.cur["g"]
        if name not in g:
            F = np.asarray(self.F[name])
            x = np.take_along_axis(F, self.cur["slot_t"], axis=1)
            g[name] = np.where(self.cur["valid_t"], x, np.nan).astype(np.float32)
        return g[name]


def evaluate(spec: dict, ctx: Context, cost_stress: float = 1.0, latency_stress: bool = False,
             inst_mask: np.ndarray | None = None, sig_override=None):
    """Run one candidate. inst_mask: bool[N] of instruments allowed to trade (leave-out tests)."""
    ctx.use_scanner(spec["scanner"])
    sig, score, sl, tp = FAM.signals(spec, ctx) if sig_override is None else sig_override
    sel = ctx.cur["sel_inst"]
    if inst_mask is not None:
        sel = np.where((sel >= 0) & inst_mask[np.maximum(sel, 0)], sel, -1).astype(np.int32)
    e = spec["exec"]
    res = B.run(ctx.panel, sel, sig, score, sl, tp, size_frac=e["size_frac"], max_hold=e["max_hold"],
                cooldown=e["cooldown"], exit_on_opp=e["exit_on_opp"], cost_stress=cost_stress,
                latency_stress=latency_stress, step_size=ctx.step_size, min_notional=ctx.min_notional)
    summ = MX.summarize(res, ctx.panel.names, ctx.active_days)
    return res, summ, (sig, score, sl, tp)
