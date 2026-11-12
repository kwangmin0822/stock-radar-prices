"""Dated share counts from SEC EDGAR XBRL (company filings), for the past-market-cap fix.
For every ticker in the exported universe: ticker -> CIK (sec.gov/files/company_tickers.json), then
companyconcept dei/EntityCommonStockSharesOutstanding (cover page, every 10-K/10-Q/20-F) and
us-gaap/CommonStockSharesOutstanding (balance sheet). Values are raw share counts on 'end' (NOT split-adjusted).
Output: sec_shares.parquet (ticker, cik, concept, end, val, accn, form, fy, fp, filed)."""
import json, sys, time, urllib.request
import pandas as pd

UA = {"User-Agent": "stock-radar-prices research script (github.com/kwangmin0822/stock-radar-prices) price-bot@users.noreply.github.com",
      "Accept-Encoding": "identity"}

def get(u):
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30) as r: return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 404: return None
            time.sleep(2 + 3 * i)
        except Exception:
            time.sleep(2 + 3 * i)
    return None

def main(universe_parquet, out):
    tick = list(pd.read_parquet(universe_parquet)["ticker"])
    m = get("https://www.sec.gov/files/company_tickers.json") or {}
    cik = {v["ticker"].upper(): int(v["cik_str"]) for v in m.values()}
    rows, miss = [], []
    for t in tick:
        c = cik.get(t.upper()) or cik.get(t.upper().replace(".", "-")) or cik.get(t.upper().replace(" ", "-"))
        if not c: miss.append(t); continue
        for concept in ("dei/EntityCommonStockSharesOutstanding", "us-gaap/CommonStockSharesOutstanding"):
            d = get(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{c:010d}/{concept}.json")
            time.sleep(0.15)
            if not d: continue
            for x in (d.get("units") or {}).get("shares", []):
                rows.append(dict(ticker=t, cik=c, concept=concept.split("/")[1], end=x["end"].replace("-", ""), val=float(x["val"]),
                                 accn=x.get("accn"), form=x.get("form"), fy=x.get("fy"), fp=x.get("fp"), filed=(x.get("filed") or "").replace("-", "")))
    df = pd.DataFrame(rows); df.to_parquet(out, index=False)
    print("tickers", len(tick), "no CIK", len(miss), "with data", df["ticker"].nunique() if len(df) else 0, "rows", len(df))
    json.dump({"no_cik": miss}, open(out.replace(".parquet", "_missing.json"), "w"))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
