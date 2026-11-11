import json, urllib.request
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36"}
out = {}
for c in ("005930", "134780", "028080", "057050"):
    for u in (f"https://m.stock.naver.com/api/stock/{c}/integration", f"https://m.stock.naver.com/api/stock/{c}/basic"):
        try:
            d = json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=20).read())
            txt = json.dumps(d, ensure_ascii=False)
            i = txt.find("상장주식"); j = txt.find("marketValue")
            out[u] = {"len": len(txt), "shares": txt[i - 20:i + 120] if i >= 0 else None, "mv": txt[j - 10:j + 60] if j >= 0 else None, "keys": list(d)[:15] if isinstance(d, dict) else None}
        except Exception as e:
            out[u] = {"err": repr(e)[:150]}
json.dump(out, open("pit_probe.json", "w"), ensure_ascii=False, indent=1); print(json.dumps(out, ensure_ascii=False))
