"""Round 4: robust comparison. Instead of one older/newer split (which moved by 10+ points when the start shifted a day),
run every rule over many overlapping 3-year windows that start every ~2 months, and compare the median result and how
often each rule beat simply buying the index with the same money. Daily checks like the page, 14-day swap lock unless noted."""
import json, datetime as dt
import concurrent.futures as cf
import numpy as np
from signals import hist, matrix, sim, etf, twr, signal, KST
from signals2 import yahoo

WIN, STEP, S0 = 756, 42, 260

def precompute(P, kind, M=None):
    S = np.full(P.shape, np.nan)
    for i in range(252, P.shape[0]): S[i] = signal(P, i, kind, M)
    return S

def rules(base):
    other = "mom6" if base == "high52" else "high52"
    return {
        "지금 규칙": {},
        "30일 잠금": {"lock": 21},
        "종목 5개": {"topn": 5},
        "종목 15개": {"topn": 15},
        "손절 −20%": {"stop": -0.20},
        "손절 없음": {"stop": None},
        "순위 3배 밖으로 밀려야 매도": {"keep": 3},
        "순위 1.5배 밖이면 매도": {"keep": 1.5},
        ("6개월 추세" if other == "mom6" else "52주 신고가 근접"): {"kind": other},
        "두 추세 섞기": {"kind": "mom6+high52"},
        "하락장엔 새로 안 사기": {"filter": True},
    }

def evaluate(P, dates, sec, M, base, start, dep, cost, R=None):
    sigs = {k: precompute(P, k, M) for k in ("high52", "mom6", "mom6+high52")}
    ma = np.array([M[max(0, i - 199):i + 1].mean() for i in range(len(M))]); up = M >= ma
    starts = list(range(S0, len(dates) - WIN, STEP))
    out = {}
    bench = [twr(*etf(M, dates, a, a + WIN, start, dep), dates[a:a + WIN]) for a in starts]
    for nm, ov in (R or rules(base)).items():
        kind = ov.get("kind", base)
        kw = dict(kind=kind, SIG=ov["SIG"] if "SIG" in ov else sigs[kind], daily=True, lock=ov.get("lock", 10), topn=ov.get("topn", 10),
                  stop=ov.get("stop", -0.12), keep=ov.get("keep", 2), buy_ok=up if ov.get("filter") else None,
                  buy_mask=ov.get("mask"), volctl=ov.get("volctl", False), **{**cost, **ov.get("cost", {})})
        rs = []
        for a in starts:
            c, f, tr, _ = sim(P, dates, sec, a, a + WIN, start, dep, M=M, **kw)
            rs.append({**twr(c, f, dates[a:a + WIN]), "trades": tr})
        cg = np.array([r["cagr"] for r in rs]); bg = np.array([b["cagr"] for b in bench])
        out[nm] = {"median": round(float(np.median(cg)), 1), "worst": round(float(cg.min()), 1),
                   "beatIndexPct": round(float((cg > bg).mean() * 100)), "medianVsIndex": round(float(np.median(cg - bg)), 1),
                   "medianEarly": round(float(np.median(cg[:len(cg) // 2])), 1), "medianLate": round(float(np.median(cg[len(cg) // 2:])), 1),
                   "medianMdd": round(float(np.median([r["mdd"] for r in rs])), 1),
                   "calmar": round(float(np.median([r["cagr"] / abs(r["mdd"]) if r["mdd"] else 0 for r in rs])), 2),
                   "tradesPerYear": round(float(np.mean([r["trades"] for r in rs])) / 3)}
        print(nm, out[nm], flush=True)
    bg = [b["cagr"] for b in bench]
    out["지수 적립"] = {"median": round(float(np.median(bg)), 1), "medianEarly": round(float(np.median(bg[:len(bg) // 2])), 1), "medianLate": round(float(np.median(bg[len(bg) // 2:])), 1), "worst": round(float(min(bg)), 1),
                    "medianMdd": round(float(np.median([b["mdd"] for b in bench])), 1)}
    return out, {"windows": len(starts), "first": dates[starts[0]], "last": dates[starts[-1] + WIN - 1]}

def main():
    u = json.load(open("universe.json"))
    res = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "windowYears": 3}
    codes = list(u["KR"])
    with cf.ThreadPoolExecutor(8) as ex: KH = list(ex.map(hist, codes))
    keep = [k for k, h in enumerate(KH) if len(h) > 300]
    codes = [codes[k] for k in keep]; KH = [KH[k] for k in keep]
    k200 = hist("069500"); kd = sorted(k200)
    KP = matrix(KH, kd); K = np.array([k200[d] for d in kd]); ks = [u["KR"][c]["sector"] for c in codes]
    res["KR"] = {"stocks": len(codes)}
    for lab, st, dp in (("7만 원 + 매달 10만 원", 70000, 100000), ("300만 원", 3000000, 0)):
        print("KR", lab, flush=True)
        res["KR"][lab], res["KR"]["span"] = evaluate(KP, kd, ks, K, "high52", st, dp, {})
        json.dump(res, open("signals4.json", "w"), ensure_ascii=False, indent=1)
    ust = list(u.get("US", {}))
    with cf.ThreadPoolExecutor(3) as ex: UH = list(ex.map(yahoo, ust))
    keep = [k for k, h in enumerate(UH) if len(h) > 600]
    ust = [ust[k] for k in keep]; UH = [UH[k] for k in keep]
    spy = yahoo("SPLG") or yahoo("SPY")
    if len(spy) > 600:
        dates = sorted(d for d in spy if d >= "20160101")
        P = matrix(UH, dates); B = np.array([spy[d] for d in dates]); us = [u["US"][t]["sector"] for t in ust]
        res["US"] = {"stocks": len(ust)}
        for lab, st, dp in (("$50 + 매달 $70", 50, 70), ("$2,200", 2200, 0)):
            print("US", lab, flush=True)
            res["US"][lab], res["US"]["span"] = evaluate(P, dates, us, B, "mom6", st, dp, dict(buyc=0.0025, sellc=0.0025))
            json.dump(res, open("signals4.json", "w"), ensure_ascii=False, indent=1)
    res["notes"] = "3년 기간을 약 2달 간격으로 여러 번 시작해 비교 · 매일 점검 · 1주 단위 · 다음 날 체결 · 수수료·거래세 · 현재 후보만 사용(생존 편향, 미국이 특히 큼)"
    json.dump(res, open("signals4.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
