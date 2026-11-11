"""Round 8: ChatGPT's second set, each added alone to the current rule (Korea: 6-1 trend + 25% 12-7 trend, crash pause,
skip one-day spikes; US: 6-1 trend, crash pause, 30-day lock). Compared on final money with the same deposits.
A  rebound score: after the index fell below 80% of its 200-day average, a rebound starts when it is 8%+ above its 20-day
   low and closes above its 10-day average 3 days in a row; for the next 20 trading days rank by 60% 20-day + 40% 5-day return
   A1 rebound score only / A2 half current score + half rebound score / A3 = A2 and no crash pause during the rebound
B1 current score 80% + 20-day return rank 20%, all the time
C1 +5 points (of 100) if the 20-day return is positive and 20-day volume / previous 60-day volume >= 1.3
C2 same but no bonus when that volume ratio is above 3"""
import json, re, time, datetime as dt, urllib.request, urllib.parse
import concurrent.futures as cf
import numpy as np
from signals import matrix, KST, BUY, SELL, UA
from signals2 import YUA, _op, CRUMB
from signals4 import evaluate
from signals6 import build, rankpct

def hist_kr(code, count=2100):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={count}&requestType=0", headers=UA), timeout=25) as r:
            x = r.read().decode("euc-kr", "replace")
    except Exception:
        return {}, {}
    c, v = {}, {}
    for m in re.findall(r'data="([^"]+)"', x):
        f = m.split("|")
        if float(f[4]) > 0: c[f[0]] = float(f[4]); v[f[0]] = float(f[5])
    return c, v

def hist_us(t):
    for i in range(4):
        try:
            u = (f"https://query{1 + i % 2}.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(t.replace('.', '-'))}"
                 f"?interval=1d&range=10y&crumb={urllib.parse.quote(CRUMB)}")
            with _op.open(urllib.request.Request(u, headers=YUA), timeout=25) as r:
                d = json.loads(r.read())["chart"]["result"][0]
            q = d["indicators"]["quote"][0]; c, v = {}, {}
            for a, cl, vo in zip(d["timestamp"], q["close"], q["volume"]):
                if cl: k = dt.datetime.utcfromtimestamp(a).strftime("%Y%m%d"); c[k] = cl; v[k] = vo or 0
            return c, v
        except Exception:
            time.sleep(1 + 2 * i)
    return {}, {}

def rebound_days(M):
    T = len(M); ma200 = np.array([M[max(0, i - 199):i + 1].mean() for i in range(T)])
    ma10 = np.array([M[max(0, i - 9):i + 1].mean() for i in range(T)])
    on = np.zeros(T, bool); was_down = False; streak = 0; i = 200
    while i < T:
        if M[i] <= 0.8 * ma200[i]: was_down = True
        streak = streak + 1 if M[i] > ma10[i] else 0
        if was_down and M[i] >= 1.08 * M[max(0, i - 19):i + 1].min() and streak >= 3:
            on[i:i + 21] = True; was_down = False; i += 21; continue
        i += 1
    return on

