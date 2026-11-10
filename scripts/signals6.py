"""Round 6: price-only ideas suggested by ChatGPT, each added alone to the current rule (6-month trend skipping the
last month; lock 14 days KR / 30 days US), over many 3-year windows (same method as signals4/5).
A  relative strength: no new buy if the stock's 6-1 return is not above the market's
B  trend consistency: trend score x0.8 unless at least 4 of the 6 monthly returns (ending a month ago) were up
C1 short-term overheat: no new buy within 5 days after a 5-day gain above +12%
C2 lottery stocks (Bali, Cakici & Whitelaw 2011): no new buy if the largest daily gain of the last 21 days is in the top 10%
D  add older momentum: trend = 75% rank of 6-1 return + 25% rank of 12-7 return
E  high beta: no new buy if the 1-year beta to the market is above 1.5
F  portfolio volatility: pause new buys while 20-day portfolio volatility > 1.5x its 1-year median (resume under 1.2x)
G  momentum crash: pause new buys for 5 days when top-20% trend names trailed bottom-20% by 10 points over 20 days
Plus the current rule with doubled costs, and each rule's trades, to check cost robustness."""
import json, datetime as dt
import concurrent.futures as cf
import numpy as np
from signals import hist, matrix, signal, KST, BUY, SELL
from signals2 import yahoo
from signals4 import evaluate

def rankpct(x):
    out = np.full(x.shape, np.nan)
    for i in range(x.shape[0]):
        v = x[i]; ok = ~np.isnan(v)
        if ok.sum() < 2: continue
        r = np.argsort(np.argsort(v[ok])).astype(float) / (ok.sum() - 1)
        out[i, ok] = r
    return out

def build(P, M, lock, cost):
    T, n = P.shape
    m6 = np.full(P.shape, np.nan); m712 = np.full(P.shape, np.nan); ups = np.full(P.shape, np.nan)
    mk6 = np.full(T, np.nan)
    for i in range(252, T):
        m6[i] = P[i - 21] / P[i - 126] - 1
        m712[i] = P[i - 126] / P[i - 252] - 1
        mk6[i] = M[i - 21] / M[i - 126] - 1
        seg = np.stack([P[i - 21 - 21 * k] / P[i - 42 - 21 * k] - 1 for k in range(6)])
        ups[i] = np.where(np.isnan(seg).any(0), np.nan, (seg > 0).sum(0))
    R = np.diff(np.log(P), axis=0, prepend=np.nan); r = np.exp(R) - 1
    m = np.diff(np.log(M), prepend=np.nan)
    # A relative strength
    rs = m6 > mk6[:, None]
    # B consistency
    rk = rankpct(m6); sigB = np.where(ups >= 4, rk, rk * 0.8)
    # C1 overheat: any 5-day gain > 12% within the last 5 days
    r5 = np.full(P.shape, np.nan); r5[5:] = P[5:] / P[:-5] - 1
    hot = np.zeros(P.shape, bool)
    for k in range(5): hot[k:] |= np.nan_to_num(r5[:T - k] if k == 0 else r5[:-k], nan=0) > 0.12
    # C2 MAX21 top 10%
    mx = np.full(P.shape, np.nan)
    for i in range(21, T): mx[i] = np.nanmax(r[i - 20:i + 1], axis=0)
    q90 = np.nanpercentile(mx, 90, axis=1)
    lottery = mx > q90[:, None]
    # D blend
    sigD = 0.75 * rk + 0.25 * rankpct(m712)
    # E beta (rolling 252 days)
    Rn = np.nan_to_num(R); mn = np.nan_to_num(m)
    cs = lambda a: np.cumsum(a, axis=0)
    W = 252
    Sx, Sy, Sxy, Syy = cs(mn), cs(Rn), cs(Rn * mn[:, None]), cs(mn ** 2)
    beta = np.full(P.shape, np.nan)
    for i in range(W, T):
        sx = Sx[i] - Sx[i - W]; sy = Sy[i] - Sy[i - W]; sxy = Sxy[i] - Sxy[i - W]; syy = Syy[i] - Syy[i - W]
        varm = syy / W - (sx / W) ** 2
        if varm > 0: beta[i] = (sxy / W - (sx / W) * (sy / W)) / varm
    hib = beta > 1.5
    # G momentum crash: 20-day return of top vs bottom quintile by 6-1 trend (sorted 20 days ago)
    crash = np.zeros(T, bool)
    for i in range(252 + 20, T):
        s = m6[i - 20]; ok = ~np.isnan(s) & ~np.isnan(P[i]) & ~np.isnan(P[i - 20])
        if ok.sum() < 20: continue
        q = np.nanpercentile(s[ok], [20, 80]); ret = P[i] / P[i - 20] - 1
        if np.nanmean(ret[ok & (s >= q[1])]) - np.nanmean(ret[ok & (s <= q[0])]) < -0.10: crash[i:i + 6] = True
    crash = crash[:T]
    base = {"kind": "mom6", "lock": lock}
    R_ = {
        "지금 규칙": base,
        "지금 규칙 · 비용 2배": {**base, "cost": cost},
        "A 시장보다 강한 종목만 매수": {**base, "mask": rs},
        "B 꾸준히 오른 종목 우대": {**base, "SIG": sigB},
        "C1 5일 +12% 급등 직후 매수 보류": {**base, "mask": ~hot},
        "C2 최근 하루 급등 상위 10% 제외": {**base, "mask": ~lottery},
        "D 12~7개월 전 추세 25% 섞기": {**base, "SIG": sigD},
        "E 베타 1.5 넘으면 매수 제외": {**base, "mask": ~hib},
        "F 계좌 변동성 급등 때 매수 쉬기": {**base, "volctl": True},
        "G 추세주 급락 때 5일 매수 쉬기": {**base, "mask": np.repeat(~crash[:, None], n, axis=1)},
    }
    return R_

