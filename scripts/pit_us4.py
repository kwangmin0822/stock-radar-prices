"""US turnover experiments (ChatGPT round 5), same realistic replay as pit_us2/3 ($50B+, top 10 new buys, real share
prices, FX, splits, dividends, 70,000 / 300,000 / 1,000,000 won + 100,000 won a month). One change at a time:
 keep buffer: a holding is sold for rank only when it falls below rank 10 / 15 / 20 (current replay) / 30 / 40
 score gap: sell for rank only if it is out of the top 10 AND the best stock not held scores 5 / 10 / 15 points higher
            (score = percentile of the 6-1 trend among candidates, 0~100, like the page)
 weekly: stop-loss daily, rank swaps only on the first trading day of each week
 trend window: 3-1 / 9-1 / 12-1 months instead of 6-1
Plus: year-by-year return of the current rule vs the S&P 500 (one long run from 2017)."""
import json, datetime as dt
import concurrent.futures as cf
import numpy as np
from signals import KST
from signals6 import rankpct
from pit_us import us_all
from pit_us2 import chart, ffill, twr, bench, FEE, SLIP, FXS, DIVTAX

def run(P, LOT, DIV, alive, E, SIG, PCT, crash, fx, dates, i0, i1, start, dep, topn=10, keep=2.0, gap=None, weekly=False,
        lock=21, stop=-0.12, cap=0.25, log=False):
    n = P.shape[1]
    u = np.zeros(n); cash = 0.0; entry = np.full(n, np.nan); since = np.zeros(n, int); pend = np.zeros(n, bool)
    curve, flows, trades, cost, month = [], [], 0, 0.0, None
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
        for j in np.where((u > 0) & (DIV[i] > 0))[0]: cash += u[j] / LOT[i, j] * DIV[i, j] * (1 - DIVTAX)
        if dates[i][:6] != month:
            add = start if month is None else dep
            cash += add / fx_i * (1 - FXS); flow = add if month is not None else 0.0; cost += add * FXS; month = dates[i][:6]
        s = SIG[i - 1]; pc = PCT[i - 1]; ok = E[i - 1] & ~np.isnan(s) & ~np.isnan(px)
        order = [j for j in np.argsort(-np.where(ok, s, -np.inf)) if ok[j]]
        rank = {j: r for r, j in enumerate(order)}
        swap_day = (not weekly) or i == i0 or dt.date(int(dates[i][:4]), int(dates[i][4:6]), int(dates[i][6:])).weekday() < \
            dt.date(int(dates[i - 1][:4]), int(dates[i - 1][4:6]), int(dates[i - 1][6:])).weekday()
        if swap_day:
            if gap is None:
                for j in np.where(u > 0)[0]:
                    if rank.get(j, 1e9) >= keep * topn and i - since[j] >= lock and not np.isnan(px[j]): sell(j)
            else:
                best = next((pc[j] for j in order[:topn] if u[j] == 0), None)
                for j in np.where(u > 0)[0]:
                    pj = pc[j] if not np.isnan(pc[j]) else 0
                    if rank.get(j, 1e9) >= topn and i - since[j] >= lock and not np.isnan(px[j]) and best is not None and (best - pj) * 100 >= gap: sell(j)
        eq = cash + np.nansum(u * px)
        target = [] if crash[i - 1] else order[:topn]
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
    return np.array(curve), np.array(flows), trades, cost

