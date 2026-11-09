"""Realistic check of the trend rule for a small Korean account.
- signals use closes up to the previous day; trades fill at the next day's close plus 0.1% slippage
- whole shares only, starting cash 70,000 KRW, optional monthly deposits
- costs: buy fee 0.015%, sell fee 0.015% + transaction tax 0.20%
- stop-loss: when a close is 12% under the entry, sell at the NEXT day's close (gaps hurt)
- holdings: keep while in the top 2N by 6-month momentum, otherwise sell; buy the best-ranked names you can afford,
  no single stock above max(1 share, 50% of equity), at most 2 names per sector
Compared with buying KODEX 200 and KODEX 미국S&P500 with the same deposits (whole shares, same costs minus the tax).
Survivorship bias remains (today's universe only)."""
import json, re, datetime as dt, urllib.request
import concurrent.futures as cf
import numpy as np

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36", "Referer": "https://finance.naver.com/"}
KST = dt.timezone(dt.timedelta(hours=9))
BUY, SELL, SLIP = 0.00015, 0.00015 + 0.0020, 0.001

def hist(code, count=2100):
    try:
        with urllib.request.urlopen(urllib.request.Request(
                f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={count}&requestType=0", headers=UA), timeout=25) as r:
            x = r.read().decode("euc-kr", "replace")
    except Exception:
        return {}
    return {m.split("|")[0]: float(m.split("|")[4]) for m in re.findall(r'data="([^"]+)"', x) if float(m.split("|")[4]) > 0}

def matrix(H, dates):
    P = np.full((len(dates), len(H)), np.nan)
    for j, h in enumerate(H):
        last = np.nan
        for i, d in enumerate(dates):
            v = h.get(d)
            if v: last = v
            P[i, j] = last if h and min(h) <= d else np.nan
    return P

def sim(P, dates, sectors, i0, i1, start, deposit, topn=10, stop=-0.12, look=126, skip=21):
    n = P.shape[1]
    sh = np.zeros(n, int); cash = float(start); entry = np.full(n, np.nan); pend_stop = np.zeros(n, bool)
    curve, flows, month, trades, cost = [], [], None, 0, 0.0
    for i in range(i0, i1):
        px = P[i]
        # 1) stop-loss orders decided yesterday fill today
        for j in np.where(pend_stop & (sh > 0))[0]:
            if np.isnan(px[j]): continue
            got = sh[j] * px[j] * (1 - SLIP); c = got * SELL
            cash += got - c; cost += c; trades += 1; sh[j] = 0; entry[j] = np.nan
        pend_stop[:] = False
        new_month = dates[i][:6] != month
        flow = 0.0
        if new_month and month is not None and deposit:
            cash += deposit; flow = deposit
        if new_month:
            month = dates[i][:6]
            prev = P[i - 1]
            mom = P[i - 1 - skip] / P[i - 1 - look] - 1
            ok = ~np.isnan(mom) & ~np.isnan(prev) & ~np.isnan(px)
            order = [j for j in np.argsort(-np.where(ok, mom, -np.inf)) if ok[j]]
            rank = {j: r for r, j in enumerate(order)}
            # sell names that dropped out of the top 2N
            for j in np.where(sh > 0)[0]:
                if rank.get(j, 1e9) >= 2 * topn and not np.isnan(px[j]):
                    got = sh[j] * px[j] * (1 - SLIP); c = got * SELL
                    cash += got - c; cost += c; trades += 1; sh[j] = 0; entry[j] = np.nan
            eq = cash + np.nansum(sh * px)
            cap = 0.5 * eq
            sec_n = {}
            for j in np.where(sh > 0)[0]: sec_n[sectors[j]] = sec_n.get(sectors[j], 0) + 1
            target = order[:topn]
            # buy: walk the top-N; one share at a time round-robin while money lasts
            changed = True
            while changed:
                changed = False
                for j in target:
                    p = px[j] * (1 + SLIP) * (1 + BUY)
                    if p > cash: continue
                    held_val = sh[j] * px[j]
                    if sh[j] == 0 and sec_n.get(sectors[j], 0) >= 2: continue
                    if sh[j] > 0 and held_val + px[j] > cap: continue
                    if sh[j] == 0: sec_n[sectors[j]] = sec_n.get(sectors[j], 0) + 1; entry[j] = px[j]
                    cash -= p; cost += px[j] * (SLIP + BUY); sh[j] += 1; trades += 1; changed = True
        # 2) stop check on today's close, fills tomorrow
        if stop is not None:
            pend_stop = (sh > 0) & ~np.isnan(px) & (px / entry - 1 <= stop)
        curve.append(cash + np.nansum(np.where(sh > 0, sh * px, 0))); flows.append(flow)
    return np.array(curve), np.array(flows), trades, cost

def etf(prices, dates, i0, i1, start, deposit):
    sh, cash, month, curve, flows = 0, float(start), None, [], []
    for i in range(i0, i1):
        flow = 0.0
        if dates[i][:6] != month:
            if month is not None and deposit: cash += deposit; flow = deposit
            month = dates[i][:6]
            p = prices[i] * (1 + SLIP) * (1 + BUY)
            k = int(cash // p); sh += k; cash -= k * p
        curve.append(cash + sh * prices[i]); flows.append(flow)
    return np.array(curve), np.array(flows)

def twr(curve, flows, dates):
    g = 1.0
    for i in range(1, len(curve)):
        if curve[i - 1] > 0: g *= (curve[i] - flows[i]) / curve[i - 1]
    yrs = (dt.date(int(dates[-1][:4]), int(dates[-1][4:6]), int(dates[-1][6:])) - dt.date(int(dates[0][:4]), int(dates[0][4:6]), int(dates[0][6:]))).days / 365.25
    # drawdown on the time-weighted index
    idx = [1.0]
    for i in range(1, len(curve)): idx.append(idx[-1] * ((curve[i] - flows[i]) / curve[i - 1] if curve[i - 1] > 0 else 1))
    idx = np.array(idx); mdd = float(np.min(idx / np.maximum.accumulate(idx) - 1))
    return {"cagr": round(float(g ** (1 / yrs) - 1) * 100, 1), "mdd": round(mdd * 100, 1), "final": int(curve[-1]), "paidIn": int(curve[0] + flows.sum())}

def main():
    u = json.load(open("universe.json"))
    codes = list(u["KR"])
    with cf.ThreadPoolExecutor(8) as ex:
        H = list(ex.map(hist, codes))
    keep = [k for k, h in enumerate(H) if len(h) > 300]
    codes = [codes[k] for k in keep]; H = [H[k] for k in keep]
    sectors = [u["KR"][c]["sector"] for c in codes]
    k200, sp = hist("069500"), hist("379800")
    dates = sorted(d for d in k200 if d in sp) if sp else sorted(k200)
    P = matrix(H, dates)
    K = np.array([k200[d] for d in dates]); S = np.array([sp.get(d, np.nan) for d in dates])
    start_i = 260
    res = {"period": [dates[start_i], dates[-1]], "stocks": len(codes), "scenarios": {}}
    for label, start, dep in [("7만 원, 추가 입금 없음", 70000, 0), ("7만 원 + 매달 10만 원", 70000, 100000),
                              ("7만 원 + 매달 30만 원", 70000, 300000), ("300만 원 (비교용)", 3000000, 0)]:
        row = {}
        for nm, stop in [("6개월 추세 + 손절 −12%", -0.12), ("6개월 추세, 손절 없음", None)]:
            c, f, tr, cost = sim(P, dates, sectors, start_i, len(dates), start, dep, stop=stop)
            row[nm] = {**twr(c, f, dates[start_i:]), "trades": tr, "costKRW": int(cost)}
        c, f = etf(K, dates, start_i, len(dates), start, dep); row["KODEX 200 적립"] = twr(c, f, dates[start_i:])
        if not np.isnan(S[start_i:]).any():
            c, f = etf(S, dates, start_i, len(dates), start, dep); row["KODEX 미국S&P500 적립"] = twr(c, f, dates[start_i:])
        res["scenarios"][label] = row
    res["updatedAt"] = dt.datetime.now(KST).isoformat(timespec="seconds")
    res["notes"] = "신호는 전날 종가, 체결은 다음 날 종가+0.1% · 1주 단위 · 수수료·거래세 반영 · 손절은 다음 날 체결 · 현재 후보만 사용(생존 편향)"
    json.dump(res, open("realcheck.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