def main():
    u = json.load(open("universe.json"))
    res = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "windowYears": 3}
    codes = list(u["KR"])
    with cf.ThreadPoolExecutor(8) as ex: KH = list(ex.map(hist, codes))
    keep = [k for k, h in enumerate(KH) if len(h) > 300]
    codes = [codes[k] for k in keep]; KH = [KH[k] for k in keep]
    k200 = hist("069500"); kd = sorted(k200)
    KP = matrix(KH, kd); K = np.array([k200[d] for d in kd]); ks = [u["KR"][c]["sector"] for c in codes]
    RK = build(KP, K, 10, dict(buyc=2 * BUY, sellc=2 * SELL))
    res["KR"] = {"stocks": len(codes)}
    for lab, st, dp in (("7만 원 + 매달 10만 원", 70000, 100000), ("300만 원", 3000000, 0), ("1000만 원", 10000000, 0)):
        print("KR", lab, flush=True)
        res["KR"][lab], res["KR"]["span"] = evaluate(KP, kd, ks, K, "mom6", st, dp, {}, RK)
        json.dump(res, open("signals6.json", "w"), ensure_ascii=False, indent=1)
    ust = list(u.get("US", {}))
    with cf.ThreadPoolExecutor(3) as ex: UH = list(ex.map(yahoo, ust))
    keep = [k for k, h in enumerate(UH) if len(h) > 600]
    ust = [ust[k] for k in keep]; UH = [UH[k] for k in keep]
    spy = yahoo("SPLG") or yahoo("SPY")
    if len(spy) > 600:
        dates = sorted(d for d in spy if d >= "20160101")
        P = matrix(UH, dates); B = np.array([spy[d] for d in dates]); us = [u["US"][t]["sector"] for t in ust]
        RU = build(P, B, 21, dict(buyc=0.005, sellc=0.005))
        res["US"] = {"stocks": len(ust)}
        for lab, st, dp in (("$50 + 매달 $70", 50, 70), ("$2,200", 2200, 0), ("$7,000", 7000, 0)):
            print("US", lab, flush=True)
            res["US"][lab], res["US"]["span"] = evaluate(P, dates, us, B, "mom6", st, dp, dict(buyc=0.0025, sellc=0.0025), RU)
            json.dump(res, open("signals6.json", "w"), ensure_ascii=False, indent=1)
    json.dump(res, open("signals6.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
