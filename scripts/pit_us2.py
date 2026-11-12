"""US strategy replayed the way the account would really trade (ChatGPT round 3):
- KRW account: 70,000 / 300,000 / 1,000,000 won start + 100,000 won every month, converted to dollars at that day's
  USD/KRW (Yahoo KRW=X) with a 0.25% FX spread; results in won.
- 1-share lots at the REAL price of that day (split-adjusted close x later split factors); a split multiplies the
  shares held; dividends paid in cash minus 15% tax. Trend uses split-adjusted prices.
- candidates: stocks whose market cap that day (adjusted close x today's share count) was >= $10B / $30B / $50B,
  from every NYSE/NASDAQ stock worth >= $2B today (bankrupt/acquired names still missing).
- page rules: daily check, 6-1 trend rank, top N (10/20/30), keep while in top 2N, 30-day swap lock, -12% stop filled
  next day, one stock <= 25% of the account (first share exempt), no new buys during a momentum crash,
  0.25% fee each way + 0.1% slippage.
- 3-year windows starting every quarter; benchmark = the same won deposits into the S&P 500 (SPY, fractional, dividends in).
Reports median yearly return (time-weighted, in won), final money vs paid in, max drawdown, average cash share,
average number of holdings, share of the top-N trend names that one share was affordable for, trades and costs."""
import json, time, datetime as dt, urllib.request, urllib.parse
import concurrent.futures as cf
import numpy as np
from signals import KST
from signals2 import YUA, _op, CRUMB
from pit_us import us_all

FEE, SLIP, FXS, DIVTAX = 0.0025, 0.001, 0.0025, 0.15

def chart(t):
    for i in range(4):
        try:
            u = (f"https://query{1 + i % 2}.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(t.replace('.', '-'))}"
                 f"?interval=1d&range=10y&events=div%7Csplit&crumb={urllib.parse.quote(CRUMB)}")
            with _op.open(urllib.request.Request(u, headers=YUA), timeout=25) as r:
                d = json.loads(r.read())["chart"]["result"][0]
            q = d["indicators"]["quote"][0]; ev = d.get("events") or {}
            day = lambda a: dt.datetime.utcfromtimestamp(int(a)).strftime("%Y%m%d")
            c = {day(a): cl for a, cl in zip(d["timestamp"], q["close"]) if cl}
            sp = {day(v["date"]): v["numerator"] / v["denominator"] for v in (ev.get("splits") or {}).values() if v.get("denominator")}
            dv = {day(v["date"]): v["amount"] for v in (ev.get("dividends") or {}).values()}
            adj = d["indicators"].get("adjclose", [{}])[0].get("adjclose")
            ac = {day(a): x for a, x in zip(d["timestamp"], adj) if x} if adj else {}
            return c, sp, dv, ac
        except Exception:
            time.sleep(1 + 2 * i)
    return {}, {}, {}, {}

def ffill(h, dates):
    out = np.full(len(dates), np.nan); last = np.nan; first = min(h) if h else None
    for i, d in enumerate(dates):
        if d in h: last = h[d]
        if first and d >= first: out[i] = last
    return out

