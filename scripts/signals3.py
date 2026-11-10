"""Round 3: how long should a new buy be protected from rank-based swaps?
The page checks every day, so this simulates daily checks with a lock of 0 / 7 / 14 / 30 calendar days
(0 / 5 / 10 / 21 trading days) on rank swaps. Stop-loss always applies. Also shows the old monthly re-ranking.
Korea uses the 52-week-high trend, the US uses 6-month return skipping the last month (current page rules)."""
import json, datetime as dt
import concurrent.futures as cf
import numpy as np
from signals import hist, matrix, KST
from signals2 import yahoo, run_set

LOCKS = {"매일 점검 · 잠금 없음": 0, "매일 점검 · 7일 잠금": 5, "매일 점검 · 14일 잠금 (지금)": 10, "매일 점검 · 30일 잠금": 21}

def variants(kind):
    v = {"한 달에 한 번 교체": {"kind": kind}}
    for nm, k in LOCKS.items(): v[nm] = {"kind": kind, "daily": True, "lock": k}
    return v

def main():
    u = json.load(open("universe.json"))
    res = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds")}
    # Korea
    codes = list(u["KR"])
    with cf.ThreadPoolExecutor(8) as ex: KH = list(ex.map(hist, codes))
    keep = [k for k, h in enumerate(KH) if len(h) > 300]
    codes = [codes[k] for k in keep]; KH = [KH[k] for k in keep]
    k200 = hist("069500"); kd = sorted(k200)
    KP = matrix(KH, kd); K = np.array([k200[d] for d in kd])
    ksec = [u["KR"][c]["sector"] for c in codes]
    r1, p1 = run_set(KP, kd, ksec, 70000, 100000, variants("high52"), M=K, bench=("KODEX 200 적립", K))
    r2, _ = run_set(KP, kd, ksec, 3000000, 0, variants("high52"), M=K, bench=("KODEX 200 적립", K))
    res["KR"] = {"stocks": len(codes), "periods": p1, "7만 원 + 매달 10만 원": r1, "300만 원": r2}
    json.dump(res, open("signals3.json", "w"), ensure_ascii=False, indent=1)
    # US
    ust = list(u.get("US", {}))
    with cf.ThreadPoolExecutor(3) as ex: UH = list(ex.map(yahoo, ust))
    keep = [k for k, h in enumerate(UH) if len(h) > 600]
    ust = [ust[k] for k in keep]; UH = [UH[k] for k in keep]
    spy = yahoo("SPLG") or yahoo("SPY")
    if len(spy) > 600:
        dates = sorted(d for d in spy if d >= "20160101")
        P = matrix(UH, dates); B = np.array([spy[d] for d in dates])
        sec = [u["US"][t]["sector"] for t in ust]
        c = dict(buyc=0.0025, sellc=0.0025)
        r3, p3 = run_set(P, dates, sec, 50, 70, variants("mom6"), M=B, bench=("S&P500 적립", B), **c)
        r4, _ = run_set(P, dates, sec, 2200, 0, variants("mom6"), M=B, bench=("S&P500 적립", B), **c)
        res["US"] = {"stocks": len(ust), "periods": p3, "$50 + 매달 $70": r3, "$2,200 (약 300만 원)": r4}
    res["notes"] = "상위 10종목 · 손절 −12%(잠금과 상관없이 적용) · 다음 날 체결 · 1주 단위 · 수수료·거래세 · 현재 후보만 사용(생존 편향)"
    json.dump(res, open("signals3.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
