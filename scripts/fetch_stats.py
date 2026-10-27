"""Weekly: 1-year annualized volatility (%) of daily returns for tickers.json -> stats.json.
KR: Naver fchart (fallback Yahoo .KS/.KQ). US: Yahoo chart."""
import json, math, re, time, datetime as dt, urllib.request, urllib.parse
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36", "Referer": "https://finance.naver.com/"}
KST = dt.timezone(dt.timedelta(hours=9))

def raw(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
        return r.read()

def vol(closes):
    c = [x for x in closes if x and x > 0]
    if len(c) < 120: return None
    rs = [math.log(c[i] / c[i-1]) for i in range(1, len(c))]
    m = sum(rs) / len(rs)
    sd = math.sqrt(sum((r - m) ** 2 for r in rs) / (len(rs) - 1))
    return round(sd * math.sqrt(252) * 100, 1)

def naver(code):
    x = raw(f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count=260&requestType=0").decode("euc-kr", "replace")
    return [float(m.split("|")[4]) for m in re.findall(r'data="([^"]+)"', x)]

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
    out = {}
    for c in tk["KR"]:
        v = None
        try: v = vol(naver(c))
        except Exception as e: print("naver fail", c, e)
        if v is None: v = vol(yahoo(c + ".KS")) or vol(yahoo(c + ".KQ"))
        if v is not None: out["KR-" + c] = v
        time.sleep(0.2)
    for t in tk["US"]:
        v = vol(yahoo(t.replace(".", "-")))
        if v is not None: out["US-" + t] = v
        time.sleep(0.6)
    json.dump({"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "vol": out}, open("stats.json", "w"), indent=0, sort_keys=True)
    print(f"vol {len(out)}/{len(tk['KR'])+len(tk['US'])}")

if __name__ == "__main__":
    main()
