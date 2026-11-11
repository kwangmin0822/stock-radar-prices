"""Probe 2: delisted-company list from KIND and price history for delisted codes; Naver full listing with shares."""
import json, re, traceback, urllib.request, urllib.parse
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"}
out = {}
def get(u, data=None, hdr=None):
    req = urllib.request.Request(u, data=urllib.parse.urlencode(data).encode() if data else None, headers={**UA, **(hdr or {})})
    with urllib.request.urlopen(req, timeout=30) as r: return r.read()
try:
    b = get("https://kind.krx.co.kr/investwarn/delcompany.do", {"method": "searchDelCompanySub", "currentPageSize": "3000", "pageIndex": "1",
            "orderMode": "1", "orderStat": "D", "marketType": "", "searchCorpName": "", "fromDate": "2018-01-01", "toDate": "2026-11-10"},
            {"Referer": "https://kind.krx.co.kr/investwarn/delcompany.do?method=searchDelCompanyMain"}).decode("utf-8", "replace")
    rows = re.findall(r"<tr>(.*?)</tr>", b, re.S)
    out["kind_len"] = len(b); out["kind_rows"] = len(rows); out["kind_sample"] = [re.sub(r"<[^>]+>|\s+", " ", r).strip() for r in rows[:6]]
except Exception:
    out["kind_err"] = traceback.format_exc()[-400:]
try:
    from pykrx import stock
    for code in ("036570", "015760"):
        o = stock.get_market_ohlcv("20190101", "20191231", code); out["ohlcv_" + code] = len(o)
except Exception:
    out["pykrx_err"] = traceback.format_exc()[-300:]
codes = re.findall(r"\b(\d{6})\b", " ".join(out.get("kind_sample", [])))[:4]
out["delisted_try"] = {}
for c in codes:
    try:
        from pykrx import stock
        o = stock.get_market_ohlcv("20180101", "20261110", c); out["delisted_try"][c] = {"pykrx": len(o), "last": str(o.index[-1]) if len(o) else None}
    except Exception as e:
        out["delisted_try"][c] = {"pykrx_err": repr(e)[:150]}
    try:
        x = get(f"https://fchart.stock.naver.com/sise.nhn?symbol={c}&timeframe=day&count=3000&requestType=0").decode("euc-kr", "replace")
        out["delisted_try"][c]["naver"] = len(re.findall(r'data="', x))
    except Exception as e:
        out["delisted_try"][c]["naver_err"] = repr(e)[:100]
print(json.dumps(out, ensure_ascii=False, indent=1))
json.dump(out, open("pit_probe.json", "w"), ensure_ascii=False, indent=1)
