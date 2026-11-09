"""Search trend-rule settings on ~8 years of Korean daily closes, with an out-of-sample check.
Train on the older ~60% of the period, pick the best settings there, then see how they do on the newer ~40%
that the search never saw. Only price rules are tested (no fundamentals history).
Survivorship bias: today's universe members only, so absolute numbers look better than reality."""
import json, re, datetime as dt, urllib.request, itertools
import concurrent.futures as cf
import numpy as np

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36", "Referer": "https://finance.naver.com/"}
KST = dt.timezone(dt.timedelta(hours=9))
COST = 0.0025

def hist(code, count=2100):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={count}&requestType=0", headers=UA), timeout=25) as r:
            x = r.read().decode("euc-kr", "replace")
    except Exception:
        return {}
    out = {}
    for m in re.findall(r'data="([^"]+)"', x):
        f = m.split("|")
        if float(f[4]) > 0: out[f[0]] = float(f[4])
    return out

def load():
    u = json.load(open("universe.json"))
    codes = list(u["KR"])
    with cf.ThreadPoolExecutor(8) as ex:
        H = dict(zip(codes, ex.map(hist, codes)))
    bench = hist("069500")
    dates = sorted(bench)
    codes = [c for c in codes if len(H[c]) > 300]
    P = np.full((len(dates), len(codes)), np.nan)
    for j, c in enumerate(codes):
        for i, d in enumerate(dates):
            v = H[c].get(d)
            if v: P[i, j] = v
    # forward-fill short gaps (trading halts); leave pre-listing as NaN
    for j in range(P.shape[1]):
        last = np.nan
        for i in range(P.shape[0]):
            if np.isnan(P[i, j]): P[i, j] = last
            else: last = P[i, j]
    B = np.array([bench[d] for d in dates])
    return dates, codes, P, B

def stats(curve, dates):
    curve = np.asarray(curve)
    yrs = (dt.date(int(dates[-1][:4]), int(dates[-1][4:6]), int(dates[-1][6:])) - dt.date(int(dates[0][:4]), int(dates[0][4:6]), int(dates[0][6:]))).days / 365.25
    cagr = (curve[-1] / curve[0]) ** (1 / yrs) - 1
    mdd = float(np.min(curve / np.maximum.accumulate(curve) - 1))
    r = np.diff(curve) / curve[:-1]
    sharpe = float(r.mean() / r.std() * np.sqrt(252)) if r.std() > 0 else 0
    return {"cagr": round(float(cagr) * 100, 1), "mdd": round(mdd * 100, 1), "sharpe": round(sharpe, 2)}

def run(P, dates, i0, i1, look, topn, stop, ma, skip=21):
    """simulate from day i0 to i1; monthly rebalance; returns equity curve"""
    n = P.shape[1]
    pos = np.zeros(n); cash = 1.0; entry = np.full(n, np.nan)
    curve = []; month = None
    for i in range(i0, i1):
        if i > i0:
            r = P[i] / P[i - 1]
            r[np.isnan(r)] = 1.0
            pos *= r
            if stop is not None:
                hit = (pos > 0) & (P[i] / entry - 1 <= stop)
                if hit.any():
                    cash += pos[hit].sum() * (1 - COST); pos[hit] = 0; entry[hit] = np.nan
        v = cash + pos.sum()
        if dates[i][:6] != month:
            month = dates[i][:6]
            a, b = P[i - look], P[i - skip]
            mom = b / a - 1
            ok = ~np.isnan(mom) & ~np.isnan(P[i])
            if ma:
                m200 = np.nanmean(P[i - 199:i + 1], axis=0)
                ok &= P[i] >= m200
            idx = np.where(ok)[0]
            if len(idx):
                pick = idx[np.argsort(-mom[idx])[:topn]]
                new = np.zeros(n); new[pick] = v / len(pick)
                v -= np.abs(new - pos).sum() * COST
                new[pick] = v / len(pick)
                fresh = (pos == 0) & (new > 0)
                entry[fresh] = P[i][fresh]
                entry[new == 0] = np.nan
                pos = new; cash = 0.0
        curve.append(v)
    return curve

def main():
    dates, codes, P, B = load()
    start = 260
    split = start + int((len(dates) - start) * 0.6)
    grid = {"look": [63, 126, 252], "topn": [5, 10, 20], "stop": [None, -0.08, -0.12, -0.15, -0.20], "ma": [False, True]}
    rows = []
    for look, topn, stop, ma in itertools.product(*grid.values()):
        tr = run(P, dates, start, split, look, topn, stop, ma)
        te = run(P, dates, split, len(dates), look, topn, stop, ma)
        rows.append({"look": look, "topn": topn, "stop": stop, "ma": ma,
                     "train": stats(tr, dates[start:split]), "test": stats(te, dates[split:])})
    # pick on the training period only: highest CAGR among settings whose drawdown stayed above -45%
    ok = [r for r in rows if r["train"]["mdd"] > -45] or rows
    ranked = sorted(ok, key=lambda r: -r["train"]["cagr"])
    cur = next(r for r in rows if r["look"] == 252 and r["topn"] == 10 and r["stop"] == -0.12 and r["ma"])
    bt = lambda i0, i1: stats(B[i0:i1], dates[i0:i1])
    test_rank = sorted(rows, key=lambda r: -r["test"]["cagr"])
    out = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"),
           "stocks": len(codes),
           "train": [dates[start], dates[split - 1]], "test": [dates[split], dates[-1]],
           "kospi200": {"train": bt(start, split), "test": bt(split, len(dates))},
           "current": cur, "bestOnTrain": ranked[:8], "bestOnTest_forReference": test_rank[:5],
           "tested": len(rows),
           "avgTest": round(float(np.mean([r["test"]["cagr"] for r in rows])), 1),
           "rankOfTrainWinnerInTest": 1 + [id(r) for r in test_rank].index(id(ranked[0]))}
    json.dump(out, open("optimize.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps({k: out[k] for k in ("train", "test", "kospi200", "current", "rankOfTrainWinnerInTest", "avgTest")}, ensure_ascii=False, indent=1))
    for r in ranked[:8]: print(r)

if __name__ == "__main__":
    main()
