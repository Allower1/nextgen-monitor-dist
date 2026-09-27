"""Synthetic zone panel for engine tests (same interface as universe.Panel)."""
import numpy as np

from vega_core import kernel as K


class SynthPanel:
    def __init__(self, N=3, T=12 * 48, price=100.0, names=None, t_start=K.DEV_START, qv24h=5e8, rv=0.001):
        self.N, self.T, self.H = N, T, T // 12 + 1
        self.t_start = t_start
        self.names = names or [f"S{i}USDT" for i in range(N)]
        L = T
        self.r_off = np.arange(N + 1, dtype=np.int64) * L
        self.r_start = np.zeros(N, np.int64)
        tot = N * L
        f = lambda v: np.full(tot, v, np.float32)
        self.r = {"open": f(price), "high": f(price), "low": f(price), "close": f(price),
                  "exec_open": f(price), "exec_open3": f(price), "h_after": f(price), "l_after": f(price),
                  "rv60": f(rv), "qv24h": f(qv24h), "n1m": f(5)}
        self.h = {"rv_ratio": np.ones((self.H, N), np.float32), "beta7d": np.ones((self.H, N), np.float32)}
        self.f_time = np.zeros(0, np.int64)
        self.f_rate = np.zeros(0)
        self.f_off = np.zeros(N + 1, np.int64)
        self.known_delist = np.full(N, 2 ** 61, np.int64)

    def row(self, i, t):
        return int(self.r_off[i] + t)

    def set_bar(self, i, t, **kw):
        for k, v in kw.items():
            self.r[k][self.row(i, t)] = v

    def set_funding(self, events):
        """events: list of (inst, time_ms, rate)."""
        ev = sorted(events)
        self.f_time = np.array([e[1] for e in ev], np.int64)
        self.f_rate = np.array([e[2] for e in ev], np.float64)
        cnt = np.bincount([e[0] for e in ev], minlength=self.N)
        self.f_off = np.concatenate([[0], np.cumsum(cnt)]).astype(np.int64)

    def blank_signals(self, S=None):
        S = S or self.N
        sel = np.tile(np.arange(S, dtype=np.int32), (self.H, 1))
        z = lambda dt: np.zeros((self.T, S), dt)
        return sel, z(np.int8), z(np.float32), z(np.float32), z(np.float32)
