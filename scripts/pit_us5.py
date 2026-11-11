"""ChatGPT round 6, the two new ideas only (same realistic US replay as pit_us2-4):
 ATR stop: trailing stop at the highest close since buying minus k x 14-day average daily move (close-to-close), k = 3,
           instead of / in addition to the fixed -12% stop
 risk-adjusted trend: 6-1 return divided by 126-day volatility, alone and 50/50 with the plain 6-1 rank"""
import json, datetime as dt
import concurrent.futures as cf
import numpy as np
from signals import KST
from signals6 import rankpct
from pit_us import us_all
from pit_us2 import chart, ffill, twr, bench, FEE, SLIP, FXS, DIVTAX

def run(P, LOT, DIV, alive, E, SIG, crash, fx, dates, i0, i1, start, dep, ATR=None, atr_k=None, fixed=True,
        topn=10, keep=2.0, lock=21, stop=-0.12, cap=0.25):
    n = P.shape[1]
    u = np.zeros(n); cash = 0.0; entry = np.full(n, np.nan); peak = np.full(n, np.nan); since = np.zeros(n, int); pend = np.zeros(n, bool)
    curve, flows, trades, month = [], [], 0, None
    for i in range(i0, i1):
        px = P[i]; fx_i = fx[i]; flow = 0.0
        def sell(j):
            nonlocal cash, trades
            got = u[j] * px[j] * (1 - SLIP); cash += got * (1 - FEE); trades += 1; u[j] = 0; entry[j] = np.nan; peak[j] = np.nan
        for j in np.where((u > 0) & ~alive[i])[0]: sell(j)
        for j in np.where(pend & (u > 0))[0]:
            if not np.isnan(px[j]): sell(j)
        pend[:] = False
        for j in np.where((u > 0) & (DIV[i] > 0))[0]: cash += u[j] / LOT[i, j] * DIV[i, j] * (1 - DIVTAX)
        if dates[i][:6] != month:
            add = start if month is None else dep
            cash += add / fx_i * (1 - FXS); flow = add if month is not None else 0.0; month = dates[i][:6]
        s = SIG[i - 1]; ok = E[i - 1] & ~np.isnan(s) & ~np.isnan(px)
        order = [j for j in np.argsort(-np.where(ok, s, -np.inf)) if ok[j]]
        rank = {j: r for r, j in enumerate(order)}
        for j in np.where(u > 0)[0]:
            if rank.get(j, 1e9) >= keep * topn and i - since[j] >= lock and not np.isnan(px[j]): sell(j)
        eq = cash + np.nansum(u * px)
        target = [] if crash[i - 1] else order[:topn]
        changed = True
        while changed:
            changed = False
            for j in target:
                p1 = LOT[i, j] * px[j] * (1 + SLIP) * (1 + FEE)
                if p1 > cash: continue
                if u[j] > 0 and (u[j] + LOT[i, j]) * px[j] > cap * eq: continue
                if u[j] == 0: entry[j] = px[j]; peak[j] = px[j]; since[j] = i
                cash -= p1; u[j] += LOT[i, j]; trades += 1; changed = True
        held = (u > 0) & ~np.isnan(px)
        peak = np.where(held, np.fmax(peak, px), peak)
        pend = np.zeros(n, bool)
        if fixed: pend |= held & (px / entry - 1 <= stop)
        if atr_k is not None: pend |= held & (px < peak - atr_k * ATR[i])
        curve.append((cash + np.nansum(np.where(u > 0, u * px, 0))) * fx_i); flows.append(flow)
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
    m6 = np.full((T, n), np.nan); m6[126:] = P[105:-21] / P[:-126] - 1; m6 = np.where(E, m6, np.nan)
    d1 = np.abs(np.diff(P, axis=0, prepend=np.nan)); cs = np.nancumsum(d1, axis=0)
    ATR = np.full((T, n), np.nan); ATR[14:] = (cs[14:] - cs[:-14]) / 14
    lr = np.diff(np.log(P), axis=0, prepend=np.nan); vol = np.full((T, n), np.nan)
    for i in range(126, T): vol[i] = np.nanstd(lr[i - 125:i + 1], axis=0)
    radj = np.where(E, m6 / vol, np.nan); mix = 0.5 * rankpct(m6) + 0.5 * rankpct(radj)
    crash = np.zeros(T, bool)
    for i in range(272, T):
        s = m6[i - 20]; ok = ~np.isnan(s) & ~np.isnan(P[i]) & ~np.isnan(P[i - 20])
        if ok.sum() < 20: continue
        q = np.nanpercentile(s[ok], [20, 80]); ret = P[i] / P[i - 20] - 1
        if np.nanmean(ret[ok & (s >= q[1])]) - np.nanmean(ret[ok & (s <= q[0])]) < -0.10: crash[i:i + 6] = True
    crash = crash[:T]
    V = {"지금 규칙": dict(SIG=m6), "변동성 손절 3배 (−12% 대신)": dict(SIG=m6, atr_k=3, fixed=False),
         "변동성 손절 3배 + −12% 둘 다": dict(SIG=m6, atr_k=3), "덜 출렁이며 오른 종목": dict(SIG=radj),
         "지금 점수 반 + 덜 출렁이며 오른 반": dict(SIG=mix)}
    starts = list(range(260, T - 756, 63)); res = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "windows": len(starts)}
    for sname, st in (("7만 원 + 매달 10만 원", 70000), ("30만 원 + 매달 10만 원", 300000), ("100만 원 + 매달 10만 원", 1000000)):
        res[sname] = {}; base = None
        for vname, kw in V.items():
            rows = []
            for a in starts:
                b = a + 756
                c, f, tr = run(P, LOT, DIV, alive, E, kw["SIG"], crash, fx, dates, a, b, st, 100000, ATR=ATR,
                               **{x: y for x, y in kw.items() if x != "SIG"})
                bc, bf = bench(B, fx, dates, a, b, st, 100000); cg, mdd = twr(c, f, dates[a:b])
                rows.append({"cagr": cg, "mdd": mdd, "fin": c[-1], "paid": st + f.sum(), "bfin": bc[-1], "tr": tr / 3})
            fin = np.array([r["fin"] for r in rows])
            if base is None: base = fin
            med = lambda x: round(float(np.median([r[x] for r in rows])), 2)
            res[sname][vname] = {"연평균": med("cagr"), "가장 나쁜 경우": round(min(r["cagr"] for r in rows), 1), "최대 하락": med("mdd"),
                                 "지금 규칙 대비 남은 돈%": round(float(np.median(fin / base - 1) * 100), 1),
                                 "지금 규칙보다 많이 남은 비율%": round(float((fin > base).mean() * 100)), "1년 거래": round(med("tr"))}
            print(sname, vname, res[sname][vname], flush=True)
            json.dump(res, open("pit_us5.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
