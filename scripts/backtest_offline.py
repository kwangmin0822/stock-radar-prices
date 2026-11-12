"""Stand-alone, offline replay of the adopted US strategy (pit_us7.py variant "손절 없음").
Needs only numpy + pandas + pyarrow and the data folder made by export_data.py. No network.

  python backtest_offline.py DATA_DIR OUT_DIR

The rules below are a line-by-line copy of pit_us7.run() / pit_us2.twr() / pit_us2.bench() with stop=None,
topn=3, keep=2.0 (sell when rank >= 6, i.e. outside the top 6), lock=21 trading days, ban=0, cap=0.25.
Fixes vs the first report (2026-11-12): dividends = units held x Yahoo's split-adjusted amount (was divided by the
split factor again), and past market cap uses dated share counts (PIT_SHARES) instead of today's count.
On top of that it records every trading day (signal, trades, holdings, cash, value) so the result can be audited.
"""
import sys, os, json, datetime as dt
import numpy as np
import pandas as pd

FEE, SLIP, FXS, DIVTAX = 0.0025, 0.001, 0.0025, 0.15
SCEN = (("7만 원 + 매달 10만 원", 70000), ("30만 원 + 매달 10만 원", 300000), ("100만 원 + 매달 10만 원", 1000000))
DEP = 100000
CAP_MIN = 5e10          # candidate: that day's market cap (split-adjusted close x today's share count) >= $50B
AGE_MIN = 253           # and at least 253 trading days of history
TOPN, KEEP, LOCK, BAN, CAP = 3, 2.0, 21, 0, 0.25
PIT_SHARES = True       # False = old method (today's share count for every past day)
WIN, STEP, FIRST = 756, 63, 260   # 3-year windows, a new one every quarter, first one after ~1 year of history


def ffill(h, dates):
    out = np.full(len(dates), np.nan); last = np.nan; first = min(h) if h else None
    for i, d in enumerate(dates):
        if d in h: last = h[d]
        if first and d >= first: out[i] = last
    return out


def load(data_dir):
    px = pd.read_parquet(os.path.join(data_dir, "us_prices_daily.parquet"))
    spl = pd.read_parquet(os.path.join(data_dir, "us_splits.parquet"))
    div = pd.read_parquet(os.path.join(data_dir, "us_dividends.parquet"))
    uni = pd.read_parquet(os.path.join(data_dir, "us_universe_shares.parquet"))
    spy = pd.read_parquet(os.path.join(data_dir, "spy_daily.parquet"))
    fxd = pd.read_parquet(os.path.join(data_dir, "usdkrw_daily.parquet"))
    # same rule as pit_us2.chart(): a close is used only when it is not null / not 0
    px = px[px["close"].notna() & (px["close"] != 0)]
    closes = {t: dict(zip(g["date"], g["close"])) for t, g in px.groupby("ticker")}
    tick = sorted(t for t in uni["ticker"] if len(closes.get(t, {})) > 300)
    SH = dict(zip(uni["ticker"], uni["shares_today"]))
    s_c = spy[spy["close"].notna() & (spy["close"] != 0)]
    s_a = spy[spy["adjclose"].notna() & (spy["adjclose"] != 0)]
    dates = sorted(d for d in s_c["date"] if d >= "20160101")
    T, n = len(dates), len(tick); di = {d: i for i, d in enumerate(dates)}; DA = np.array(dates)
    P = np.full((T, n), np.nan); LOT = np.ones((T, n)); DIV = np.zeros((T, n)); alive = np.zeros((T, n), bool)
    sp_by = {t: g for t, g in spl.groupby("ticker")}; dv_by = {t: g for t, g in div.groupby("ticker")}
    for j, t in enumerate(tick):
        c = closes[t]
        P[:, j] = ffill(c, dates); ds = sorted(c); alive[:, j] = (DA >= ds[0]) & (DA <= ds[-1])
        f = np.ones(T)
        if t in sp_by:
            for d, r in zip(sp_by[t]["date"], sp_by[t]["ratio"]): f[DA < d] *= r
        LOT[:, j] = f
        if t in dv_by:
            for d, a in zip(dv_by[t]["date"], dv_by[t]["amount"]):
                if d in di: DIV[di[d], j] = a
    fx_c = fxd[fxd["close"].notna() & (fxd["close"] != 0)]
    fx = ffill(dict(zip(fx_c["date"], fx_c["close"])), dates); fx = np.where(np.isnan(fx), np.nanmean(fx), fx)
    B = ffill(dict(zip(s_a["date"], s_a["adjclose"])) if len(s_a) else dict(zip(s_c["date"], s_c["close"])), dates)
    D = dict(P=P, LOT=LOT, DIV=DIV, alive=alive, fx=fx, B=B, dates=dates, tick=tick, SH=SH, T=T, n=n)
    if PIT_SHARES and os.path.exists(os.path.join(data_dir, "us_shares_history_yahoo.parquet")):
        D["SHT"], D["pit_shares_tickers"] = pit_shares(data_dir, D, uni)
    return D


