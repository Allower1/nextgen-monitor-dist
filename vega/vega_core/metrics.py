"""Performance metrics, multiple-testing statistics (DSR, PBO/CSCV), bootstrap."""
from __future__ import annotations

import itertools
import math

import numpy as np
from scipy import stats

from . import kernel as K

STEPS_PER_DAY = 288


def daily_returns(equity: np.ndarray, start_capital: float = K.START_CAPITAL) -> np.ndarray:
    n = len(equity) // STEPS_PER_DAY
    e = equity[: n * STEPS_PER_DAY].reshape(n, STEPS_PER_DAY)[:, -1]
    prev = np.concatenate([[start_capital], e[:-1]])
    return e / prev - 1.0


def sharpe(r: np.ndarray, ann: float = 365.0) -> float:
    r = r[np.isfinite(r)]
    if len(r) < 2 or r.std(ddof=1) == 0:
        return 0.0
    return float(r.mean() / r.std(ddof=1) * math.sqrt(ann))


def sortino(r: np.ndarray, ann: float = 365.0) -> float:
    d = r[r < 0]
    if len(d) < 2:
        return 0.0
    dd = math.sqrt((d ** 2).mean())
    return float(r.mean() / dd * math.sqrt(ann)) if dd > 0 else 0.0


def max_drawdown(equity: np.ndarray) -> float:
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(np.maximum(equity, 1e-12))
    return float(np.max(1.0 - equity / peak))


def year_of_days(t0_ms: int, n_days: int) -> np.ndarray:
    d = np.datetime64(int(t0_ms), "ms").astype("datetime64[D]") + np.arange(n_days)
    return d.astype("datetime64[Y]").astype(int) + 1970


def half_year_blocks(t0_ms: int, n_days: int) -> np.ndarray:
    d = np.datetime64(int(t0_ms), "ms").astype("datetime64[D]") + np.arange(n_days)
    y = d.astype("datetime64[Y]").astype(int) + 1970
    m = d.astype("datetime64[M]").astype(int) % 12
    return (y - 2020) * 2 + (m >= 6)


