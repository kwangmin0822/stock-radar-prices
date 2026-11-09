"""Round 2 of realistic tests (same simulator as signals.py):
A) US universe: does the 52-week-high signal work there too? (Yahoo daily closes, USD account, 0.25% fee per side, no tax)
B) Korean market filter: no new buys while KODEX 200 is under its 200-day average
C) Re-ranking cadence: every month vs every quarter
Each is checked in an older and a newer half."""
import json, time, datetime as dt, urllib.request, urllib.parse
import concurrent.futures as cf
import numpy as np
from signals import hist, matrix, sim, etf, twr, KST

YUA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"}

def yahoo(t):
    for i in range(3):
        try:
            u = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(t.replace('.', '-'))}?interval=1d&range=10y"
            with urllib.request.urlopen(urllib.request.Request(u, headers=YUA), timeout=25) as r:
                d = json.loads(r.read())["chart"]["result"][0]
            ts = d["timestamp"]; cl = d["indicators"]["quote"][0]["close"]
            return {dt.datetime.utcfromtimestamp(a).strftime("%Y%m%d"): c for a, c in zip(ts, cl) if c}
        except Exception:
            time.sleep(1 + 2 * i)
    return {}

def halves(n, s0=260):
    mid = s0 + (n - s0) // 2
    return {"앞": (s0, mid), "뒤": (mid, n)}

def run_set(P, dates, sectors, start, dep, variants, M=None, bench=None, **kw):
    out = {}
    H = halves(len(dates))
    for nm, extra in variants.items():
        out[nm] = {}
        for h, (a, b) in H.items():
            c, f, tr, cost = sim(P, dates, sectors, a, b, start, dep, M=M, **{**kw, **extra})
            out[nm][h] = {**twr(c, f, dates[a:b]), "trades": tr}
    if bench is not None:
        out[bench[0]] = {}
        for h, (a, b) in H.items():
            c, f = etf(bench[1], dates, a, b, start, dep)
            out[bench[0]][h] = twr(c, f, dates[a:b])
    return out, {h: [dates[a], dates[b - 1]] for h, (a, b) in H.items()}

def main():
    u = json.load(open("universe.json"))
    res = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds")}

    # ---- A) US ----
    ust = list(u.get("US", {}))
    with cf.ThreadPoolExecutor(6) as ex:
        UH = list(ex.map(yahoo, ust))
    keep = [k for k, h in enumerate(UH) if len(h) > 600]
    ust = [ust[k] for k in keep]; UH = [UH[k] for k in keep]
    spy = yahoo("SPLG")
    dates = sorted(d for d in spy if d >= "20160101")
    P = matrix(UH, dates); B = np.array([spy[d] for d in dates])
    sec = [u["US"][t]["sector"] for t in ust]
    us_cost = dict(buyc=0.0025, sellc=0.0025)
    variants = {"52주 신고가 근접": {"kind": "high52"}, "6개월 추세": {"kind": "mom6"}}
    r1, p1 = run_set(P, dates, sec, 50, 70, variants, M=B, bench=("SPLG(S&P500) 적립", B), **us_cost)
    r2, _ = run_set(P, dates, sec, 2200, 0, variants, M=B, bench=("SPLG(S&P500) 적립", B), **us_cost)
    res["US"] = {"stocks": len(ust), "periods": p1, "$50 + 매달 $70": r1, "$2,200 (약 300만 원)": r2}

    # ---- B, C) Korea ----
    codes = list(u["KR"])
    with cf.ThreadPoolExecutor(8) as ex:
        KH = list(ex.map(hist, codes))
    keep = [k for k, h in enumerate(KH) if len(h) > 300]
    codes = [codes[k] for k in keep]; KH = [KH[k] for k in keep]
    k200 = hist("069500"); kd = sorted(k200)
    KP = matrix(KH, kd); K = np.array([k200[d] for d in kd])
    ma = np.array([K[max(0, i - 199):i + 1].mean() for i in range(len(K))])
    up = K >= ma
    ksec = [u["KR"][c]["sector"] for c in codes]
    kv = {"52주 신고가 (지금)": {"kind": "high52"},
          "+ 하락장엔 신규 매수 중단": {"kind": "high52", "buy_ok": up},
          "분기마다 교체": {"kind": "high52", "months": {1, 4, 7, 10}},
          "분기 교체 + 하락장 매수 중단": {"kind": "high52", "months": {1, 4, 7, 10}, "buy_ok": up}}
    r3, p3 = run_set(KP, kd, ksec, 70000, 100000, kv, M=K, bench=("KODEX 200 적립", K))
    r4, _ = run_set(KP, kd, ksec, 3000000, 0, kv, M=K, bench=("KODEX 200 적립", K))
    res["KR"] = {"stocks": len(codes), "periods": p3, "7만 원 + 매달 10만 원": r3, "300만 원": r4,
                 "marketUpShare": round(float(up[260:].mean()) * 100, 1)}
    res["notes"] = "상위 10종목 · 손절 −12% · 다음 날 체결 · 1주 단위 · 한국 수수료+거래세, 미국 수수료 0.25% · 현재 후보만 사용(생존 편향)"
    json.dump(res, open("signals2.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
