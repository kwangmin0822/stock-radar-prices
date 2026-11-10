"""Round 7: confirm the round-6 winners. Combinations, doubled costs, and older-vs-newer windows separately."""
import json, datetime as dt
import concurrent.futures as cf
import numpy as np
from signals import hist, matrix, KST, BUY, SELL
from signals2 import yahoo
from signals4 import evaluate
from signals6 import build

def combos(R, cost2):
    b = R["지금 규칙"]; G = R["G 추세주 급락 때 5일 매수 쉬기"]["mask"]; C1 = R["C1 5일 +12% 급등 직후 매수 보류"]["mask"]
    C2 = R["C2 최근 하루 급등 상위 10% 제외"]["mask"]; E = R["E 베타 1.5 넘으면 매수 제외"]["mask"]; D = R["D 12~7개월 전 추세 25% 섞기"]["SIG"]
    out = {"지금 규칙": b, "G 급락 때 쉬기": {**b, "mask": G}, "C1 급등 직후 보류": {**b, "mask": C1}, "C2 하루 급등주 제외": {**b, "mask": C2},
           "D 오래된 추세 섞기": {**b, "SIG": D}, "E 고베타 제외": {**b, "mask": E},
           "G + C1": {**b, "mask": G & C1}, "G + C2": {**b, "mask": G & C2}, "G + D": {**b, "mask": G, "SIG": D},
           "G + D + C2": {**b, "mask": G & C2, "SIG": D}, "G + C1 + C2": {**b, "mask": G & C1 & C2}}
    for k in list(out):
        if k != "지금 규칙": pass
    out2 = {f"{k} · 비용 2배": {**v, "cost": cost2} for k, v in out.items()}
    return {**out, **out2}

def main():
    u = json.load(open("universe.json"))
    res = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "windowYears": 3}
    codes = list(u["KR"])
    with cf.ThreadPoolExecutor(8) as ex: KH = list(ex.map(hist, codes))
    keep = [k for k, h in enumerate(KH) if len(h) > 300]
    codes = [codes[k] for k in keep]; KH = [KH[k] for k in keep]
    k200 = hist("069500"); kd = sorted(k200)
    KP = matrix(KH, kd); K = np.array([k200[d] for d in kd]); ks = [u["KR"][c]["sector"] for c in codes]
    c2 = dict(buyc=2 * BUY, sellc=2 * SELL)
    RK = combos(build(KP, K, 10, c2), c2)
    res["KR"] = {"stocks": len(codes)}
    for lab, st, dp in (("7만 원 + 매달 10만 원", 70000, 100000), ("300만 원", 3000000, 0), ("1000만 원", 10000000, 0)):
        res["KR"][lab], res["KR"]["span"] = evaluate(KP, kd, ks, K, "mom6", st, dp, {}, RK)
        json.dump(res, open("signals7.json", "w"), ensure_ascii=False, indent=1)
    ust = list(u.get("US", {}))
    with cf.ThreadPoolExecutor(3) as ex: UH = list(ex.map(yahoo, ust))
    keep = [k for k, h in enumerate(UH) if len(h) > 600]
    ust = [ust[k] for k in keep]; UH = [UH[k] for k in keep]
    spy = yahoo("SPLG") or yahoo("SPY")
    if len(spy) > 600:
        dates = sorted(d for d in spy if d >= "20160101")
        P = matrix(UH, dates); B = np.array([spy[d] for d in dates]); us = [u["US"][t]["sector"] for t in ust]
        c2 = dict(buyc=0.005, sellc=0.005)
        RU = combos(build(P, B, 21, c2), c2)
        res["US"] = {"stocks": len(ust)}
        for lab, st, dp in (("$50 + 매달 $70", 50, 70), ("$2,200", 2200, 0), ("$7,000", 7000, 0)):
            res["US"][lab], res["US"]["span"] = evaluate(P, dates, us, B, "mom6", st, dp, dict(buyc=0.0025, sellc=0.0025), RU)
            json.dump(res, open("signals7.json", "w"), ensure_ascii=False, indent=1)
    json.dump(res, open("signals7.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
