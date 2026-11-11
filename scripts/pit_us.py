"""US survivorship check, same idea as the Korean one: candidates = stocks whose past market cap (that day's close x
today's share count) was >= $10B on that day, taken from every NYSE/NASDAQ stock worth >= $2B today. Companies that
went bankrupt or were acquired are still missing (no free history), so this is a lower bound on the bias.
Prints the factor check (top 10 / 30 / decile by 6-1 trend, held a month) and the trading simulation."""
import json, time, datetime as dt, urllib.request
import concurrent.futures as cf
import numpy as np
from signals import matrix, sim, twr, KST
from signals8 import hist_us
from signals9 import get

def us_all(min_cap=2e9):
    out = {}
    for ex in ("NYSE", "NASDAQ"):
        for page in range(1, 40):
            try: d = json.loads(get(f"https://api.stock.naver.com/stock/exchange/{ex}/marketValue?page={page}&pageSize=100"))
            except Exception: time.sleep(2); continue
            xs = d.get("stocks") or []
            if not xs: break
            stop = False
            for s in xs:
                try:
                    cap = float(str(s.get("marketValue")).replace(",", "")) * 1000; px = float(str(s.get("closePrice")).replace(",", ""))
                except Exception: continue
                if cap < min_cap: stop = True; break
                if s.get("stockEndType") != "stock" or px <= 0: continue
                t = s.get("symbolCode") or s.get("reutersCode")
                if t: out[t] = cap / px
            if stop: break
            time.sleep(0.3)
    return out

def main():
    u = json.load(open("universe.json")); today = set(u.get("US", {}))
    SH = us_all(); tick = sorted(SH)
    print("tickers", len(tick), flush=True)
    with cf.ThreadPoolExecutor(4) as ex: H = list(ex.map(hist_us, tick))
    keep = [k for k, h in enumerate(H) if len(h[0]) > 300]; tick = [tick[k] for k in keep]; H = [H[k] for k in keep]
    sc, _ = hist_us("SPLG")
    if len(sc) < 600: sc, _ = hist_us("SPY")
    dates = sorted(d for d in sc if d >= "20160101"); B = np.array([sc[d] for d in dates])
    P = matrix([h[0] for h in H], dates); T, n = P.shape
    alive = np.zeros(P.shape, bool)
    for j, (c, v) in enumerate(H):
        ds = sorted(c)
        for i, d in enumerate(dates):
            if ds[0] <= d <= ds[-1]: alive[i, j] = True
    age = np.cumsum(alive, axis=0)
    cap = np.nan_to_num(P) * np.array([SH[t] for t in tick])[None, :]
    surv = alive & np.isin(np.array(tick), list(today))[None, :] & (age >= 253)
    pit = alive & (age >= 253) & (cap >= 1e10)
    months = [i for i in range(1, T) if dates[i][:6] != dates[i - 1][:6] and i >= 260]
    res = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "tickers": n}
    for uname, E in (("오늘 300개 (이전)", surv), ("그날 시총 100억 달러+", pit)):
        g = {"상위 10개": [], "상위 30개": [], "상위 10%": [], "전체 평균": []}
        for a, b in zip(months[:-1], months[1:]):
            i = a - 1; ok = E[i] & ~np.isnan(P[i]) & ~np.isnan(P[b - 1]); r = P[b - 1] / P[a - 1] - 1
            s = np.where(ok, P[i - 21] / P[i - 126] - 1, np.nan); idx = np.argsort(-np.nan_to_num(s, nan=-1e9)); m = int(ok.sum())
            g["상위 10개"].append(np.nanmean(r[idx[:10]])); g["상위 30개"].append(np.nanmean(r[idx[:30]]))
            g["상위 10%"].append(np.nanmean(r[idx[:max(1, m // 10)]])); g["전체 평균"].append(np.nanmean(r[ok]))
        out = {k: round((np.prod(1 + np.array(v)) ** (12 / len(v)) - 1) * 100, 1) for k, v in g.items()}
        out["평균 종목 수"] = int(E.sum(1)[260:].mean())
        SIG = np.full(P.shape, np.nan); SIG[126:] = P[105:-21] / P[:-126] - 1; SIG = np.where(E, SIG, np.nan)
        c, f, tr, cost = sim(P, dates, list(tick), 260, T, 2200, 0, kind="mom6", SIG=SIG, buy_mask=E, daily=True, lock=21,
                             buyc=0.0025, sellc=0.0025, alive=alive)
        t = twr(c, f, dates[260:T]); out["거래 시뮬 · 매일 점검 ($2,200)"] = {"cagr": t["cagr"], "mdd": t["mdd"]}
        res[uname] = out; print(uname, out, flush=True)
    bb = [B[b - 1] / B[a - 1] - 1 for a, b in zip(months[:-1], months[1:])]
    res["S&P500"] = round((np.prod(1 + np.array(bb)) ** (12 / len(bb)) - 1) * 100, 1)
    json.dump(res, open("pit_us.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
