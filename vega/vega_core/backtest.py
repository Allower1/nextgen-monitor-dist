"""Portfolio backtest engine (numba). Frozen execution/accounting rules from the SAFETY KERNEL.

Time grid: 5m steps, step t = bar [t0 + 5m·t, t0 + 5m·(t+1)).
Order of events inside step t:
  A. fill orders decided at the close of bar t-1 at exec price = open of the 1m bar at
     bar-open + 60 s (latency) — or + 180 s under latency stress — adverse slippage + taker fee;
  B. intrabar risk for open positions on this bar's extremes (entry bar: only minutes after the
     fill): liquidation / STOP (stop wins over TP when both touched) / take-profit;
  C. funding events settling inside (bar open, bar close] for positions still open;
  D. mark-to-market at bar close;
  E. exit decisions (time stop, opposite signal, delisting 48 h, zone force-close, halt);
  F. new entry decisions from signals on the CLOSED bar t (fill in step t+1), deterministic order
     (score desc, instrument asc) under portfolio caps.
The candidate provides sig/score/sl/tp panels (T × S slots) and the hourly TOP-S selection.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numba as nb
import numpy as np

from . import kernel as K

REASONS = ["time", "stop", "tp", "liq", "signal", "delist_or_zone", "halt"]


@nb.njit(cache=True)
def _slip(notional, adv, rv, rv_ratio, stress):
    """Numba mirror of kernel.slippage_frac (equality asserted in tests)."""
    if not (adv == adv) or adv < 1.0:
        adv = 1.0
    if not (rv == rv):
        rv = 0.002
    if rv < 0.0:
        rv = 0.0
    if adv >= 1e9:
        fl = 1.0
    elif adv >= 1e8:
        fl = 2.0
    elif adv >= 2e7:
        fl = 4.0
    else:
        fl = 8.0
    sig_day = rv * math.sqrt(1440.0)
    bps = fl + 0.10 * rv * 1e4 + 1e4 * 1.0 * sig_day * math.sqrt(abs(notional) / adv)
    r = rv_ratio if rv_ratio == rv_ratio else 1.0
    m = r / 2.0
    if m < 1.0:
        m = 1.0
    if m > 4.0:
        m = 4.0
    return stress * m * bps * 1e-4


@nb.njit(cache=True)
def _row(i, t, r_off, r_start):
    k = t - r_start[i]
    if k < 0 or k >= r_off[i + 1] - r_off[i]:
        return -1
    return r_off[i] + k


@nb.njit(cache=True)
def run_engine(T, S, t0_ms, sel, sig, score, slf, tpf, size_frac, max_hold, cooldown, exit_on_opp,
               r_open, r_high, r_low, r_close, r_exec, r_exec3, r_h_after, r_l_after, r_rv60, r_qv24h, r_n1m,
               r_off, r_start, h_rv_ratio, h_beta, f_time, f_rate, f_off, known_delist,
               mmr, step_size, min_notional, trade_end_ms, force_close_ms,
               cost_stress, latency_stress, start_capital, max_gross, max_pos_frac, max_positions,
               max_net_beta, pos_lev, liq_fee, taker_fee, miss_fund_min, gap_slip_mult):
    STEP = 300000
    MAXP = 64
    N = r_start.shape[0]
    # open-position state (slot arrays)
    p_inst = np.full(MAXP, -1, np.int64)
    p_side = np.zeros(MAXP, np.int64)
    p_qty = np.zeros(MAXP)
    p_entry = np.zeros(MAXP)
    p_t = np.zeros(MAXP, np.int64)       # entry step
    p_sl = np.zeros(MAXP)
    p_tp = np.zeros(MAXP)
    p_fee = np.zeros(MAXP)
    p_slip = np.zeros(MAXP)
    p_fund = np.zeros(MAXP)
    p_notional0 = np.zeros(MAXP)
    p_last = np.zeros(MAXP)              # last known close (for MTM)
    p_exit_pending = np.zeros(MAXP, np.int64)   # 0 none, else reason+1
    p_halt = np.zeros(MAXP, np.bool_)
    p_beta = np.zeros(MAXP)
    # pending entries (decided at close of previous bar)
    q_inst = np.full(MAXP, -1, np.int64)
    q_side = np.zeros(MAXP, np.int64)
    q_notional = np.zeros(MAXP)
    q_sl = np.zeros(MAXP)
    q_tp = np.zeros(MAXP)
    q_beta = np.zeros(MAXP)
    nq = 0
    last_exit_t = np.full(N, -10**9, np.int64)
    f_ptr = f_off[:-1].copy()
    # outputs
    CAP = 2000000
    tr_i = np.zeros(CAP, np.int32); tr_side = np.zeros(CAP, np.int8)
    tr_te = np.zeros(CAP, np.int32); tr_tx = np.zeros(CAP, np.int32)
    tr_pe = np.zeros(CAP); tr_px = np.zeros(CAP); tr_not = np.zeros(CAP)
    tr_fee = np.zeros(CAP); tr_slip = np.zeros(CAP); tr_fund = np.zeros(CAP)
    tr_pnl = np.zeros(CAP); tr_reason = np.zeros(CAP, np.int8)
    ntr = 0
    equity_curve = np.zeros(T)
    gross_curve = np.zeros(T)
    cash = start_capital
    equity = start_capital
    skipped = 0
    for t in range(T):
        bar_open = t0_ms + t * STEP
        bar_close = bar_open + STEP
        h = t // 12
        # ---------------------------------------------------------------- A. fills
        for k in range(MAXP):
            if p_inst[k] < 0 or p_exit_pending[k] == 0:
                continue
            i = p_inst[k]
            r = _row(i, t, r_off, r_start)
            px = np.nan
            mult = 1.0
            if r >= 0:
                px = r_exec[r] if latency_stress == 0 else r_exec3[r]
                if not (px == px):
                    if r_n1m[r] > 0 and r_close[r] == r_close[r]:
                        px = r_close[r]
                        mult = gap_slip_mult
            if not (px == px):
                continue  # halted: keep pending until data returns
            if p_halt[k]:
                mult = gap_slip_mult
            rp = _row(i, t - 1, r_off, r_start)
            adv = r_qv24h[rp] if rp >= 0 else np.nan
            rv = r_rv60[rp] if rp >= 0 else np.nan
            hh = h - 1 if h > 0 else 0
            s = mult * _slip(p_qty[k] * px, adv, rv, h_rv_ratio[hh, i], cost_stress)
            fill = px * (1.0 - p_side[k] * s)
            fee = abs(p_qty[k] * fill) * taker_fee * cost_stress
            pnl = p_side[k] * p_qty[k] * (fill - p_entry[k])
            cash += pnl - fee
            p_fee[k] += fee
            p_slip[k] += abs(p_qty[k] * px) * s
            if ntr < CAP:
                tr_i[ntr] = i; tr_side[ntr] = p_side[k]; tr_te[ntr] = p_t[k]; tr_tx[ntr] = t
                tr_pe[ntr] = p_entry[k]; tr_px[ntr] = fill; tr_not[ntr] = p_notional0[k]
                tr_fee[ntr] = p_fee[k]; tr_slip[ntr] = p_slip[k]; tr_fund[ntr] = p_fund[k]
                tr_pnl[ntr] = p_side[k] * p_qty[k] * (fill - p_entry[k]) - p_fee[k] + p_fund[k]
                tr_reason[ntr] = p_exit_pending[k] - 1
                ntr += 1
            last_exit_t[i] = t
            p_inst[k] = -1
            p_exit_pending[k] = 0
            p_halt[k] = False
        for qk in range(nq):
            i = q_inst[qk]
            r = _row(i, t, r_off, r_start)
            if r < 0:
                skipped += 1
                continue
            px = r_exec[r] if latency_stress == 0 else r_exec3[r]
            if not (px == px):
                skipped += 1
                continue
            rp = _row(i, t - 1, r_off, r_start)
            adv = r_qv24h[rp] if rp >= 0 else np.nan
            rv = r_rv60[rp] if rp >= 0 else np.nan
            hh = h - 1 if h > 0 else 0
            notional = q_notional[qk]
            s = _slip(notional, adv, rv, h_rv_ratio[hh, i], cost_stress)
            fill = px * (1.0 + q_side[qk] * s)
            # quantity rounding (down) to exchange step, notional step ≥ 1 USDT
            stepn = step_size[i] * fill
            if not (stepn == stepn) or stepn < 1.0:
                stepn = 1.0
            notional = math.floor(notional / stepn) * stepn
            if notional < min_notional[i]:
                skipped += 1
                continue
            qty = notional / fill
            fee = notional * taker_fee * cost_stress
            cash -= fee
            k = 0
            while k < MAXP and p_inst[k] >= 0:
                k += 1
            if k == MAXP:
                skipped += 1
                continue
            p_inst[k] = i; p_side[k] = q_side[qk]; p_qty[k] = qty; p_entry[k] = fill; p_t[k] = t
            p_sl[k] = q_sl[qk]; p_tp[k] = q_tp[qk]; p_fee[k] = fee; p_slip[k] = notional * s
            p_fund[k] = 0.0; p_notional0[k] = notional; p_last[k] = fill; p_exit_pending[k] = 0
            p_halt[k] = False; p_beta[k] = q_beta[qk]
        nq = 0
        # ---------------------------------------------------------------- B. intrabar risk
        for k in range(MAXP):
            if p_inst[k] < 0:
                continue
            i = p_inst[k]
            r = _row(i, t, r_off, r_start)
            if r < 0 or r_n1m[r] == 0:
                p_halt[k] = True
                if p_exit_pending[k] == 0:
                    p_exit_pending[k] = 7  # halt → exit at first available price
                continue
            if r_n1m[r] < 5:
                p_halt[k] = True
            entered_now = p_t[k] == t
            tp_ok = True
            if entered_now:
                hi = r_h_after[r]; lo = r_l_after[r]; op = np.nan
                if latency_stress != 0:
                    tp_ok = False  # conservative: no TP on the entry bar under latency stress
            else:
                hi = r_high[r]; lo = r_low[r]; op = r_open[r]
            side = p_side[k]
            liq = p_entry[k] * (1.0 - side * (1.0 / pos_lev - mmr[i]))
            stop = p_entry[k] * (1.0 - side * p_sl[k]) if p_sl[k] > 0 else np.nan
            tp = p_entry[k] * (1.0 + side * p_tp[k]) if p_tp[k] > 0 else np.nan
            adverse = lo if side > 0 else hi
            favor = hi if side > 0 else lo
            if not tp_ok:
                favor = np.nan
            exit_px = np.nan
            reason = -1
            if stop == stop and adverse == adverse and side * (adverse - stop) <= 0:
                exit_px = stop
                if op == op and side * (op - stop) < 0:
                    exit_px = op  # gapped through the stop
                reason = 1
                if side * (exit_px - liq) <= 0:
                    reason = 3
            elif adverse == adverse and side * (adverse - liq) <= 0:
                reason = 3
            elif tp == tp and favor == favor and side * (favor - tp) >= 0:
                exit_px = tp
                reason = 2
            if reason == 3:
                notional = p_qty[k] * p_entry[k]
                loss = notional / pos_lev + liq_fee * notional
                cash += -loss
                if ntr < CAP:
                    tr_i[ntr] = i; tr_side[ntr] = side; tr_te[ntr] = p_t[k]; tr_tx[ntr] = t
                    tr_pe[ntr] = p_entry[k]; tr_px[ntr] = liq; tr_not[ntr] = p_notional0[k]
                    tr_fee[ntr] = p_fee[k] + liq_fee * notional; tr_slip[ntr] = p_slip[k]
                    tr_fund[ntr] = p_fund[k]; tr_pnl[ntr] = -loss - p_fee[k] + p_fund[k]
                    tr_reason[ntr] = 3
                    ntr += 1
                last_exit_t[i] = t
                p_inst[k] = -1; p_exit_pending[k] = 0
                continue
            if reason > 0:
                rp = _row(i, t - 1, r_off, r_start)
                adv = r_qv24h[rp] if rp >= 0 else np.nan
                rv = r_rv60[rp] if rp >= 0 else np.nan
                hh = h - 1 if h > 0 else 0
                s = _slip(p_qty[k] * exit_px, adv, rv, h_rv_ratio[hh, i], cost_stress)
                fill = exit_px * (1.0 - side * s)
                fee = abs(p_qty[k] * fill) * taker_fee * cost_stress
                cash += side * p_qty[k] * (fill - p_entry[k]) - fee
                p_fee[k] += fee
                p_slip[k] += abs(p_qty[k] * exit_px) * s
                if ntr < CAP:
                    tr_i[ntr] = i; tr_side[ntr] = side; tr_te[ntr] = p_t[k]; tr_tx[ntr] = t
                    tr_pe[ntr] = p_entry[k]; tr_px[ntr] = fill; tr_not[ntr] = p_notional0[k]
                    tr_fee[ntr] = p_fee[k]; tr_slip[ntr] = p_slip[k]; tr_fund[ntr] = p_fund[k]
                    tr_pnl[ntr] = side * p_qty[k] * (fill - p_entry[k]) - p_fee[k] + p_fund[k]
                    tr_reason[ntr] = reason
                    ntr += 1
                last_exit_t[i] = t
                p_inst[k] = -1; p_exit_pending[k] = 0
                continue
            if r_close[r] == r_close[r]:
                p_last[k] = r_close[r]
        # ---------------------------------------------------------------- C. funding
        for k in range(MAXP):
            if p_inst[k] < 0:
                continue
            i = p_inst[k]
            j = f_ptr[i]
            end = f_off[i + 1]
            while j < end and f_time[j] <= bar_open:
                j += 1
            f_ptr[i] = j
            while j < end and f_time[j] <= bar_close:
                rate = f_rate[j]
                notional = p_qty[k] * p_last[k]
                if rate == rate:
                    cf = -p_side[k] * notional * rate
                else:  # missing record → conservative rate against the position
                    lr = 0.0
                    jj = j - 1
                    while jj >= f_off[i]:
                        if f_rate[jj] == f_rate[jj]:
                            lr = abs(f_rate[jj])
                            break
                        jj -= 1
                    cf = -notional * max(lr, miss_fund_min)
                cash += cf
                p_fund[k] += cf
                j += 1
            # f_ptr not advanced past this bar so other positions (same inst) are impossible anyway
        # ---------------------------------------------------------------- D. mark to market
        upnl = 0.0
        gross = 0.0
        netb = 0.0
        npos = 0
        for k in range(MAXP):
            if p_inst[k] >= 0:
                upnl += p_side[k] * p_qty[k] * (p_last[k] - p_entry[k])
                gross += p_qty[k] * p_last[k]
                netb += p_side[k] * p_beta[k] * p_qty[k] * p_last[k]
                npos += 1
        equity = cash + upnl
        equity_curve[t] = equity
        gross_curve[t] = gross
        if equity <= 0:
            # account wiped out: stop trading (remaining steps keep equity)
            for tt in range(t + 1, T):
                equity_curve[tt] = equity
            break
        # ---------------------------------------------------------------- E. exit decisions
        for k in range(MAXP):
            if p_inst[k] < 0 or p_exit_pending[k] != 0:
                continue
            i = p_inst[k]
            if t - p_t[k] + 1 >= max_hold:
                p_exit_pending[k] = 1
            elif bar_close >= force_close_ms or bar_close >= known_delist[i] - 172800000:
                p_exit_pending[k] = 6
            elif exit_on_opp:
                for s_ in range(S):
                    if sel[h, s_] == i and sig[t, s_] == -p_side[k]:
                        p_exit_pending[k] = 5
                        break
        # ---------------------------------------------------------------- F. entry decisions
        if bar_close >= trade_end_ms:
            continue
        # collect candidates
        nc = 0
        c_s = np.empty(S, np.int64)
        c_sc = np.empty(S)
        for s_ in range(S):
            i = sel[h, s_]
            if i < 0 or sig[t, s_] == 0:
                continue
            c_s[nc] = s_
            c_sc[nc] = score[t, s_]
            nc += 1
        if nc == 0:
            continue
        # deterministic order: score desc, instrument asc
        order = np.empty(nc, np.int64)
        for a in range(nc):
            order[a] = a
        for a in range(1, nc):
            b = a
            while b > 0:
                x = order[b - 1]; y = order[b]
                ix = sel[h, c_s[x]]; iy = sel[h, c_s[y]]
                if (c_sc[y] > c_sc[x]) or (c_sc[y] == c_sc[x] and iy < ix):
                    order[b - 1] = y; order[b] = x
                    b -= 1
                else:
                    break
        for a in range(nc):
            s_ = c_s[order[a]]
            i = sel[h, s_]
            if npos + nq >= max_positions:
                break
            held = False
            for k in range(MAXP):
                if p_inst[k] == i:
                    held = True
                    break
            if held or t - last_exit_t[i] < cooldown:
                continue
            r = _row(i, t, r_off, r_start)
            if r < 0 or r_n1m[r] < 5 or not (r_rv60[r] == r_rv60[r]):
                continue
            if bar_close >= known_delist[i] - 172800000:
                continue
            notional = size_frac * equity
            if notional > max_pos_frac * equity:
                notional = max_pos_frac * equity
            if gross + notional > max_gross * equity:
                skipped += 1
                continue
            beta = h_beta[h - 1, i] if h > 0 else 1.0
            if not (beta == beta):
                beta = 1.0
            side = 1 if sig[t, s_] > 0 else -1
            if abs(netb + side * beta * notional) > max_net_beta * equity:
                skipped += 1
                continue
            q_inst[nq] = i; q_side[nq] = side; q_notional[nq] = notional
            q_sl[nq] = slf[t, s_]; q_tp[nq] = tpf[t, s_]; q_beta[nq] = beta
            nq += 1
            gross += notional
            netb += side * beta * notional
    return (equity_curve, gross_curve, tr_i[:ntr], tr_side[:ntr], tr_te[:ntr], tr_tx[:ntr], tr_pe[:ntr],
            tr_px[:ntr], tr_not[:ntr], tr_fee[:ntr], tr_slip[:ntr], tr_fund[:ntr], tr_pnl[:ntr],
            tr_reason[:ntr], skipped)


@dataclass
class Result:
    equity: np.ndarray
    gross: np.ndarray
    trades: dict
    skipped: int
    t0_ms: int


def run(panel, sel, sig, score, slf, tpf, *, size_frac, max_hold, cooldown=0, exit_on_opp=False,
        cost_stress=1.0, latency_stress=False, trade_end_ms=None, force_close_ms=None,
        step_size=None, min_notional=None) -> Result:
    """panel: universe.Panel-like object (see tests for a synthetic one)."""
    size_frac = min(float(size_frac), K.MAX_POSITION_FRAC)
    max_hold = int(min(max_hold, K.MAX_HOLD_MS // (5 * K.MIN_MS)))
    N = panel.N
    mmr = np.array([K.mmr_for(n) for n in panel.names])
    if step_size is None:
        step_size = np.full(N, np.nan)
    if min_notional is None:
        min_notional = np.array([K.MIN_NOTIONAL_MAJOR if n.split("#")[0] in K.MAJORS else K.MIN_NOTIONAL_DEFAULT
                                 for n in panel.names])
    if trade_end_ms is None:
        trade_end_ms = K.EVOLUTION_TRADE_END if panel.t_start < K.EVOLUTION_END else K.INNER_TRADE_END
    if force_close_ms is None:
        force_close_ms = trade_end_ms + 12 * K.HOUR_MS
    R = panel.r
    out = run_engine(panel.T, sel.shape[1], panel.t_start, sel, sig, score, slf, tpf, size_frac, max_hold,
                     int(cooldown), bool(exit_on_opp),
                     R["open"], R["high"], R["low"], R["close"], R["exec_open"], R["exec_open3"],
                     R["h_after"], R["l_after"],
                     R["rv60"], R["qv24h"], R["n1m"], panel.r_off, panel.r_start,
                     panel.h["rv_ratio"], panel.h["beta7d"], panel.f_time, panel.f_rate, panel.f_off,
                     panel.known_delist, mmr, step_size, min_notional, int(trade_end_ms), int(force_close_ms),
                     float(cost_stress), 1 if latency_stress else 0, K.START_CAPITAL, K.MAX_GROSS_LEVERAGE,
                     K.MAX_POSITION_FRAC, K.MAX_POSITIONS, K.MAX_NET_BETA, K.POSITION_LEVERAGE,
                     K.LIQUIDATION_FEE, K.TAKER_FEE, K.MISSING_FUNDING_MIN_RATE, K.GAP_EXIT_SLIP_MULT)
    keys = ["inst", "side", "t_entry", "t_exit", "entry_px", "exit_px", "notional", "fee", "slip",
            "funding", "pnl", "reason"]
    trades = dict(zip(keys, out[2:14]))
    return Result(out[0], out[1], trades, int(out[14]), panel.t_start)
