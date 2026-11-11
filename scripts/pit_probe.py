import json
from pykrx import stock
out = {}
for c in ("005930", "134780", "028080"):
    try:
        o = stock.get_market_cap("20190101", "20201231", c)
        out[c] = {"rows": len(o), "cols": list(map(str, o.columns)), "head": o.head(2).reset_index().astype(str).values.tolist(), "tail": o.tail(2).reset_index().astype(str).values.tolist()}
    except Exception as e:
        out[c] = {"err": repr(e)[:300]}
json.dump(out, open("pit_probe.json", "w"), ensure_ascii=False, indent=1); print(json.dumps(out, ensure_ascii=False))
