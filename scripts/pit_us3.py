"""Can the US rule step aside in bad markets? Same realistic replay as pit_us2 ($50B+, top 10, real share prices,
FX, splits, dividends, 70,000 / 300,000 / 1,000,000 won + 100,000 won a month), adding exit rules that SELL holdings:
 A  S&P 500 closes below its 200-day average -> sell everything, hold cash, buy again once it closes above
 B  same with a 10-month average checked at month ends only (Faber 2007)
 C  absolute momentum: sell / do not buy a stock whose own 6-1 return is below zero (Antonacci 2014)
 D  account falls 20% from its peak -> sell everything, wait until the S&P 500 is above its 200-day average
 E  A + C together"""
import json, datetime as dt
import concurrent.futures as cf
import numpy as np
from signals import KST
from pit_us import us_all
from pit_us2 import chart, ffill, twr, bench, FEE, SLIP, FXS, DIVTAX

def run(P, LOT, DIV, alive, E, SIG, crash, fx, dates, i0, i1, start, dep, topn, off=None, absmom=False, ddstop=None, up=None,
        lock=21, stop=-0.12, cap=0.25):
    n = P.shape[1]
    u = np.zeros(n); cash = 0.0; entry = np.full(n, np.nan); since = np.zeros(n, int); pend = np.zeros(n, bool)
    curve, flows, trades, cost, month = [], [], 0, 0.0, None
    peak, out_dd, days_out = 0.0, False, 0
    for i in range(i0, i1):
        px = P[i]; fx_i = fx[i]; flow = 0.0
        def sell(j):
            nonlocal cash, cost, trades
            got = u[j] * px[j] * (1 - SLIP); c = got * FEE; cash += got - c; cost += (c + u[j] * px[j] * SLIP) * fx_i; trades += 1
            u[j] = 0; entry[j] = np.nan
        for j in np.where((u > 0) & ~alive[i])[0]: sell(j)
        for j in np.where(pend & (u > 0))[0]:
            if not np.isnan(px[j]): sell(j)
        pend[:] = False
        for j in np.where((u > 0) & (DIV[i] > 0))[0]: cash += u[j] * DIV[i, j] * (1 - DIVTAX)
        if dates[i][:6] != month:
            add = start if month is None else dep
            cash += add / fx_i * (1 - FXS); flow = add if month is not None else 0.0; cost += add * FXS; month = dates[i][:6]
        val0 = cash + np.nansum(np.where(u > 0, u * px, 0))
        if ddstop is not None:
            peak = max(peak, val0 * fx_i) if not out_dd else peak
            if not out_dd and peak > 0 and val0 * fx_i < (1 - ddstop) * peak: out_dd = True
            elif out_dd and up[i - 1]: out_dd = False; peak = val0 * fx_i
        risk_off = (off is not None and off[i - 1]) or out_dd
        if risk_off:
            for j in np.where(u > 0)[0]:
                if not np.isnan(px[j]): sell(j)
            days_out += 1
        s = SIG[i - 1]; ok = E[i - 1] & ~np.isnan(s) & ~np.isnan(px)
        if absmom: ok &= s > 0
        order = [j for j in np.argsort(-np.where(ok, s, -np.inf)) if ok[j]]
        rank = {j: r for r, j in enumerate(order)}
        for j in np.where(u > 0)[0]:
            if absmom and not (s[j] > 0) and not np.isnan(px[j]): sell(j); continue
            if rank.get(j, 1e9) >= 2 * topn and i - since[j] >= lock and not np.isnan(px[j]): sell(j)
        eq = cash + np.nansum(u * px)
        target = [] if (crash[i - 1] or risk_off) else order[:topn]
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
        curve.append((cash + np.nansum(np.where(u > 0, u * px, 0))) * fx_i); flows.append(flow)
    return np.array(curve), np.array(flows), trades, cost, days_out / (i1 - i0)

