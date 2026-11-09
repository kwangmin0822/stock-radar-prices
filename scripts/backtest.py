"""Backtest of the radar's price-based rules on the current Korean universe (universe.json), ~3 years of daily closes.
Fundamentals history isn't available, so this checks only the trend parts of the strategy:
  - momentum (12-1 month return) ranking
  - 200-day moving average filter
  - -12% stop-loss from entry
Monthly rebalance, equal weight, 0.25% cost per trade side. Survivorship bias: today's members only (results look better than reality)."""
import json, re, time, math, datetime as dt, urllib.request
import concurrent.futures as cf

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36", "Referer": "https://finance.naver.com/"}
KST = dt.timezone(dt.timedelta(hours=9))
COST = 0.0025
TOPN = 10

def hist(code, count=900):
    with urllib.request.urlopen(urllib.request.Request(
            f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={count}&requestType=0", headers=UA), timeout=20) as r:
        x = r.read().decode("euc-kr", "replace")
    out = {}
    for m in re.findall(r'data="([^"]+)"', x):
        f = m.split("|")
        if float(f[4]) > 0: out[f[0]] = float(f[4])
    return out

def stats(curve, dates):
    if len(curve) < 2: return {}
    iso = lambda s: dt.date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    yrs = (iso(dates[-1]) - iso(dates[0])).days / 365.25
    cagr = (curve[-1] / curve[0]) ** (1 / yrs) - 1 if yrs > 0 else 0
    peak, mdd = curve[0], 0
    for v in curve:
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    rets = [curve[i] / curve[i-1] - 1 for i in range(1, len(curve))]
    m = sum(rets) / len(rets); sd = math.sqrt(sum((r - m) ** 2 for r in rets) / max(1, len(rets) - 1))
    sharpe = (m / sd) * math.sqrt(252) if sd > 0 else 0
    return {"total": round((curve[-1] / curve[0] - 1) * 100, 1), "cagr": round(cagr * 100, 1), "mdd": round(mdd * 100, 1), "sharpe": round(sharpe, 2)}

def run(px, dates, rule):
    """rule: dict(mom=bool, ma=bool, stop=bool). Positions held as money amounts plus cash."""
    codes = list(px)
    pos, cash, entry = {}, 1.0, {}
    curve, month = [], None
    for i, d in enumerate(dates):
        if i > 0:
            pd_ = dates[i-1]
            for c in list(pos):
                a, b = px[c].get(pd_), px[c].get(d)
                if a and b: pos[c] *= b / a
            if rule.get("stop"):
                for c in list(pos):
                    p = px[c].get(d)
                    if p and entry.get(c) and p / entry[c] - 1 <= -0.12:
                        cash += pos.pop(c) * (1 - COST); entry.pop(c, None)
        value = cash + sum(pos.values())
        curve.append(value)
        if i < 260 or d[:6] == month: continue
        month = d[:6]
        scores = []
        for c in codes:
            s = px[c]
            ks = [k for k in dates[i-260:i+1] if k in s]
            if len(ks) < 240: continue
            now = s[ks[-1]]
            if rule.get("ma") and now < sum(s[k] for k in ks[-200:]) / 200: continue
            scores.append((s[ks[-21]] / s[ks[0]] - 1, c))
        if rule.get("mom"):
            scores.sort(reverse=True); pick = [c for _, c in scores[:TOPN]]
        else:
            pick = [c for _, c in scores]
        if not pick: continue
        tgt = value / len(pick)
        new = {c: tgt for c in pick}
        turnover = sum(abs(new.get(c, 0) - pos.get(c, 0)) for c in set(new) | set(pos))
        value -= turnover * COST
        for c in pick:
            if c not in pos: entry[c] = px[c].get(d)
        for c in list(entry):
            if c not in new: entry.pop(c)
        pos = {c: value / len(pick) for c in pick}; cash = 0.0
        curve[-1] = value
    return stats(curve[260:], dates[260:])

def main():
    u = json.load(open("universe.json"))
    codes = list(u["KR"])
    px = {}
    with cf.ThreadPoolExecutor(6) as ex:
        def safe(c):
            try: return hist(c)
            except Exception: return {}
        for c, h in zip(codes, ex.map(safe, codes)):
            if len(h) > 500: px[c] = h
    bench = hist("069500")
    dates = sorted(set(bench))
    dates = [d for d in dates if sum(1 for c in px if d in px[c]) > len(px) * 0.5]
    rules = {
        "전체 균등 (기준)": {},
        "추세 상위 10": {"mom": True},
        "추세 상위 10 + 200일선": {"mom": True, "ma": True},
        "추세 상위 10 + 200일선 + 손절 -12%": {"mom": True, "ma": True, "stop": True},
        "추세 상위 10 + 손절 -12%": {"mom": True, "stop": True},
    }
    res = {k: run(px, dates, r) for k, r in rules.items()}
    bc = [bench[d] for d in dates[260:]]
    res["KODEX 200 (코스피200)"] = stats(bc, dates[260:])
    out = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"),
           "period": [f"{dates[260][:4]}-{dates[260][4:6]}-{dates[260][6:]}", f"{dates[-1][:4]}-{dates[-1][4:6]}-{dates[-1][6:]}"],
           "stocks": len(px), "topN": TOPN, "costPerSide": COST, "results": res,
           "caveat": "현재 후보 종목만으로 계산(생존 편향) · 재무 점수는 과거 자료가 없어 빠짐"}
    json.dump(out, open("backtest.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
