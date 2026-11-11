"""Diagnostics for signals9: is the bad result real or a bug?
1) equal-weight return of each universe (all eligible stocks, rebalanced monthly)
2) pure factor test: each month sort the universe by 6-1 trend into 10 groups, average next-month return per group
3) the same with a steadier universe: 1-year average trading value top 250, and a 'big' universe top 100"""
import json, numpy as np, datetime as dt
import concurrent.futures as cf
from signals import matrix, KST
from signals8 import hist_kr
from signals9 import listed, delisted

def main():
    u = json.load(open("universe.json")); today = list(u["KR"])
    codes = sorted(set(listed()) | set(delisted()) | set(today))
    with cf.ThreadPoolExecutor(8) as ex: H = list(ex.map(hist_kr, codes))
    keep = [k for k, h in enumerate(H) if len(h[0]) > 60]; codes = [codes[k] for k in keep]; H = [H[k] for k in keep]
    kc, _ = hist_kr("069500"); kd = sorted(kc); K = np.array([kc[d] for d in kd])
    P = matrix([h[0] for h in H], kd); T, n = P.shape
    V = np.zeros(P.shape); alive = np.zeros(P.shape, bool)
    for j, (c, v) in enumerate(H):
        ds = sorted(c)
        for i, d in enumerate(kd):
            if ds[0] <= d <= ds[-1]: alive[i, j] = True; V[i, j] = v.get(d, 0)
    tv = np.where(alive, np.nan_to_num(P) * V, 0); cs = np.cumsum(tv, axis=0); age = np.cumsum(alive, axis=0)
    def top(win, N):
        a = np.zeros(P.shape); a[win:] = (cs[win:] - cs[:-win]) / win; E = np.zeros(P.shape, bool)
        for i in range(T):
            ok = alive[i] & (age[i] >= 253)
            if ok.sum() < N: continue
            th = np.sort(a[i][ok])[::-1][N - 1]; E[i] = ok & (a[i] >= th)
        return E
    U = {"오늘 대형주 200 (이전)": alive & np.isin(np.array(codes), today)[None, :] & (age >= 253),
         "그날 거래 상위 250 (60일)": top(60, 250), "그날 거래 상위 250 (1년)": top(250, 250), "그날 거래 상위 100 (1년)": top(250, 100)}
    months = [i for i in range(1, T) if kd[i][:6] != kd[i - 1][:6] and i >= 260]
    res = {"stocks": n, "months": len(months)}
    for name, E in U.items():
        ew = []; dec = [[] for _ in range(10)]
        for a, b in zip(months[:-1], months[1:]):
            i = a - 1; ok = E[i] & ~np.isnan(P[i]) & ~np.isnan(P[b - 1])
            # next-month return; a stock that delists inside the month ends at its last price
            r = P[b - 1] / P[a - 1] - 1
            ew.append(np.nanmean(r[ok]))
            s = P[i - 21] / P[i - 126] - 1; ok2 = ok & ~np.isnan(s)
            if ok2.sum() < 50: continue
            qs = np.nanpercentile(s[ok2], np.arange(10, 100, 10)); g = np.digitize(s, qs)
            for k in range(10): dec[k].append(np.nanmean(r[ok2 & (g == k)]))
        yrs = len(ew) / 12
        res[name] = {"ewCagr": round((np.prod(1 + np.array(ew)) ** (1 / yrs) - 1) * 100, 1),
                     "decileMonthlyPct": [round(float(np.mean(x)) * 100, 2) for x in dec],
                     "topMinusBottom": round(float(np.mean(dec[9]) - np.mean(dec[0])) * 100, 2),
                     "topDecileCagr": round((np.prod(1 + np.array(dec[9])) ** (12 / len(dec[9])) - 1) * 100, 1)}
        print(name, res[name], flush=True)
    kk = [K[b - 1] / K[a - 1] - 1 for a, b in zip(months[:-1], months[1:])]
    res["KODEX200Cagr"] = round((np.prod(1 + np.array(kk)) ** (12 / len(kk)) - 1) * 100, 1)
    json.dump(res, open("pit_diag.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
