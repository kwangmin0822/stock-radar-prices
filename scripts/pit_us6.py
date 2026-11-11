"""ChatGPT round 7, one change at a time on the realistic US replay (pit_us2-5):
holdings 3/5/7/10, stop -8/-12/-16%, re-buy ban 0/15/30 days after a sale, trend window 4/5/6/7/8 months (skip 1).
Plus diagnostics from one long run (2017-11 ->, 70,000 won + 100,000 won a month): profit by purchase rank (1-3, 4-10,
11+) and the stocks that made the 2020 return."""
import json, datetime as dt
import concurrent.futures as cf
import numpy as np
from signals import KST
from pit_us import us_all
from pit_us2 import chart, ffill, twr, bench, FEE, SLIP, FXS, DIVTAX

def run(P, LOT, DIV, alive, E, SIG, crash, fx, dates, i0, i1, start, dep, topn=10, keep=2.0, lock=21, stop=-0.12,
        ban=0, cap=0.25, log=None, tick=None):
    n = P.shape[1]
    u = np.zeros(n); cash = 0.0; entry = np.full(n, np.nan); since = np.zeros(n, int); pend = np.zeros(n, bool)
    sold_at = np.full(n, -10**9); cost_usd = np.zeros(n); erank = np.zeros(n, int); edate = [""] * n
    curve, flows, trades, month = [], [], 0, None
    for i in range(i0, i1):
        px = P[i]; fx_i = fx[i]; flow = 0.0
        def sell(j, why):
            nonlocal cash, trades
            got = u[j] * px[j] * (1 - SLIP) * (1 - FEE); cash += got; trades += 1
            if log is not None: log.append({"t": tick[j], "rank": int(erank[j]), "buy": edate[j], "sell": dates[i], "pnl": got - cost_usd[j], "why": why})
            u[j] = 0; entry[j] = np.nan; sold_at[j] = i; cost_usd[j] = 0
        for j in np.where((u > 0) & ~alive[i])[0]: sell(j, "delist")
        for j in np.where(pend & (u > 0))[0]:
            if not np.isnan(px[j]): sell(j, "stop")
        pend[:] = False
        for j in np.where((u > 0) & (DIV[i] > 0))[0]:
            d = u[j] / LOT[i, j] * DIV[i, j] * (1 - DIVTAX); cash += d; cost_usd[j] -= d
        if dates[i][:6] != month:
            add = start if month is None else dep
            cash += add / fx_i * (1 - FXS); flow = add if month is not None else 0.0; month = dates[i][:6]
        s = SIG[i - 1]; ok = E[i - 1] & ~np.isnan(s) & ~np.isnan(px)
        order = [j for j in np.argsort(-np.where(ok, s, -np.inf)) if ok[j]]
        rank = {j: r for r, j in enumerate(order)}
        for j in np.where(u > 0)[0]:
            if rank.get(j, 1e9) >= keep * topn and i - since[j] >= lock and not np.isnan(px[j]): sell(j, "rank")
        eq = cash + np.nansum(u * px)
        target = [] if crash[i - 1] else [j for j in order[:topn] if u[j] > 0 or i - sold_at[j] >= ban]
        changed = True
        while changed:
            changed = False
            for j in target:
                p1 = LOT[i, j] * px[j] * (1 + SLIP) * (1 + FEE)
                if p1 > cash: continue
                if u[j] > 0 and (u[j] + LOT[i, j]) * px[j] > cap * eq: continue
                if u[j] == 0: entry[j] = px[j]; since[j] = i; erank[j] = rank[j] + 1; edate[j] = dates[i]
                cash -= p1; cost_usd[j] += p1; u[j] += LOT[i, j]; trades += 1; changed = True
        pend = (u > 0) & ~np.isnan(px) & (px / entry - 1 <= stop)
        curve.append((cash + np.nansum(np.where(u > 0, u * px, 0))) * fx_i); flows.append(flow)
    if log is not None:
        for j in np.where(u > 0)[0]:
            log.append({"t": tick[j], "rank": int(erank[j]), "buy": edate[j], "sell": "open", "pnl": u[j] * P[i1 - 1, j] - cost_usd[j], "why": "open"})
    return np.array(curve), np.array(flows), trades

