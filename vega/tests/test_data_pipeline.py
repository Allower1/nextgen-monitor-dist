import io
import json
import zipfile

import numpy as np
import pandas as pd
import pytest

from vega_core import kernel as K
from vega_core.data import derive as D
from vega_core.data import download as DL
from vega_core.data import discover as DS
from vega_core import features as FE
from vega_core import universe as U
from vega_core import scanner as SC
from vega_core.evolution import ledger as LG

M = K.MIN_MS


def mk_1m(n=600, t0=K.DEV_START, price=100.0, seed=0, drop=()):
    rng = np.random.default_rng(seed)
    c = price * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    o = np.concatenate([[price], c[:-1]])
    h = np.maximum(o, c) * 1.0005
    l = np.minimum(o, c) * 0.9995
    df = pd.DataFrame({"open_time": t0 + np.arange(n, dtype=np.int64) * M, "open": o, "high": h, "low": l,
                       "close": c, "volume": 1.0, "quote_volume": 1000.0, "count": 10,
                       "taker_buy_quote_volume": 600.0})
    if drop:
        df = df.drop(index=list(drop)).reset_index(drop=True)
    return df


def test_resample_5m_correct_and_close_time():
    df = mk_1m(60)
    g = D.dense_grid(df)
    b, hr = D.derive_instrument(g)
    assert len(b) == 12
    r = df.iloc[5:10]
    assert b.open_time[1] == K.DEV_START + 5 * M
    assert b.open[1] == pytest.approx(r.open.iloc[0])
    assert b.high[1] == pytest.approx(r.high.max()) and b.low[1] == pytest.approx(r.low.min())
    assert b.close[1] == pytest.approx(r.close.iloc[-1])
    assert b.exec_open[1] == pytest.approx(r.open.iloc[1])      # fill at bar open + 60 s
    assert b.exec_open3[1] == pytest.approx(r.open.iloc[3])
    assert b.h_after[1] == pytest.approx(r.high.iloc[1:].max())
    assert len(hr) == 1 and hr.qv1h[0] == pytest.approx(60 * 1000.0)


def test_missing_bars_not_forward_filled():
    df = mk_1m(60, drop=(7, 8))
    b, _ = D.derive_instrument(D.dense_grid(df))
    assert b.n1m[1] == 3
    assert b.n1m[0] == 5
    df2 = mk_1m(60, drop=(5,))
    b2, _ = D.derive_instrument(D.dense_grid(df2))
    assert np.isnan(b2.open[1])          # first minute missing → open unknown, not filled


def test_rolling_rv_is_causal():
    df = mk_1m(600, seed=1)
    b1, _ = D.derive_instrument(D.dense_grid(df))
    df2 = df.copy()
    df2.loc[400:, ["open", "high", "low", "close"]] *= 3.0   # change the future
    b2, _ = D.derive_instrument(D.dense_grid(df2))
    k = 399 // 5 - 1        # bars closing before minute 399
    np.testing.assert_allclose(b1.rv60[:k], b2.rv60[:k])
    np.testing.assert_allclose(b1.qv24h[:k], b2.qv24h[:k])


def test_audit_duplicates_and_bad_rows():
    df = mk_1m(100)
    df = pd.concat([df, df.iloc[[3, 4]]])
    df.loc[df.index[10], "low"] = -1
    c, a = D.audit_and_clean(df)
    assert a["duplicates"] == 2 and a["bad_ohlc"] >= 1
    assert c.open_time.is_unique and c.open_time.is_monotonic_increasing


def test_segmentation_relist_and_reuse():
    a = mk_1m(200, price=100.0)
    b = mk_1m(200, t0=K.DEV_START + 10 * K.DAY_MS, price=100.0)        # 10-day gap → new instrument
    c = mk_1m(200, t0=K.DEV_START + 12 * K.DAY_MS, price=2.0)          # 2-day gap + price jump → new
    d = mk_1m(200, t0=K.DEV_START + 12 * K.DAY_MS + 300 * M, price=2.0)  # short gap, no jump → same
    df = pd.concat([a, b, c, d]).reset_index(drop=True)
    segs = D.segment(df)
    assert len(segs) == 3


def test_feature_causality_future_change():
    rng = np.random.default_rng(3)
    n = 3000
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    h, l = c * 1.001, c * 0.999
    qv = rng.uniform(1e5, 2e5, n)
    tb = qv * 0.5
    f1 = FE.instrument_features(c, h, l, qv, tb)
    c2 = c.copy(); c2[2000:] *= 1.5
    h2, l2 = c2 * 1.001, c2 * 0.999
    qv2 = qv.copy(); qv2[2000:] *= 10
    f2 = FE.instrument_features(c2, h2, l2, qv2, tb)
    for k in f1:
        np.testing.assert_allclose(f1[k][:2000], f2[k][:2000], rtol=1e-5, equal_nan=True, err_msg=k)