def rules(P, V, M, lock, cost2, market):
    R = build(P, M, lock, cost2)
    T, n = P.shape
    if market == "KR":
        base = {"kind": "mom6", "lock": lock, "SIG": R["D 12~7개월 전 추세 25% 섞기"]["SIG"],
                "mask": R["G 추세주 급락 때 5일 매수 쉬기"]["mask"] & R["C2 최근 하루 급등 상위 10% 제외"]["mask"]}
        nocrash = R["C2 최근 하루 급등 상위 10% 제외"]["mask"]
    else:
        m6 = np.full(P.shape, np.nan); m6[126:] = P[105:-21] / P[:-126] - 1
        base = {"kind": "mom6", "lock": lock, "SIG": rankpct(m6), "mask": R["G 추세주 급락 때 5일 매수 쉬기"]["mask"]}
        nocrash = np.ones(P.shape, bool)
    S0 = base["SIG"]
    r20 = np.full(P.shape, np.nan); r20[20:] = P[20:] / P[:-20] - 1
    r5 = np.full(P.shape, np.nan); r5[5:] = P[5:] / P[:-5] - 1
    reb = 0.6 * rankpct(r20) + 0.4 * rankpct(r5)
    on = rebound_days(M)[:, None]
    A1 = np.where(on, reb, S0); A2 = np.where(on, 0.5 * S0 + 0.5 * reb, S0)
    maskA3 = np.where(on, nocrash, base["mask"])
    B1 = 0.8 * S0 + 0.2 * rankpct(r20)
    Vn = np.nan_to_num(V)
    cs = np.cumsum(Vn, axis=0)
    v20 = np.full(P.shape, np.nan); v60 = np.full(P.shape, np.nan)
    v20[80:] = (cs[80:] - cs[60:-20]) / 20; v60[80:] = (cs[60:-20] - cs[:-80]) / 60
    with np.errstate(divide="ignore", invalid="ignore"): vr = v20 / v60
    up = r20 > 0
    C1 = S0 + np.where(up & (vr >= 1.3), 0.05, 0)
    C2 = S0 + np.where(up & (vr >= 1.3) & (vr <= 3), 0.05, 0)
    return {"지금 규칙": base,
            "A1 반등 땐 반등 점수만": {**base, "SIG": A1},
            "A2 반등 땐 반반 섞기": {**base, "SIG": A2},
            "A3 = A2 + 반등 땐 급락 쉬기 해제": {**base, "SIG": A2, "mask": maskA3},
            "B1 최근 20일 추세 20% 섞기": {**base, "SIG": B1},
            "C1 거래량 늘며 오르면 +5점": {**base, "SIG": C1},
            "C2 = C1, 거래량 3배 넘으면 제외": {**base, "SIG": C2},
            "지금 규칙 · 비용 2배": {**base, "cost": cost2}}, int(rebound_days(M).sum())

def main():
    u = json.load(open("universe.json"))
    res = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "windowYears": 3}
    codes = list(u["KR"])
    with cf.ThreadPoolExecutor(8) as ex: KH = list(ex.map(hist_kr, codes))
    keep = [k for k, h in enumerate(KH) if len(h[0]) > 300]
    codes = [codes[k] for k in keep]; KH = [KH[k] for k in keep]
    kc, _ = hist_kr("069500"); kd = sorted(kc)
    KP = matrix([h[0] for h in KH], kd); KV = matrix([h[1] for h in KH], kd); K = np.array([kc[d] for d in kd])
    ks = [u["KR"][c]["sector"] for c in codes]
    c2 = dict(buyc=2 * BUY, sellc=2 * SELL)
    RK, nreb = rules(KP, KV, K, 10, c2, "KR")
    res["KR"] = {"stocks": len(codes), "reboundDays": nreb}
    for lab, st, dp in (("7만 원 + 매달 10만 원", 70000, 100000), ("300만 원", 3000000, 0), ("1000만 원", 10000000, 0)):
        print("KR", lab, flush=True)
        res["KR"][lab], res["KR"]["span"] = evaluate(KP, kd, ks, K, "mom6", st, dp, {}, RK)
        json.dump(res, open("signals8.json", "w"), ensure_ascii=False, indent=1)
    ust = list(u.get("US", {}))
    with cf.ThreadPoolExecutor(3) as ex: UH = list(ex.map(hist_us, ust))
    keep = [k for k, h in enumerate(UH) if len(h[0]) > 600]
    ust = [ust[k] for k in keep]; UH = [UH[k] for k in keep]
    sc, _ = hist_us("SPLG")
    if len(sc) > 600:
        dates = sorted(d for d in sc if d >= "20160101")
        P = matrix([h[0] for h in UH], dates); V = matrix([h[1] for h in UH], dates); B = np.array([sc[d] for d in dates])
        us = [u["US"][t]["sector"] for t in ust]
        RU, nreb = rules(P, V, B, 21, dict(buyc=0.005, sellc=0.005), "US")
        res["US"] = {"stocks": len(ust), "reboundDays": nreb}
        for lab, st, dp in (("$50 + 매달 $70", 50, 70), ("$2,200", 2200, 0), ("$7,000", 7000, 0)):
            print("US", lab, flush=True)
            res["US"][lab], res["US"]["span"] = evaluate(P, dates, us, B, "mom6", st, dp, dict(buyc=0.0025, sellc=0.0025), RU)
            json.dump(res, open("signals8.json", "w"), ensure_ascii=False, indent=1)
    json.dump(res, open("signals8.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