def summarize(res, names: list[str], active_days: np.ndarray | None = None, trade_start_day: int = 7) -> dict:
    """res: backtest.Result. active_days: bool mask of days with an eligible universe."""
    tr = res.trades
    eq = res.equity
    dr = daily_returns(eq)
    nd = len(dr)
    if active_days is None:
        active_days = np.zeros(nd, bool)
        active_days[trade_start_day:] = True
    active_days = active_days[:nd]
    n = len(tr["pnl"])
    exit_day = (tr["t_exit"] // STEPS_PER_DAY).astype(np.int64)
    tpd = np.bincount(exit_day[exit_day < nd], minlength=nd)[active_days] if n else np.zeros(active_days.sum())
    pnl = tr["pnl"]
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    years = year_of_days(res.t0_ms, nd)
    blocks = half_year_blocks(res.t0_ms, nd)
    yr = {}
    for y in np.unique(years[active_days]):
        m = (years == y) & active_days
        yr[int(y)] = float(np.prod(1 + dr[m]) - 1)
    bl = {}
    for b in np.unique(blocks[active_days]):
        m = (blocks == b) & active_days
        bl[int(b)] = {"ret": float(np.prod(1 + dr[m]) - 1), "sharpe": sharpe(dr[m])}
    # instrument shares of total net pnl
    by_inst = {}
    if n:
        s = np.bincount(tr["inst"], weights=pnl)
        for i in np.nonzero(s)[0]:
            by_inst[names[i]] = float(s[i])
    total = float(pnl.sum()) if n else 0.0
    shares = sorted((v / total for v in by_inst.values()), reverse=True) if total > 0 else [1.0]
    notional = tr["notional"] if n else np.zeros(1)
    ra = dr[active_days]
    out = {
        "n_trades": int(n),
        "trades_per_day_mean": float(tpd.mean()) if len(tpd) else 0.0,
        "trades_per_day_median": float(np.median(tpd)) if len(tpd) else 0.0,
        "net_pnl": total,
        "total_return": float(eq[-1] / K.START_CAPITAL - 1.0),
        "expectancy_usdt": float(pnl.mean()) if n else 0.0,
        "expectancy_bps": float((pnl / notional).mean() * 1e4) if n else 0.0,
        "gross_expectancy_bps": float(((pnl + tr["fee"] + tr["slip"] - tr["funding"]) / notional).mean() * 1e4) if n else 0.0,
        "fees": float(tr["fee"].sum()) if n else 0.0,
        "slippage": float(tr["slip"].sum()) if n else 0.0,
        "funding": float(tr["funding"].sum()) if n else 0.0,
        "sharpe": sharpe(ra), "sortino": sortino(ra), "max_dd": max_drawdown(eq),
        "profit_factor": float(wins.sum() / -losses.sum()) if n and losses.sum() < 0 else float("inf") if n else 0.0,
        "win_rate": float(len(wins) / n) if n else 0.0,
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "payoff": float(wins.mean() / -losses.mean()) if len(wins) and len(losses) and losses.mean() < 0 else 0.0,
        "tail_loss_cvar5_daily": float(np.sort(ra)[: max(1, len(ra) // 20)].mean()) if len(ra) else 0.0,
        "turnover_notional": float(notional.sum() * 2) if n else 0.0,
        "long_trades": int((tr["side"] > 0).sum()) if n else 0,
        "short_trades": int((tr["side"] < 0).sum()) if n else 0,
        "long_pnl": float(pnl[tr["side"] > 0].sum()) if n else 0.0,
        "short_pnl": float(pnl[tr["side"] < 0].sum()) if n else 0.0,
        "years": yr, "blocks": bl,
        "top1_share": float(shares[0]) if shares else 0.0,
        "top3_share": float(sum(shares[:3])) if shares else 0.0,
        "n_instruments_traded": len(by_inst),
        "reasons": {r: int((tr["reason"] == k).sum()) for k, r in enumerate(["time", "stop", "tp", "liq", "signal", "delist_or_zone", "halt"])} if n else {},
        "skewness": float(stats.skew(ra)) if len(ra) > 3 else 0.0,
        "kurtosis": float(stats.kurtosis(ra, fisher=False)) if len(ra) > 3 else 3.0,
        "n_days": int(active_days.sum()),
        "skipped_orders": int(res.skipped),
    }
    return out


def top_instruments(res, names, k=3):
    tr = res.trades
    s = np.bincount(tr["inst"], weights=tr["pnl"], minlength=len(names))
    return [int(i) for i in np.argsort(-s)[:k]]


# ------------------------------------------------------------------ multiple testing
def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """E[max SR] among n_trials iid N(0, var_sr) (Bailey & López de Prado 2014)."""
    if n_trials <= 1:
        return 0.0
    g = 0.5772156649
    z1 = stats.norm.ppf(1 - 1.0 / n_trials)
    z2 = stats.norm.ppf(1 - 1.0 / (n_trials * math.e))
    return math.sqrt(max(var_sr, 0.0)) * ((1 - g) * z1 + g * z2)


def deflated_sharpe(sr_daily: float, n_obs: int, skew: float, kurt: float, n_trials: int, var_sr_daily: float) -> float:
    """Probability that the true SR > E[max SR under the null] (daily, non-annualised units)."""
    sr0 = expected_max_sharpe(n_trials, var_sr_daily)
    den = 1 - skew * sr_daily + (kurt - 1) / 4.0 * sr_daily ** 2
    if den <= 0 or n_obs < 3:
        return 0.0
    z = (sr_daily - sr0) * math.sqrt(n_obs - 1) / math.sqrt(den)
    return float(stats.norm.cdf(z))


def pbo_cscv(M: np.ndarray) -> float:
    """Probability of backtest overfitting. M: [n_blocks, n_candidates] block performance."""
    nb, nc = M.shape
    if nc < 2 or nb < 4:
        return 1.0
    half = nb // 2
    logits = []
    for IS in itertools.combinations(range(nb), half):
        OS = [b for b in range(nb) if b not in IS]
        is_perf = M[list(IS)].mean(0)
        os_perf = M[OS].mean(0)
        best = int(np.argmax(is_perf))
        rank = (stats.rankdata(os_perf)[best]) / (nc + 1)
        logits.append(math.log(rank / (1 - rank)))
    return float(np.mean(np.array(logits) <= 0))


def stationary_bootstrap_sharpe(r: np.ndarray, n_boot: int = 1000, block: int = 10, seed: int = 0) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(r)
    if n < 20:
        return 0.0, 0.0
    out = np.empty(n_boot)
    p = 1.0 / block
    for b in range(n_boot):
        idx = np.empty(n, np.int64)
        idx[0] = rng.integers(n)
        jumps = rng.random(n) < p
        starts = rng.integers(n, size=n)
        for k in range(1, n):
            idx[k] = starts[k] if jumps[k] else (idx[k - 1] + 1) % n
        out[b] = sharpe(r[idx])
    return float(np.percentile(out, 5)), float(np.percentile(out, 50))
