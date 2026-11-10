"""Weekly: 1-year annualized volatility (%) of daily returns for tickers.json -> stats.json.
KR: Naver fchart (fallback Yahoo .KS/.KQ). US: Yahoo chart."""
import json, math, re, time, datetime as dt, urllib.request, urllib.parse
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36", "Referer": "https://finance.naver.com/"}
KST = dt.timezone(dt.timedelta(hours=9))

def raw(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
        return r.read()

def ma200(closes):
    c = [x for x in closes if x and x > 0]
    if len(c) < 200: return None
    return round(sum(c[-200:]) / 200, 4)

def vol(closes):
    c = [x for x in closes if x and x > 0]
    if len(c) < 120: return None
    rs = [math.log(c[i] / c[i-1]) for i in range(1, len(c))]
    m = sum(rs) / len(rs)
    sd = math.sqrt(sum((r - m) ** 2 for r in rs) / (len(rs) - 1))
    return round(sd * math.sqrt(252) * 100, 1)

def chg52(closes):
    c = [x for x in closes if x and x > 0]
    if len(c) < 200: return None
    base = c[-250] if len(c) >= 250 else c[0]
    return round((c[-1] / base - 1) * 100, 1)

def near_high(closes):
    """price / highest close of the last 252 days, in % (100 = at the 52-week high)"""
    c = [x for x in closes if x and x > 0]
    if len(c) < 200: return None
    return round(c[-1] / max(c[-252:]) * 100, 1)

def mom6s(closes):
    """6-month return skipping the latest month (closes 21 days ago vs 126 days ago), in %"""
    c = [x for x in closes if x and x > 0]
    if len(c) < 130: return None
    return round((c[-22] / c[-127] - 1) * 100, 1)

def mom12_7(closes):
    """return from 12 months ago to 6 months ago (closes 252 vs 126 days ago), in %"""
    c = [x for x in closes if x and x > 0]
    if len(c) < 253: return None
    return round((c[-127] / c[-253] - 1) * 100, 1)

def max21(closes):
    """largest one-day gain of the last 21 trading days, in %"""
    c = [x for x in closes if x and x > 0]
    if len(c) < 23: return None
    return round(max(c[i] / c[i - 1] - 1 for i in range(len(c) - 21, len(c))) * 100, 1)

def crash_flag(series):
    """momentum-crash check over the last 6 trading days: sort by 6-1 trend as of 20 days earlier, compare the next
    20-day return of the top and bottom 20%. Triggered if the top trailed the bottom by more than 10 points."""
    S = [[x for x in c if x and x > 0] for c in series]
    S = [c for c in S if len(c) >= 160]
    out = {"crash": False, "spread": None, "n": len(S)}
    if len(S) < 20: return out
    for o in range(6):
        e = -1 - o
        sig = [(c[e - 41] / c[e - 146] - 1, c[e] / c[e - 20] - 1) for c in S]
        sig.sort(key=lambda t: t[0]); k = max(1, len(sig) // 5)
        spread = sum(t[1] for t in sig[-k:]) / k - sum(t[1] for t in sig[:k]) / k
        if o == 0: out["spread"] = round(spread * 100, 1)
        if spread < -0.10: out["crash"] = True; out["triggeredDaysAgo"] = o; break
    return out

def chg26(closes):
    c = [x for x in closes if x and x > 0]
    if len(c) < 130: return None
    return round((c[-1] / c[-127] - 1) * 100, 1)

def naver(code):
    x = raw(f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count=300&requestType=0").decode("euc-kr", "replace")
    return [float(m.split("|")[4]) for m in re.findall(r'data="([^"]+)"', x)]

BENCH = {"KR-069500": "069500", "KR-379800": "379800"}   # KODEX 200 (코스피), KODEX 미국S&P500 (원화)

def naver_dated(code, count=500):
    x = raw(f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count={count}&requestType=0").decode("euc-kr", "replace")
    out = []
    for m in re.findall(r'data="([^"]+)"', x):
        f = m.split("|")
        out.append([f"{f[0][:4]}-{f[0][4:6]}-{f[0][6:8]}", float(f[4])])
    return out

def yahoo(sym):
    for i in range(3):
        try:
            d = json.loads(raw("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(sym) + "?interval=1d&range=1y"))
            return d["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        except Exception:
            time.sleep(2 + 3 * i)
    return []

def main():
    tk = json.load(open("tickers.json"))
    out, ma, p52, p26, hi, m6, m712, mx = {}, {}, {}, {}, {}, {}, {}, {}
    series = {"KR": [], "US": []}
    bench = {}
    for k, c in BENCH.items():
        try: bench[k] = naver_dated(c)
        except Exception as e: print("bench fail", k, e)
    for c in tk["KR"]:
        cl = []
        try: cl = naver(c)
        except Exception as e: print("naver fail", c, e)
        if vol(cl) is None: cl = yahoo(c + ".KS") or yahoo(c + ".KQ")
        v, m = vol(cl), ma200(cl)
        if v is not None: out["KR-" + c] = v
        if m is not None: ma["KR-" + c] = m
        p = chg52(cl)
        if p is not None: p52["KR-" + c] = p
        q = chg26(cl)
        if q is not None: p26["KR-" + c] = q
        h = near_high(cl)
        if h is not None: hi["KR-" + c] = h
        w = mom6s(cl)
        if w is not None: m6["KR-" + c] = w
        w = mom12_7(cl)
        if w is not None: m712["KR-" + c] = w
        w = max21(cl)
        if w is not None: mx["KR-" + c] = w
        series["KR"].append(cl)
        time.sleep(0.2)
    for t in tk["US"]:
        cl = yahoo(t.replace(".", "-"))
        v, m = vol(cl), ma200(cl)
        if v is not None: out["US-" + t] = v
        if m is not None: ma["US-" + t] = m
        p = chg52(cl)
        if p is not None: p52["US-" + t] = p
        q = chg26(cl)
        if q is not None: p26["US-" + t] = q
        h = near_high(cl)
        if h is not None: hi["US-" + t] = h
        w = mom6s(cl)
        if w is not None: m6["US-" + t] = w
        w = mom12_7(cl)
        if w is not None: m712["US-" + t] = w
        w = max21(cl)
        if w is not None: mx["US-" + t] = w
        series["US"].append(cl)
        time.sleep(0.6)
    json.dump({"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "vol": out, "ma200": ma, "p52": p52, "p26": p26, "hi52": hi, "m6s": m6, "m712": m712, "max21": mx, "regime": {k: crash_flag(v) for k, v in series.items()}, "bench": bench}, open("stats.json", "w"), indent=0, sort_keys=True)
    print(f"vol {len(out)}/{len(tk['KR'])+len(tk['US'])}")

if __name__ == "__main__":
    main()