def pit_shares(data_dir, D, uni):
    """Share count by date instead of today's count. Yahoo's reported ordinary-share counts (quarterly, else annual;
    split-adjusted) are used from their date on; before the oldest report (about 2021-12) the oldest report is used.
    Counts are scaled so the latest report equals today's Naver count (fixes class/ADR unit differences); a ticker
    whose latest report is more than 20% away from today's count (ADRs, multi-class) keeps today's count."""
    sh = pd.read_parquet(os.path.join(data_dir, "us_shares_history_yahoo.parquet"))
    q = sh[sh["type"] == "quarterlyOrdinarySharesNumber"]; a = sh[sh["type"] == "annualOrdinarySharesNumber"]
    src = {t: g for t, g in q.groupby("ticker")}
    for t, g in a.groupby("ticker"): src.setdefault(t, g)
    DA = np.array(D["dates"]); SHT = np.tile(np.array([D["SH"][t] for t in D["tick"]], float), (D["T"], 1)); used = []
    for j, t in enumerate(D["tick"]):
        g = src.get(t)
        if g is None or not len(g): continue
        g = g.sort_values("as_of"); today = D["SH"][t]; k = today / g["shares"].iloc[-1]
        if not (0.8 <= k <= 1.25): continue
        col = np.full(D["T"], g["shares"].iloc[0] * k)
        for d, v in zip(g["as_of"], g["shares"]): col[DA >= d] = v * k
        SHT[:, j] = col; used.append(t)
    return SHT, used


def signals(D):
    P, alive, T, n = D["P"], D["alive"], D["T"], D["n"]
    age = np.cumsum(alive, axis=0)
    capm = np.nan_to_num(P) * D.get("SHT", np.array([D["SH"][t] for t in D["tick"]])[None, :])
    E = alive & (age >= AGE_MIN) & (capm >= CAP_MIN)
    m = np.full((T, n), np.nan); m[126:] = P[105:T - 21] / P[:T - 126] - 1     # 6-1 trend: close 21 days ago / close 126 days ago - 1
    SIG = np.where(E, m, np.nan)
    crash = np.zeros(T, bool); spread = np.full(T, np.nan)
    for i in range(272, T):
        s = SIG[i - 20]; ok = ~np.isnan(s) & ~np.isnan(P[i]) & ~np.isnan(P[i - 20])
        if ok.sum() < 20: continue
        q = np.nanpercentile(s[ok], [20, 80]); ret = P[i] / P[i - 20] - 1
        spread[i] = np.nanmean(ret[ok & (s >= q[1])]) - np.nanmean(ret[ok & (s <= q[0])])
        if spread[i] < -0.10: crash[i:i + 6] = True     # flag day i .. i+5; run() reads crash[i-1], so buys pause for the 6 trading days after a trigger (same as the live radar)
    return dict(E=E, SIG=SIG, crash=crash[:T], spread=spread, capm=capm, age=age)