def run(P, LOT, DIV, alive, E, SIG, crash, fx, dates, i0, i1, start, dep, topn, lock=21, stop=-0.12, cap=0.25):
    n = P.shape[1]
    u = np.zeros(n); cash = 0.0; entry = np.full(n, np.nan); since = np.zeros(n, int); pend = np.zeros(n, bool)
    curve, flows, trades, cost, month = [], [], 0, 0.0, None
    cash_sh, nhold, access = [], [], []
    def sell(j, px):
        nonlocal cash, cost, trades
        got = u[j] * px * (1 - SLIP); c = got * FEE; cash += got - c; cost += c * fx_i + u[j] * px * SLIP * fx_i; trades += 1
        u[j] = 0; entry[j] = np.nan
    for i in range(i0, i1):
        px = P[i]; fx_i = fx[i]; flow = 0.0
        for j in np.where((u > 0) & ~alive[i])[0]: sell(j, px[j])
        for j in np.where(pend & (u > 0))[0]:
            if not np.isnan(px[j]): sell(j, px[j])
        pend[:] = False
        # dividends: Yahoo amounts are already split-adjusted (per adjusted unit), so cash = units held x DIV
        for j in np.where((u > 0) & (DIV[i] > 0))[0]: cash += u[j] * DIV[i, j] * (1 - DIVTAX)
        if dates[i][:6] != month:
            add = start if month is None else dep
            cash += add / fx_i * (1 - FXS); flow = add if month is not None else 0.0; cost += add * FXS
            month = dates[i][:6]
        s = SIG[i - 1]; ok = E[i - 1] & ~np.isnan(s) & ~np.isnan(px)
        order = [j for j in np.argsort(-np.where(ok, s, -np.inf)) if ok[j]]
        rank = {j: r for r, j in enumerate(order)}
        for j in np.where(u > 0)[0]:
            if rank.get(j, 1e9) >= 2 * topn and i - since[j] >= lock and not np.isnan(px[j]): sell(j, px[j])
        eq = cash + np.nansum(u * px)
        target = [] if crash[i - 1] else order[:topn]
        if order[:topn]:
            access.append(np.mean([LOT[i, j] * px[j] * (1 + SLIP) * (1 + FEE) <= eq for j in order[:topn]]))
        changed = True
        while changed:
            changed = False
            for j in target:
                p1 = LOT[i, j] * px[j] * (1 + SLIP) * (1 + FEE)
                if p1 > cash: continue
                if u[j] > 0 and (u[j] + LOT[i, j]) * px[j] > cap * eq: continue
                if u[j] == 0: entry[j] = px[j]; since[j] = i
                cash -= p1; cost += LOT[i, j] * px[j] * (SLIP + FEE) * fx_i; u[j] += LOT[i, j]; trades += 1; changed = True
        pend = (u > 0) & ~np.isnan(px) & (px / entry - 1 <= stop)
        val = cash + np.nansum(np.where(u > 0, u * px, 0))
        curve.append(val * fx_i); flows.append(flow)
        cash_sh.append(cash / val if val > 0 else 1); nhold.append(int((u > 0).sum()))
    return np.array(curve), np.array(flows), trades, cost, float(np.mean(cash_sh)), float(np.mean(nhold)), float(np.mean(access)) if access else None

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

