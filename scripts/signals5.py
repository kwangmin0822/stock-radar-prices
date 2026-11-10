"""Round 5: follow-up on round 4. In Korea the 6-month trend (skip last month) beat the 52-week-high rule once every
day is checked and many start dates are used, and the market filter cut drawdowns. Test the combinations."""
import json, datetime as dt
import concurrent.futures as cf
import numpy as np
from signals import hist, matrix, KST
from signals2 import yahoo
from signals4 import evaluate

KR_RULES = {
    "52주 신고가 근접 (지금)": {"kind": "high52"},
    "6개월 추세": {"kind": "mom6"},
    "6개월 추세 + 하락장엔 새로 안 사기": {"kind": "mom6", "filter": True},
    "6개월 추세 + 30일 잠금": {"kind": "mom6", "lock": 21},
    "6개월 추세 + 하락장 + 30일 잠금": {"kind": "mom6", "filter": True, "lock": 21},
    "6개월 추세 + 하락장 + 손절 −20%": {"kind": "mom6", "filter": True, "stop": -0.20},
    "6개월 추세 + 하락장 + 종목 15개": {"kind": "mom6", "filter": True, "topn": 15},
}
US_RULES = {
    "6개월 추세 (지금)": {},
    "+ 30일 잠금": {"lock": 21},
    "+ 30일 잠금 + 손절 없음": {"lock": 21, "stop": None},
}

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
    for lab, st, dp in (("7만 원 + 매달 10만 원", 70000, 100000), ("300만 원", 3000000, 0), ("1000만 원", 10000000, 0)):
        res["KR"][lab], res["KR"]["span"] = evaluate(KP, kd, ks, K, "high52", st, dp, {}, KR_RULES)
        json.dump(res, open("signals5.json", "w"), ensure_ascii=False, indent=1)
    ust = list(u.get("US", {}))
    with cf.ThreadPoolExecutor(3) as ex: UH = list(ex.map(yahoo, ust))
    keep = [k for k, h in enumerate(UH) if len(h) > 600]
    ust = [ust[k] for k in keep]; UH = [UH[k] for k in keep]
    spy = yahoo("SPLG") or yahoo("SPY")
    if len(spy) > 600:
        dates = sorted(d for d in spy if d >= "20160101")
        P = matrix(UH, dates); B = np.array([spy[d] for d in dates]); us = [u["US"][t]["sector"] for t in ust]
        res["US"] = {"stocks": len(ust)}
        for lab, st, dp in (("$50 + 매달 $70", 50, 70), ("$2,200", 2200, 0), ("$7,000", 7000, 0)):
            res["US"][lab], res["US"]["span"] = evaluate(P, dates, us, B, "mom6", st, dp, dict(buyc=0.0025, sellc=0.0025), US_RULES)
            json.dump(res, open("signals5.json", "w"), ensure_ascii=False, indent=1)
    json.dump(res, open("signals5.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