def run(D, S, i0, i1, start, dep, ledger=None, trades_log=None):
    P, LOT, DIV, alive, fx, dates, tick = D["P"], D["LOT"], D["DIV"], D["alive"], D["fx"], D["dates"], D["tick"]
    E, SIG, crash = S["E"], S["SIG"], S["crash"]
    n = P.shape[1]
    u = np.zeros(n); cash = 0.0; entry = np.full(n, np.nan); since = np.zeros(n, int)
    sold_at = np.full(n, -10**9); curve, flows, trades, month = [], [], 0, None
    for i in range(i0, i1):
        px = P[i]; fx_i = fx[i]; flow = 0.0; tl = []
        def sell(j, why):
            nonlocal cash, trades
            got = u[j] * px[j] * (1 - SLIP) * (1 - FEE); cash += got; trades += 1
            tl.append(dict(date=dates[i], ticker=tick[j], side="sell", reason=why, real_shares=round(u[j] / LOT[i, j], 6),
                           real_price=px[j] * LOT[i, j], usd=got))
            u[j] = 0; entry[j] = np.nan; sold_at[j] = i
        for j in np.where((u > 0) & ~alive[i])[0]: sell(j, "delisted/no-more-data")
        divi = 0.0
        for j in np.where((u > 0) & (DIV[i] > 0))[0]:
            d = u[j] * DIV[i, j] * (1 - DIVTAX); cash += d; divi += d
        dep_krw = 0.0
        if dates[i][:6] != month:
            add = start if month is None else dep
            cash += add / fx_i * (1 - FXS); flow = add if month is not None else 0.0; month = dates[i][:6]; dep_krw = add
        s = SIG[i - 1]; ok = E[i - 1] & ~np.isnan(s) & ~np.isnan(px)
        order = [j for j in np.argsort(-np.where(ok, s, -np.inf)) if ok[j]]
        rank = {j: r for r, j in enumerate(order)}
        for j in np.where(u > 0)[0]:
            if rank.get(j, 1e9) >= KEEP * TOPN and i - since[j] >= LOCK and not np.isnan(px[j]): sell(j, "rank>=6 after lock")
        eq = cash + np.nansum(u * px)
        target = [] if crash[i - 1] else [j for j in order[:TOPN] if u[j] > 0 or i - sold_at[j] >= BAN]
        changed = True
        while changed:
            changed = False
            for j in target:
                p1 = LOT[i, j] * px[j] * (1 + SLIP) * (1 + FEE)
                if p1 > cash: continue
                if u[j] > 0 and (u[j] + LOT[i, j]) * px[j] > CAP * eq: continue
                if u[j] == 0: entry[j] = px[j]; since[j] = i
                cash -= p1; u[j] += LOT[i, j]; trades += 1; changed = True
                tl.append(dict(date=dates[i], ticker=tick[j], side="buy", reason=f"rank {rank[j] + 1}", real_shares=1.0,
                               real_price=px[j] * LOT[i, j], usd=-p1))
        val = cash + np.nansum(np.where(u > 0, u * px, 0))
        curve.append(val * fx_i); flows.append(flow)
        if ledger is not None:
            h = {tick[j]: round(float(u[j] / LOT[i, j]), 4) for j in np.where(u > 0)[0]}
            ledger.append(dict(date=dates[i], deposit_krw=dep_krw, usdkrw=fx_i, crash_block=bool(crash[i - 1]),
                               top3=",".join(tick[j] for j in order[:3]), top6=",".join(tick[j] for j in order[:6]),
                               n_buys=sum(t["side"] == "buy" for t in tl), n_sells=sum(t["side"] == "sell" for t in tl),
                               dividends_usd=divi, cash_usd=cash, value_usd=val, value_krw=val * fx_i, n_holdings=len(h),
                               holdings_real_shares=json.dumps(h)))
        if trades_log is not None: trades_log.extend(tl)
    return np.array(curve), np.array(flows), trades