def main():
    SH = us_all(); tick = sorted(SH)
    with cf.ThreadPoolExecutor(4) as ex: R = list(ex.map(chart, tick))
    keep = [k for k, r in enumerate(R) if len(r[0]) > 300]; tick = [tick[k] for k in keep]; R = [R[k] for k in keep]
    spy = chart("SPY"); fxh = chart("KRW=X")[0]
    dates = sorted(d for d in spy[0] if d >= "20160101")
    T, n = len(dates), len(tick)
    di = {d: i for i, d in enumerate(dates)}; DA = np.array(dates)
    P = np.full((T, n), np.nan); LOT = np.ones((T, n)); DIV = np.zeros((T, n)); alive = np.zeros((T, n), bool)
    for j, (c, sp, dv, _) in enumerate(R):
        P[:, j] = ffill(c, dates)
        ds = sorted(c); alive[:, j] = [(ds[0] <= d <= ds[-1]) for d in dates]
        # LOT = real shares -> split-adjusted units: product of split ratios AFTER the day
        f = np.ones(T)
        for d, ratio in sp.items():
            f[DA < d] *= ratio
        LOT[:, j] = f
        for d, a in dv.items():
            if d in di: DIV[di[d], j] = a
    fx = ffill(fxh, dates); fx = np.where(np.isnan(fx), np.nanmean(fx), fx)
    B = ffill(spy[3] or spy[0], dates)
    age = np.cumsum(alive, axis=0)
    capm = np.nan_to_num(P) * np.array([SH[t] for t in tick])[None, :]
    m6 = np.full((T, n), np.nan); m6[126:] = P[105:-21] / P[:-126] - 1
    res = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "tickers": n,
           "realPriceCheck": {t: [round(float(P[-1, tick.index(t)] * LOT[-1, tick.index(t)]), 2), round(float(P[dates.index("20200103"), tick.index(t)] * LOT[dates.index("20200103"), tick.index(t)]), 2)]
                              for t in ("AAPL", "NVDA", "TSLA", "AMZN") if t in tick}}
    starts = list(range(260, T - 756, 63))
    scen = (("7만 원 + 매달 10만 원", 70000), ("30만 원 + 매달 10만 원", 300000), ("100만 원 + 매달 10만 원", 1000000))
    variants = (("시총 100억$+ · 상위 10 (지금)", 1e10, 10), ("시총 300억$+ · 상위 10", 3e10, 10), ("시총 500억$+ · 상위 10", 5e10, 10),
                ("시총 100억$+ · 상위 20", 1e10, 20), ("시총 100억$+ · 상위 30", 1e10, 30))
    for vname, thr, topn in variants:
        E = alive & (age >= 253) & (capm >= thr)
        SIG = np.where(E, m6, np.nan)
        crash = np.zeros(T, bool)
        for i in range(272, T):
            s = SIG[i - 20]; ok = ~np.isnan(s) & ~np.isnan(P[i]) & ~np.isnan(P[i - 20])
            if ok.sum() < 20: continue
            q = np.nanpercentile(s[ok], [20, 80]); ret = P[i] / P[i - 20] - 1
            if np.nanmean(ret[ok & (s >= q[1])]) - np.nanmean(ret[ok & (s <= q[0])]) < -0.10: crash[i:i + 6] = True
        crash = crash[:T]
        res[vname] = {"평균 후보 수": int(E.sum(1)[260:].mean())}
        for sname, st in scen:
            rows = []
            for a in starts:
                b = a + 756
                c, f, tr, cost, cs, nh, acc = run(P, LOT, DIV, alive, E, SIG, crash, fx, dates, a, b, st, 100000, topn)
                bc, bf = bench(B, fx, dates, a, b, st, 100000)
                cg, mdd = twr(c, f, dates[a:b]); bcg, bmdd = twr(bc, bf, dates[a:b])
                rows.append({"cagr": cg, "mdd": mdd, "final": c[-1], "paid": st + f.sum(), "bench": bcg, "bfinal": bc[-1], "bmdd": bmdd,
                             "cash": cs, "hold": nh, "acc": acc, "trades": tr / 3, "cost": cost / (st + f.sum())})
            med = lambda k: round(float(np.median([r[k] for r in rows])), 2)
            res[vname][sname] = {"연평균(중간값)": med("cagr"), "가장 나쁜 경우": round(min(r["cagr"] for r in rows), 1),
                                 "최대 하락(중간값)": med("mdd"), "최종/넣은 돈(중간값)": round(float(np.median([r["final"] / r["paid"] for r in rows])), 2),
                                 "S&P500 최종/넣은 돈": round(float(np.median([r["bfinal"] / r["paid"] for r in rows])), 2),
                                 "S&P500 연평균": med("bench"), "S&P500 최대 하락": med("bmdd"),
                                 "S&P500보다 많이 남은 비율%": round(float(np.mean([r["final"] > r["bfinal"] for r in rows]) * 100)),
                                 "평균 현금 비중%": round(med("cash") * 100), "평균 보유 종목 수": med("hold"),
                                 "상위 종목 중 1주 살 수 있던 비율%": round(med("acc") * 100) if rows[0]["acc"] is not None else None,
                                 "1년 거래 횟수": round(med("trades")), "비용/넣은 돈%": round(med("cost") * 100, 1)}
            print(vname, sname, res[vname][sname], flush=True)
            json.dump(res, open("pit_us2.json", "w"), ensure_ascii=False, indent=1)
    res["windows"] = len(starts); res["span"] = [dates[starts[0]], dates[starts[-1] + 755]]
    json.dump(res, open("pit_us2.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