def main():
    SH = us_all(); tick = sorted(SH)
    with cf.ThreadPoolExecutor(4) as ex: R = list(ex.map(chart, tick))
    k_ = [k for k, r in enumerate(R) if len(r[0]) > 300]; tick = [tick[k] for k in k_]; R = [R[k] for k in k_]
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
    fx = ffill(fxh, dates); fx = np.where(np.isnan(fx), np.nanmean(fx), fx); B = ffill(spy[3] or spy[0], dates)
    age = np.cumsum(alive, axis=0); capm = np.nan_to_num(P) * np.array([SH[t] for t in tick])[None, :]
    E = alive & (age >= 253) & (capm >= 5e10)
    def mom(a):
        m = np.full((T, n), np.nan); m[a:] = P[a - 21:T - 21] / P[:T - a] - 1; return np.where(E, m, np.nan)
    sig = {k: mom(21 * k) for k in (4, 5, 6, 7, 8)}
    m6 = sig[6]
    crash = np.zeros(T, bool)
    for i in range(272, T):
        s = m6[i - 20]; ok = ~np.isnan(s) & ~np.isnan(P[i]) & ~np.isnan(P[i - 20])
        if ok.sum() < 20: continue
        q = np.nanpercentile(s[ok], [20, 80]); ret = P[i] / P[i - 20] - 1
        if np.nanmean(ret[ok & (s >= q[1])]) - np.nanmean(ret[ok & (s <= q[0])]) < -0.10: crash[i:i + 6] = True
    crash = crash[:T]
    V = {"지금 규칙 (10종목·−12%·재매수 제한 없음·6개월)": {}, "3종목": {"topn": 3}, "5종목": {"topn": 5}, "7종목": {"topn": 7},
         "손절 −8%": {"stop": -0.08}, "손절 −16%": {"stop": -0.16}, "재매수 금지 15일": {"ban": 10}, "재매수 금지 30일 (페이지)": {"ban": 21},
         "추세 4개월": {"k": 4}, "추세 5개월": {"k": 5}, "추세 7개월": {"k": 7}, "추세 8개월": {"k": 8}}
    starts = list(range(260, T - 756, 63)); res = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "windows": len(starts)}
    for sname, st in (("7만 원 + 매달 10만 원", 70000), ("30만 원 + 매달 10만 원", 300000), ("100만 원 + 매달 10만 원", 1000000)):
        res[sname] = {}; base = None
        for vname, kw in V.items():
            S = sig[kw.get("k", 6)]; kw2 = {x: y for x, y in kw.items() if x != "k"}
            rows = []
            for a in starts:
                b = a + 756
                c, f, tr = run(P, LOT, DIV, alive, E, S, crash, fx, dates, a, b, st, 100000, **kw2)
                bc, bf = bench(B, fx, dates, a, b, st, 100000); cg, mdd = twr(c, f, dates[a:b])
                rows.append({"cagr": cg, "mdd": mdd, "fin": c[-1], "paid": st + f.sum(), "bfin": bc[-1], "tr": tr / 3})
            fin = np.array([r["fin"] for r in rows])
            if base is None: base = fin
            med = lambda x: round(float(np.median([r[x] for r in rows])), 2)
            res[sname][vname] = {"연평균": med("cagr"), "가장 나쁜 경우": round(min(r["cagr"] for r in rows), 1), "최대 하락": med("mdd"),
                                 "지금 규칙 대비 남은 돈%": round(float(np.median(fin / base - 1) * 100), 1),
                                 "지금 규칙보다 많이 남은 비율%": round(float((fin > base).mean() * 100)), "1년 거래": round(med("tr"))}
            print(sname, vname, res[sname][vname], flush=True)
            json.dump(res, open("pit_us6.json", "w"), ensure_ascii=False, indent=1)
    # diagnostics: one long run
    log = []
    run(P, LOT, DIV, alive, E, m6, crash, fx, dates, 260, T, 70000, 100000, log=log, tick=tick)
    by = {}
    for g, lo, hi in (("1~3위로 산 종목", 1, 3), ("4~10위로 산 종목", 4, 10), ("11위 이하", 11, 10**9)):
        xs = [x["pnl"] for x in log if lo <= x["rank"] <= hi]
        by[g] = {"건수": len(xs), "손익 합계 $": round(sum(xs), 1), "이익 본 비율%": round(100 * np.mean([x > 0 for x in xs]), 0) if xs else None}
    res["순위별 손익 (2017-11부터, 7만 원 + 매달 10만 원)"] = by
    y2020 = {}
    for x in log:
        if x["sell"] != "open" and x["sell"][:4] == "2020" or x["buy"][:4] == "2020":
            y2020[x["t"]] = y2020.get(x["t"], 0) + x["pnl"]
    top = sorted(y2020.items(), key=lambda kv: -kv[1])
    res["2020년 손익 상위 종목 $"] = [[t, round(v, 1)] for t, v in top[:8]]
    res["2020년 손익 합계 $"] = round(sum(y2020.values()), 1)
    why = {}
    for x in log: why.setdefault(x["why"], []).append(x["pnl"])
    res["매도 이유별 손익 $"] = {k: {"건수": len(v), "합계": round(sum(v), 1)} for k, v in why.items()}
    json.dump(res, open("pit_us6.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: res[k] for k in ("순위별 손익 (2017-11부터, 7만 원 + 매달 10만 원)", "2020년 손익 상위 종목 $", "2020년 손익 합계 $", "매도 이유별 손익 $")}, ensure_ascii=False))

if __name__ == "__main__":
    main()