def main():
    SH = us_all(); tick = sorted(SH)
    with cf.ThreadPoolExecutor(4) as ex: R = list(ex.map(chart, tick))
    keep_ = [k for k, r in enumerate(R) if len(r[0]) > 300]; tick = [tick[k] for k in keep_]; R = [R[k] for k in keep_]
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
    B = ffill(spy[3] or spy[0], dates)
    age = np.cumsum(alive, axis=0); capm = np.nan_to_num(P) * np.array([SH[t] for t in tick])[None, :]
    E = alive & (age >= 253) & (capm >= 5e10)
    def mom(a, b=21):
        m = np.full((T, n), np.nan); m[a:] = P[a - b:T - b] / P[:T - a] - 1; return np.where(E, m, np.nan)
    sigs = {"6-1": mom(126), "3-1": mom(63), "9-1": mom(189), "12-1": mom(252)}
    pcts = {k: rankpct(v) for k, v in sigs.items()}
    SIG = sigs["6-1"]
    crash = np.zeros(T, bool)
    for i in range(272, T):
        s = SIG[i - 20]; ok = ~np.isnan(s) & ~np.isnan(P[i]) & ~np.isnan(P[i - 20])
        if ok.sum() < 20: continue
        q = np.nanpercentile(s[ok], [20, 80]); ret = P[i] / P[i - 20] - 1
        if np.nanmean(ret[ok & (s >= q[1])]) - np.nanmean(ret[ok & (s <= q[0])]) < -0.10: crash[i:i + 6] = True
    crash = crash[:T]
    V = {"지금 규칙 (보유 20위까지)": {}, "보유 10위까지": {"keep": 1.0}, "보유 15위까지": {"keep": 1.5}, "보유 30위까지": {"keep": 3.0},
         "보유 40위까지": {"keep": 4.0}, "교체 점수 차 5점": {"gap": 5}, "교체 점수 차 10점": {"gap": 10}, "교체 점수 차 15점": {"gap": 15},
         "순위 교체 주 1회": {"weekly": True}, "추세 3-1": {"sig": "3-1"}, "추세 9-1": {"sig": "9-1"}, "추세 12-1": {"sig": "12-1"}}
    starts = list(range(260, T - 756, 63))
    res = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "windows": len(starts)}
    for sname, st in (("7만 원 + 매달 10만 원", 70000), ("30만 원 + 매달 10만 원", 300000), ("100만 원 + 매달 10만 원", 1000000)):
        res[sname] = {}; base = None
        for vname, kw in V.items():
            k = kw.get("sig", "6-1"); kw2 = {x: y for x, y in kw.items() if x != "sig"}
            rows = []
            for a in starts:
                b = a + 756
                c, f, tr, cost = run(P, LOT, DIV, alive, E, sigs[k], pcts[k], crash, fx, dates, a, b, st, 100000, **kw2)
                bc, bf = bench(B, fx, dates, a, b, st, 100000); cg, mdd = twr(c, f, dates[a:b])
                rows.append({"cagr": cg, "mdd": mdd, "fin": c[-1], "paid": st + f.sum(), "bfin": bc[-1], "tr": tr / 3, "cost": cost / (st + f.sum())})
            fin = np.array([r["fin"] for r in rows])
            if base is None: base = fin
            med = lambda x: round(float(np.median([r[x] for r in rows])), 2)
            res[sname][vname] = {"연평균": med("cagr"), "가장 나쁜 경우": round(min(r["cagr"] for r in rows), 1), "최대 하락": med("mdd"),
                                 "남은 돈/넣은 돈": round(float(np.median(fin / np.array([r["paid"] for r in rows]))), 2),
                                 "지금 규칙 대비 남은 돈%": round(float(np.median(fin / base - 1) * 100), 1),
                                 "지금 규칙보다 많이 남은 비율%": round(float((fin > base).mean() * 100)),
                                 "S&P500보다 많이 남은 비율%": round(float(np.mean([r["fin"] > r["bfin"] for r in rows]) * 100)),
                                 "1년 거래": round(med("tr")), "비용/넣은 돈%": round(med("cost") * 100, 1)}
            print(sname, vname, res[sname][vname], flush=True)
            json.dump(res, open("pit_us4.json", "w"), ensure_ascii=False, indent=1)
    # year by year, current rule, one long run
    c, f, tr, cost = run(P, LOT, DIV, alive, E, SIG, pcts["6-1"], crash, fx, dates, 260, T, 70000, 100000)
    bc, bf = bench(B, fx, dates, 260, T, 70000, 100000)
    yr = {}
    for y in sorted(set(d[:4] for d in dates[260:T])):
        idx = [k for k, d in enumerate(dates[260:T]) if d[:4] == y]
        if len(idx) < 50: continue
        a, b = idx[0], idx[-1]
        g = lambda cv, fl: float(np.prod([(cv[k] - fl[k]) / cv[k - 1] for k in range(max(a, 1), b + 1) if cv[k - 1] > 0]) - 1)
        yr[y] = {"전략%": round(g(c, f) * 100, 1), "S&P500%": round(g(bc, bf) * 100, 1)}
    res["연도별 (7만 원 + 매달 10만 원, 2017-11부터 계속)"] = yr
    json.dump(res, open("pit_us4.json", "w"), ensure_ascii=False, indent=1)
    print(yr)

if __name__ == "__main__":
    main()
