"""Why does the simulation (top 10 names, daily checks) lose so much more than the top-decile factor test?
Monthly-held equal-weight portfolios inside the point-in-time cap>=300 billion universe:
top 10 / top 30 / top decile / 80-90th percentile by 6-1 trend; and the same for a cap>=1 trillion universe.
Plus the trading simulation itself with monthly instead of daily checks, and its trade count."""
import json, numpy as np, datetime as dt
import concurrent.futures as cf
from signals import matrix, sim, twr, KST
from signals8 import hist_kr
from signals10 import listed_caps

def main():
    SH = listed_caps(); codes = sorted(SH)
    with cf.ThreadPoolExecutor(8) as ex: H = list(ex.map(hist_kr, codes))
    keep = [k for k, h in enumerate(H) if len(h[0]) > 60]; codes = [codes[k] for k in keep]; H = [H[k] for k in keep]
    kc, _ = hist_kr("069500"); kd = sorted(kc); K = np.array([kc[d] for d in kd])
    P = matrix([h[0] for h in H], kd); T, n = P.shape
    V = np.zeros(P.shape); alive = np.zeros(P.shape, bool)
    for j, (c, v) in enumerate(H):
        ds = sorted(c)
        for i, d in enumerate(kd):
            if ds[0] <= d <= ds[-1]: alive[i, j] = True; V[i, j] = v.get(d, 0)
    trad = alive & (V > 0); age = np.cumsum(alive, axis=0)
    cap = np.nan_to_num(P) * np.array([SH[c] for c in codes])[None, :]
    months = [i for i in range(1, T) if kd[i][:6] != kd[i - 1][:6] and i >= 260]
    res = {}
    for uname, thr in (("시총 3천억+", 3e11), ("시총 1조+", 1e12)):
        E = alive & (age >= 253) & (cap >= thr)
        groups = {"상위 10개": [], "상위 30개": [], "상위 10%": [], "80~90%": [], "전체 평균": []}
        for a, b in zip(months[:-1], months[1:]):
            i = a - 1; ok = E[i] & ~np.isnan(P[i]) & ~np.isnan(P[b - 1]); r = P[b - 1] / P[a - 1] - 1
            s = np.where(ok, P[i - 21] / P[i - 126] - 1, np.nan); idx = np.argsort(-np.nan_to_num(s, nan=-1e9)); m = int(ok.sum())
            q = np.nanpercentile(s, [80, 90])
            groups["상위 10개"].append(np.nanmean(r[idx[:10]])); groups["상위 30개"].append(np.nanmean(r[idx[:30]]))
            groups["상위 10%"].append(np.nanmean(r[idx[:max(1, m // 10)]])); groups["80~90%"].append(np.nanmean(r[(s >= q[0]) & (s < q[1])]))
            groups["전체 평균"].append(np.nanmean(r[ok]))
        res[uname] = {k: round((np.prod(1 + np.array(v)) ** (12 / len(v)) - 1) * 100, 1) for k, v in groups.items()}
        res[uname]["평균 종목 수"] = int(E.sum(1)[260:].mean())
        # trading sim: monthly vs daily checks, plain 6-1 trend, 3,000,000 won lump sum over the full period
        SIG = np.full(P.shape, np.nan); SIG[126:] = P[105:-21] / P[:-126] - 1; SIG = np.where(E, SIG, np.nan)
        for lab, daily in (("거래 시뮬 · 매달 점검", False), ("거래 시뮬 · 매일 점검", True)):
            c, f, tr, cost = sim(P, kd, list(codes), 260, T, 3000000, 0, kind="mom6", SIG=SIG, buy_mask=E, daily=daily, lock=10, trad=trad, alive=alive)
            t = twr(c, f, kd[260:T]); res[uname][lab] = {"cagr": t["cagr"], "mdd": t["mdd"], "tradesPerYear": round(tr / ((T - 260) / 252)), "costPct": round(cost / 3000000 * 100, 1)}
        print(uname, res[uname], flush=True)
    kk = [K[b - 1] / K[a - 1] - 1 for a, b in zip(months[:-1], months[1:])]
    res["KODEX200"] = round((np.prod(1 + np.array(kk)) ** (12 / len(kk)) - 1) * 100, 1)
    json.dump(res, open("pit_diag2.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