def twr(curve, flows, dates):
    g = 1.0; idx = [1.0]
    for i in range(1, len(curve)):
        r = (curve[i] - flows[i]) / curve[i - 1] if curve[i - 1] > 0 else 1
        g *= r; idx.append(idx[-1] * r)
    yrs = (dt.date(int(dates[-1][:4]), int(dates[-1][4:6]), int(dates[-1][6:])) - dt.date(int(dates[0][:4]), int(dates[0][4:6]), int(dates[0][6:]))).days / 365.25
    idx = np.array(idx)
    return round((g ** (1 / yrs) - 1) * 100, 1), round(float(np.min(idx / np.maximum.accumulate(idx) - 1)) * 100, 1)


def bench(B, fx, dates, i0, i1, start, dep):
    units, month, curve, flows = 0.0, None, [], []
    for i in range(i0, i1):
        flow = 0.0
        if dates[i][:6] != month:
            add = start if month is None else dep
            units += add / fx[i] * (1 - FXS) / B[i]; flow = add if month is not None else 0.0; month = dates[i][:6]
        curve.append(units * B[i] * fx[i]); flows.append(flow)
    return np.array(curve), np.array(flows)


def main(data_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    D = load(data_dir); S = signals(D); dates, T = D["dates"], D["T"]
    starts = list(range(FIRST, T - WIN, STEP))
    win = pd.DataFrame([dict(window=k + 1, start_index=a, start=dates[a], end=dates[a + WIN - 1]) for k, a in enumerate(starts)])
    win.to_csv(os.path.join(out_dir, "windows.csv"), index=False)
    rows, summ = [], {}
    for sname, st in SCEN:
        for k, a in enumerate(starts):
            b = a + WIN; led, trl = [], []
            c, f, tr = run(D, S, a, b, st, DEP, led, trl)
            bc, bf = bench(D["B"], D["fx"], dates, a, b, st, DEP)
            cg, mdd = twr(c, f, dates[a:b]); bcg, bmdd = twr(bc, bf, dates[a:b])
            rows.append(dict(scenario=sname, start_krw=st, window=k + 1, start=dates[a], end=dates[b - 1], cagr_pct=cg, mdd_pct=mdd,
                             final_krw=round(c[-1]), paid_krw=st + f.sum(), spy_cagr_pct=bcg, spy_mdd_pct=bmdd, spy_final_krw=round(bc[-1]),
                             trades_per_year=round(tr / 3, 1), max_holdings=max(x["n_holdings"] for x in led)))
            pd.DataFrame(led).assign(scenario=sname, window=k + 1).to_csv(
                os.path.join(out_dir, f"ledger_{st}_w{k + 1:02d}.csv.gz"), index=False)
            pd.DataFrame(trl).assign(scenario=sname, window=k + 1).to_csv(
                os.path.join(out_dir, f"trades_{st}_w{k + 1:02d}.csv.gz"), index=False)
        r = [x for x in rows if x["scenario"] == sname]
        summ[sname] = {"연평균(중간값)": round(float(np.median([x["cagr_pct"] for x in r])), 2),
                       "가장 나쁜 경우": min(x["cagr_pct"] for x in r),
                       "최대 하락(중간값)": round(float(np.median([x["mdd_pct"] for x in r])), 2)}
        print(sname, summ[sname], flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(out_dir, "window_results.csv"), index=False)
    json.dump({"tickers": D["n"], "days": T, "first_date": dates[0], "last_date": dates[-1], "windows": len(starts), "summary": summ},
              open(os.path.join(out_dir, "summary.json"), "w"), ensure_ascii=False, indent=1)
    return D, S, rows


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