def test_rolling_beta_causal_and_correct():
    rng = np.random.default_rng(0)
    H = 400
    btc = rng.normal(0, 0.01, H)
    x = 2.0 * btc + rng.normal(0, 0.001, H)
    ret = np.stack([btc, x], 1).astype(np.float32)
    b = U.rolling_beta(ret, 0)
    assert b[300, 1] == pytest.approx(2.0, abs=0.05) and b[300, 0] == pytest.approx(1.0, abs=1e-3)
    ret2 = ret.copy(); ret2[350:, 1] *= -5
    b2 = U.rolling_beta(ret2, 0)
    np.testing.assert_allclose(b[:350], b2[:350])


def test_missing_funding_inserted():
    f = pd.DataFrame({"calc_time": [0, 8 * K.HOUR_MS, 32 * K.HOUR_MS], "interval_h": [8, 8, 8], "rate": [1e-4, 2e-4, 3e-4]})
    t, r = U.fill_missing_funding(f)
    assert list(t) == [0, 8 * K.HOUR_MS, 16 * K.HOUR_MS, 24 * K.HOUR_MS, 32 * K.HOUR_MS]
    assert np.isnan(r[2]) and np.isnan(r[3])


def test_parse_klines_with_and_without_header_and_microseconds():
    rows = "1583020800000,1,2,0.5,1.5,10,1583020859999,15,3,5,7,0\n"
    hdr = ",".join(DL.KLINE_COLS) + "\n"
    for raw in (rows, hdr + rows):
        t = DL.parse_klines(raw.encode())
        assert t.num_rows == 1 and t.column("open_time")[0].as_py() == 1583020800000
    us = "1583020800000000,1,2,0.5,1.5,10,1583020859999999,15,3,5,7,0\n"
    assert DL.parse_klines(us.encode()).column("open_time")[0].as_py() == 1583020800000


def test_holdout_keys_dropped_in_listing(monkeypatch):
    xml = ("<ListBucketResult><IsTruncated>false</IsTruncated>"
           "<Contents><Key>data/futures/um/monthly/klines/X/1m/X-1m-2025-12.zip</Key><Size>5</Size></Contents>"
           "<Contents><Key>data/futures/um/monthly/klines/X/1m/X-1m-2026-01.zip</Key><Size>5</Size></Contents>"
           "</ListBucketResult>")
    monkeypatch.setattr(DS, "_get", lambda url, tries=5: xml)
    keys = DS._list("data/futures/um/monthly/klines/X/1m/")
    assert [k for k, _ in keys] == ["data/futures/um/monthly/klines/X/1m/X-1m-2025-12.zip"]


def test_reader_zone_guard(tmp_path, monkeypatch):
    g = K.ZoneGuard("evolution")
    monkeypatch.setattr(D, "DATA", tmp_path)
    d = tmp_path / "k1m" / "dev" / "XUSDT"
    d.mkdir(parents=True)
    mk_1m(10).to_parquet(d / "2025-01.parquet")
    with pytest.raises(K.LeakageError):
        D.load_symbol_1m("dev", "XUSDT", g)


def test_download_jobs_zone_guarded(tmp_path, monkeypatch):
    listing = {"symbols": {"XUSDT": {"klines_1m_monthly": [["data/futures/um/monthly/klines/XUSDT/1m/XUSDT-1m-2024-12.zip", 1],
                                                          ["data/futures/um/monthly/klines/XUSDT/1m/XUSDT-1m-2025-01.zip", 1]],
                                     "funding_monthly": []}}}
    p = tmp_path / "l.json"; p.write_text(json.dumps(listing))
    monkeypatch.setattr(DL, "LISTING", p)
    dev = DL.jobs_for("dev")
    assert [j[3][-11:-4] for j in dev] == ["2024-12"]
    inner = DL.jobs_for("inner")
    assert [j[3][-11:-4] for j in inner] == ["2025-01"]


def test_ledger_hash_chain(tmp_path):
    p = tmp_path / "t.jsonl"
    LG.append([{"stage": "screen", "x": 1}, {"stage": "screen", "x": 2}], p)
    LG.append([{"stage": "gate", "x": 3}], p)
    assert LG.verify(p) and LG.n_trials(p) == 3
    lines = p.read_text().splitlines()
    lines[1] = lines[1].replace('"x": 2', '"x": 5')
    p.write_text("\n".join(lines) + "\n")
    assert not LG.verify(p)


def test_scanner_uses_previous_hour_only():
    class P:  # minimal panel
        pass
    H, N = 5, 3
    p = P()
    p.pool = np.tile(np.arange(N, dtype=np.int32), (H, 1))
    base = {k: np.ones((H, N), np.float32) for k in ["rv_ratio", "rel_vol", "ret1h", "ret4h", "range_exp", "qv24h", "funding", "zmove1h"]}
    base["rv_ratio"][2] = [1, 9, 1]     # anomaly in row 2 (hour 2 closes at 3)
    p.h = base
    si = SC.ScannerInputs(p)
    sel_slot, sel_inst, flag = SC.select_top(si, {"rv_ratio": 1.0}, 0.0, 3.0, 99, 99, top_n=1)
    assert sel_inst[3, 0] == 1           # visible in hour 3
    assert sel_inst[2, 0] == 0           # not in hour 2 (tie → lowest id)
    assert flag[3, 1] and not flag[2, 1]
