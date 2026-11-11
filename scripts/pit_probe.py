import json, re, traceback, urllib.request
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"}
out = {}
from pykrx import stock
for c in ("028080", "134780", "005940", "057050"):
    try:
        o = stock.get_market_ohlcv("20180101", "20261110", c)
        out[c] = {"pykrx": len(o), "first": str(o.index[0])[:10] if len(o) else None, "last": str(o.index[-1])[:10] if len(o) else None,
                  "tail": o.tail(3).reset_index().astype(str).values.tolist() if len(o) else None}
    except Exception as e:
        out[c] = {"pykrx_err": repr(e)[:200]}
    try:
        x = urllib.request.urlopen(urllib.request.Request(f"https://fchart.stock.naver.com/sise.nhn?symbol={c}&timeframe=day&count=3000&requestType=0", headers=UA), timeout=20).read().decode("euc-kr", "replace")
        d = re.findall(r'data="([^"]+)"', x); out[c]["naver"] = len(d); out[c]["naver_last"] = d[-1] if d else None
    except Exception as e:
        out[c]["naver_err"] = repr(e)[:100]
print(json.dumps(out, ensure_ascii=False, indent=1)); json.dump(out, open("pit_probe.json", "w"), ensure_ascii=False, indent=1)
