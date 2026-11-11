"""Round 10: the page's own rule for the candidate list (market cap >= 300 billion won), rebuilt for each past day.
Past market cap = that day's close x today's share count (KRX history needs a login). Covers every stock listed today,
so stocks that were small then and grew later only enter once they actually crossed the line. Companies delisted
since 2018 have no share count, so they are left out here (round 9 covered them with a trading-value list).
Also prints the factor check (10 trend groups, next-month return) for this universe."""
import json, re, time, datetime as dt
import concurrent.futures as cf
import numpy as np
from signals import matrix, KST
from signals4 import evaluate
from signals8 import hist_kr
from signals9 import get, build

def listed_caps():
    out = {}
    for mk in ("KOSPI", "KOSDAQ"):
        for page in range(1, 40):
            try: d = json.loads(get(f"https://m.stock.naver.com/api/stocks/marketValue/{mk}?page={page}&pageSize=100"))
            except Exception: time.sleep(2); continue
            xs = d.get("stocks") or []
            if not xs: break
            for s in xs:
                code, name = s.get("itemCode") or "", s.get("stockName") or ""
                if s.get("stockEndType") != "stock" or not code.endswith("0") or "스팩" in name or re.search(r"우[BC]?$", name): continue
                try:
                    cap = float(str(s.get("marketValue")).replace(",", "")) * 1e8; px = float(str(s.get("closePrice")).replace(",", ""))
                    if px > 0: out[code] = cap / px
                except Exception: pass
            time.sleep(0.2)
    return out

def main():
    u = json.load(open("universe.json")); today = list(u["KR"])
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
    shares = np.array([SH[c] for c in codes])
    cap = np.nan_to_num(P) * shares[None, :]
    pitcap = alive & (age >= 253) & (cap >= 3e11)
    surv = alive & np.isin(np.array(codes), today)[None, :] & (age >= 253)
    res = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "stocks": n,
           "avgUniverse": {"survivor": round(float(surv.sum(1)[260:].mean())), "pitCap": round(float(pitcap.sum(1)[260:].mean()))}}
    # factor check
    months = [i for i in range(1, T) if kd[i][:6] != kd[i - 1][:6] and i >= 260]
    res["factor"] = {}
    for name, E in (("오늘 대형주 200 (이전)", surv), ("그날 시가총액 3천억 이상", pitcap)):
        ew = []; dec = [[] for _ in range(10)]
        for a, b in zip(months[:-1], months[1:]):
            i = a - 1; ok = E[i] & ~np.isnan(P[i]) & ~np.isnan(P[b - 1]); r = P[b - 1] / P[a - 1] - 1
            ew.append(np.nanmean(r[ok])); s = P[i - 21] / P[i - 126] - 1; ok2 = ok & ~np.isnan(s)
            qs = np.nanpercentile(s[ok2], np.arange(10, 100, 10)); g = np.digitize(s, qs)
            for k in range(10): dec[k].append(np.nanmean(r[ok2 & (g == k)]))
        res["factor"][name] = {"ewCagr": round((np.prod(1 + np.array(ew)) ** (12 / len(ew)) - 1) * 100, 1),
                               "decileMonthlyPct": [round(float(np.mean(x)) * 100, 2) for x in dec],
                               "topDecileCagr": round((np.prod(1 + np.array(dec[9])) ** (12 / len(dec[9])) - 1) * 100, 1)}
        print(name, res["factor"][name], flush=True)
    out = {}
    for uname, E in (("오늘 대형주 200개를 과거에도 사용 (이전 방식)", surv), ("그날 시가총액 3천억 이상 (상장폐지 제외)", pitcap)):
        R = build(P, V, K, E, 10)
        for v in R.values(): v["trad"] = trad; v["alive"] = alive
        out[uname] = {}
        for lab, st, dp in (("7만 원 + 매달 10만 원", 70000, 100000), ("300만 원", 3000000, 0), ("1000만 원", 10000000, 0)):
            out[uname][lab], res["span"] = evaluate(P, kd, list(codes), K, "mom6", st, dp, {}, R)
            res["KR"] = out; json.dump(res, open("signals10.json", "w"), ensure_ascii=False, indent=1)
    json.dump(res, open("signals10.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
