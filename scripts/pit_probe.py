import json, re, urllib.request
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"}
out = {}
def fch(c, rt):
    x = urllib.request.urlopen(urllib.request.Request(f"https://fchart.stock.naver.com/sise.nhn?symbol={c}&timeframe=day&count=1000&requestType={rt}", headers=UA), timeout=20).read().decode("euc-kr", "replace")
    return {m.split("|")[0]: m.split("|")[4] for m in re.findall(r'data="([^"]+)"', x)}
for c, a, b in (("086520", "20240410", "20240430"), ("247540", "20230510", "20230530")):
    out[c] = {}
    for rt in (0, 1):
        try:
            d = fch(c, rt); out[c][f"fchart{rt}"] = {k: v for k, v in d.items() if a <= k <= b}
        except Exception as e: out[c][f"fchart{rt}"] = repr(e)[:100]
    try:
        from pykrx import stock
        o = stock.get_market_ohlcv(a, b, c); out[c]["pykrx"] = {str(k)[:10]: float(v) for k, v in o["종가"].items()}
    except Exception as e: out[c]["pykrx"] = repr(e)[:100]
json.dump(out, open("pit_probe.json", "w"), ensure_ascii=False, indent=1); print(json.dumps(out, ensure_ascii=False)[:3000])