def main():
    SH = us_all(); tick = sorted(SH)
    with cf.ThreadPoolExecutor(4) as ex: R = list(ex.map(chart, tick))
    keep = [k for k, r in enumerate(R) if len(r[0]) > 300]; tick = [tick[k] for k in keep]; R = [R[k] for k in keep]
    spy = chart("SPY"); fxh = chart("KRW=X")[0]
    dates = sorted(d for d in spy[0] if d >= "20160101"); T, n = len(dates), len(tick)
    di = {d: i for i, d in enumerate(dates)}; DA = np.array(dates)
    P = np.full((T, n), np.nan); LOT = np.ones((T, n)); DIV = np.zeros((T, n)); alive = np.zeros((T, n), bool)
    for j, (c, sp, dv, _) in enumerate(R):
        P[:, j] = ffill(c, dates); ds = sorted(c); alive[:, j] = (DA >= ds[0]) & (DA <= ds[-1])
        f = np.ones(T)
        for d, ratio in sp.items(): f[DA < d] *= ratio
        LOT[:, j] = f
        for d, a in dv.items():
            if d in di: DIV[di[d], j] = a
    fx = ffill(fxh, dates); fx = np.where(np.isnan(fx), np.nanmean(fx), fx)
    B = ffill(spy[3] or spy[0], dates); S = ffill(spy[0], dates)
    age = np.cumsum(alive, axis=0); capm = np.nan_to_num(P) * np.array([SH[t] for t in tick])[None, :]
    E = alive & (age >= 253) & (capm >= 5e10)
    m6 = np.full((T, n), np.nan); m6[126:] = P[105:-21] / P[:-126] - 1; SIG = np.where(E, m6, np.nan)
    crash = np.zeros(T, bool)
    for i in range(272, T):
        s = SIG[i - 20]; ok = ~np.isnan(s) & ~np.isnan(P[i]) & ~np.isnan(P[i - 20])
        if ok.sum() < 20: continue
        q = np.nanpercentile(s[ok], [20, 80]); ret = P[i] / P[i - 20] - 1
        if np.nanmean(ret[ok & (s >= q[1])]) - np.nanmean(ret[ok & (s <= q[0])]) < -0.10: crash[i:i + 6] = True
    crash = crash[:T]
    ma200 = np.array([np.nanmean(S[max(0, i - 199):i + 1]) for i in range(T)]); below = S < ma200
    me = np.array([i == T - 1 or dates[i][:6] != dates[i + 1][:6] for i in range(T)])
    ma10 = np.full(T, np.nan); offB = np.zeros(T, bool); state = False; mes = [i for i in range(T) if me[i]]
    for k, i in enumerate(mes):
        if k >= 10: state = S[i] < np.mean([S[x] for x in mes[k - 9:k + 1]])
        nxt = mes[k + 1] if k + 1 < len(mes) else T
        offB[i:nxt] = state
    variants = {"지금 규칙": {}, "A 지수 200일선 아래면 전부 팔기": {"off": below}, "B 지수 10개월선 아래면 전부 팔기 (월말 확인)": {"off": offB},
                "C 6개월 수익률 마이너스 종목은 팔기": {"absmom": True}, "D 계좌 −20%면 전부 팔고 지수 회복 때 복귀": {"ddstop": 0.2, "up": ~below},
                "E = A + C": {"off": below, "absmom": True}}
    starts = list(range(260, T - 756, 63))
    res = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "windows": len(starts),
           "spyBelow200Share": round(float(below[260:].mean()) * 100, 1)}
    for sname, st in (("7만 원 + 매달 10만 원", 70000), ("30만 원 + 매달 10만 원", 300000), ("100만 원 + 매달 10만 원", 1000000)):
        res[sname] = {}
        base_fin = None
        for vname, kw in variants.items():
            rows = []
            for a in starts:
                b = a + 756
                c, f, tr, cost, outshare = run(P, LOT, DIV, alive, E, SIG, crash, fx, dates, a, b, st, 100000, 10, **kw)
                bc, bf = bench(B, fx, dates, a, b, st, 100000)
                cg, mdd = twr(c, f, dates[a:b])
                rows.append({"cagr": cg, "mdd": mdd, "fin": c[-1], "paid": st + f.sum(), "bfin": bc[-1], "out": outshare, "tr": tr / 3})
            fin = np.array([r["fin"] for r in rows])
            if base_fin is None: base_fin = fin
            med = lambda k: round(float(np.median([r[k] for r in rows])), 2)
            res[sname][vname] = {"연평균(중간값)": med("cagr"), "가장 나쁜 경우": round(min(r["cagr"] for r in rows), 1), "최대 하락(중간값)": med("mdd"),
                                 "가장 큰 하락": round(min(r["mdd"] for r in rows), 1),
                                 "최종/넣은 돈(중간값)": round(float(np.median(fin / np.array([r["paid"] for r in rows]))), 2),
                                 "지금 규칙보다 많이 남은 비율%": round(float((fin > base_fin).mean() * 100)),
                                 "S&P500보다 많이 남은 비율%": round(float(np.mean([r["fin"] > r["bfin"] for r in rows]) * 100)),
                                 "현금으로 피해 있던 기간%": round(med("out") * 100), "1년 거래": round(med("tr"))}
            print(sname, vname, res[sname][vname], flush=True)
            json.dump(res, open("pit_us3.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
