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
        ban=0, cap=0.25, log=None, tick=None, winkeep=None):
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
            lim = winkeep if (winkeep is not None and px[j] > entry[j]) else keep * topn
            if rank.get(j, 1e9) >= lim and i - since[j] >= lock and not np.isnan(px[j]): sell(j, "rank")
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
        pend = (u > 0) & ~np.isnan(px) & (px / entry - 1 <= stop) if stop is not None else np.zeros(n, bool)
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
    EE = {c: alive & (age >= 253) & (capm >= c) for c in (5e10, 7.5e10, 1e11)}; E = EE[5e10]
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
    V = {"지금 규칙 (3종목)": {"topn": 3}, "2종목": {"topn": 2}, "시총 750억$+": {"topn": 3, "cap_": 7.5e10},
         "시총 1,000억$+": {"topn": 3, "cap_": 1e11}, "수익 중인 종목은 8위까지 보유": {"topn": 3, "winkeep": 8},
         "손절 없음": {"topn": 3, "stop": None}}
    starts = list(range(260, T - 756, 63)); res = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "windows": len(starts)}
    for sname, st in (("7만 원 + 매달 10만 원", 70000), ("30만 원 + 매달 10만 원", 300000), ("100만 원 + 매달 10만 원", 1000000)):
        res[sname] = {}; base = None
        for vname, kw in V.items():
            Eu = EE[kw.get("cap_", 5e10)]; S = np.where(Eu, sig[6], np.nan); kw2 = {x: y for x, y in kw.items() if x not in ("k", "cap_")}
            rows = []
            for a in starts:
                b = a + 756
                c, f, tr = run(P, LOT, DIV, alive, Eu, S, crash, fx, dates, a, b, st, 100000, **kw2)
                bc, bf = bench(B, fx, dates, a, b, st, 100000); cg, mdd = twr(c, f, dates[a:b])
                rows.append({"cagr": cg, "mdd": mdd, "fin": c[-1], "paid": st + f.sum(), "bfin": bc[-1], "tr": tr / 3})
            fin = np.array([r["fin"] for r in rows])
            if base is None: base = fin
            med = lambda x: round(float(np.median([r[x] for r in rows])), 2)
            res[sname][vname] = {"연평균": med("cagr"), "가장 나쁜 경우": round(min(r["cagr"] for r in rows), 1), "최대 하락": med("mdd"),
                                 "지금 규칙 대비 남은 돈%": round(float(np.median(fin / base - 1) * 100), 1),
                                 "지금 규칙보다 많이 남은 비율%": round(float((fin > base).mean() * 100)), "1년 거래": round(med("tr"))}
            print(sname, vname, res[sname][vname], flush=True)
            json.dump(res, open("pit_us7.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
