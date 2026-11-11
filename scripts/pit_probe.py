"""Probe: can we get point-in-time Korean market caps (incl. later-delisted names) from KRX via pykrx?"""
import json, traceback
out = {}
try:
    from pykrx import stock
    for d in ("20190502", "20220502", "20260105"):
        try:
            df = stock.get_market_cap_by_ticker(d, market="ALL")
            out[d] = {"rows": int(len(df)), "cols": list(map(str, df.columns)), "big": int((df["시가총액"] >= 3e11).sum()) if "시가총액" in df else None,
                      "sample": df.head(3).reset_index().astype(str).values.tolist()}
        except Exception as e:
            out[d] = {"err": repr(e)[:300]}
    try:
        o = stock.get_market_ohlcv("20190101", "20191231", "000040")
        out["ohlcv"] = {"rows": int(len(o)), "cols": list(map(str, o.columns))}
    except Exception as e:
        out["ohlcv"] = {"err": repr(e)[:300]}
except Exception:
    out["import"] = traceback.format_exc()[-500:]
print(json.dumps(out, ensure_ascii=False, indent=1))
json.dump(out, open("pit_probe.json", "w"), ensure_ascii=False, indent=1)
