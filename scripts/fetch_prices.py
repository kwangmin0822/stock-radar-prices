"""Fetch near-real-time prices for tickers.json -> prices.json.
KR: Naver realtime polling (fallback Yahoo .KS/.KQ). US: Yahoo chart (fallback Naver). FX: Yahoo KRW=X."""
import json, time, datetime as dt, urllib.request, urllib.parse, concurrent.futures as cf

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
      "Accept": "application/json,text/plain,*/*", "Referer": "https://finance.naver.com/"}
KST = dt.timezone(dt.timedelta(hours=9))

def get(url, timeout=10):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def num(x):
    if x is None: return None
    try: return float(str(x).replace(",", ""))
    except ValueError: return None

def iso(ts):  # unix seconds -> KST iso
    return dt.datetime.fromtimestamp(ts, KST).isoformat(timespec="minutes")

def naver_kr(codes):
    out = {}
    for i in range(0, len(codes), 20):
        chunk = codes[i:i+20]
        try:
            d = get("https://polling.finance.naver.com/api/realtime/domestic/stock/" + ",".join(chunk))
            for it in d.get("datas", []):
                p = num(it.get("closePrice"))
                if not p: continue
                t = it.get("localTradedAt") or ""
                out[it["itemCode"]] = {"price": p, "change": num(it.get("fluctuationsRatio")),
                    "prevClose": None, "at": t[:16] if t else None,
                    "status": it.get("marketStatus"), "src": "naver"}
        except Exception as e:
            print("naver kr chunk fail", chunk[:2], e)
    return out

def yahoo(sym):
    d = get("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(sym) + "?interval=1m&range=1d&includePrePost=true")
    m = d["chart"]["result"][0]["meta"]
    p = m.get("regularMarketPrice"); pc = m.get("chartPreviousClose") or m.get("previousClose")
    res = {"price": p, "prevClose": pc, "change": round((p / pc - 1) * 100, 2) if p and pc else None,
           "at": iso(m["regularMarketTime"]) if m.get("regularMarketTime") else None, "src": "yahoo"}
    # extended-hours last trade, if newer
    try:
        q = d["chart"]["result"][0]
        ts, cl = q["timestamp"], q["indicators"]["quote"][0]["close"]
        for t, c in zip(reversed(ts), reversed(cl)):
            if c:
                if m.get("regularMarketTime") and t > m["regularMarketTime"] + 60:
                    res["ext"] = {"price": round(c, 4), "at": iso(t)}
                break
    except Exception:
        pass
    return res

def naver_us(t):
    for suf in ("", ".O", ".K", ".N"):
        try:
            d = get(f"https://api.stock.naver.com/stock/{t}{suf}/basic")
            p = num(d.get("closePrice"))
            if p:
                return {"price": p, "change": num(d.get("fluctuationsRatio")), "prevClose": None,
                        "at": (d.get("localTradedAt") or "")[:16] or None, "status": d.get("marketStatus"), "src": "naver"}
        except Exception:
            continue
    return None

def safe(fn, *a):
    try: return fn(*a)
    except Exception as e:
        return None

def main():
    tk = json.load(open("tickers.json"))
    kr = naver_kr(tk["KR"])
    missing = [c for c in tk["KR"] if c not in kr]
    with cf.ThreadPoolExecutor(8) as ex:
        for c, r in zip(missing, ex.map(lambda c: safe(yahoo, c + ".KS") or safe(yahoo, c + ".KQ"), missing)):
            if r and r.get("price"): kr[c] = r
        us = {}
        for t, r in zip(tk["US"], ex.map(lambda t: safe(yahoo, t.replace(".", "-")) or safe(naver_us, t), tk["US"])):
            if r and r.get("price"): us[t] = r
    fx = safe(yahoo, "KRW=X")
    out = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"),
           "fxUSDKRW": fx and fx.get("price"), "fxAt": fx and fx.get("at"),
           "KR": kr, "US": us,
           "missing": {"KR": [c for c in tk["KR"] if c not in kr], "US": [t for t in tk["US"] if t not in us]}}
    json.dump(out, open("prices.json", "w"), ensure_ascii=False, indent=0, sort_keys=True)
    print(f"KR {len(kr)}/{len(tk['KR'])}  US {len(us)}/{len(tk['US'])}  FX {out['fxUSDKRW']}")
    print("missing", out["missing"])

if __name__ == "__main__":
    main()
