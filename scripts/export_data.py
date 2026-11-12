"""Dump the raw data behind pit_us7.py (adopted US strategy) so it can be re-checked offline by anyone.
Fetches exactly what pit_us7 fetches (Naver US list of stocks >= $2B today, Yahoo v8 chart range=10y with
events=div|split, SPY, KRW=X), saves it untouched as Parquet, then:
  - runs backtest_offline.py on the saved files,
  - runs the original pit_us7.run() on the same matrices and checks both give the same curves,
  - runs the code checks asked by ChatGPT,
  - tries Yahoo's historical share counts (fundamentals-timeseries) to measure the market-cap bias.
Output folder: export/ (uploaded as a workflow artifact, not committed)."""
import json, os, time, datetime as dt, urllib.request, urllib.parse
import concurrent.futures as cf
import numpy as np
import pandas as pd
from signals2 import YUA, _op, CRUMB
from signals9 import get
import backtest_offline as bo
import pit_us7

OUT = "export"; DATA = os.path.join(OUT, "data"); RES = os.path.join(OUT, "results")
os.makedirs(DATA, exist_ok=True); os.makedirs(RES, exist_ok=True)
day = lambda a: dt.datetime.utcfromtimestamp(int(a)).strftime("%Y%m%d")


def naver_list(min_cap=2e9):
    """Same loop as pit_us.us_all(), but keeps the raw rows."""
    rows, SH = [], {}
    for ex in ("NYSE", "NASDAQ"):
        for page in range(1, 40):
            try: d = json.loads(get(f"https://api.stock.naver.com/stock/exchange/{ex}/marketValue?page={page}&pageSize=100"))
            except Exception: time.sleep(2); continue
            xs = d.get("stocks") or []
            if not xs: break
            stop = False
            for s in xs:
                try:
                    cap = float(str(s.get("marketValue")).replace(",", "")) * 1000; px = float(str(s.get("closePrice")).replace(",", ""))
                except Exception: continue
                if cap < min_cap: stop = True; break
                if s.get("stockEndType") != "stock" or px <= 0: continue
                t = s.get("symbolCode") or s.get("reutersCode")
                if t:
                    SH[t] = cap / px
                    rows.append(dict(ticker=t, exchange=ex, name=s.get("stockName"), name_en=s.get("stockNameEng"),
                                     reuters_code=s.get("reutersCode"), market_value_raw=str(s.get("marketValue")),
                                     close_raw=str(s.get("closePrice")), market_cap_usd=cap, shares_today=cap / px,
                                     industry=(s.get("industryCodeType") or {}).get("industryGroupKor") if isinstance(s.get("industryCodeType"), dict) else None))
            if stop: break
            time.sleep(0.3)
    df = pd.DataFrame(rows).drop_duplicates("ticker", keep="last")   # dict overwrite in us_all() keeps the last one
    return df, SH


def chart_raw(t):
    """Same request as pit_us2.chart(); returns every field."""
    for i in range(4):
        try:
            u = (f"https://query{1 + i % 2}.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(t.replace('.', '-'))}"
                 f"?interval=1d&range=10y&events=div%7Csplit&crumb={urllib.parse.quote(CRUMB)}")
            with _op.open(urllib.request.Request(u, headers=YUA), timeout=25) as r:
                d = json.loads(r.read())["chart"]["result"][0]
            q = d["indicators"]["quote"][0]; ev = d.get("events") or {}
            adj = d["indicators"].get("adjclose", [{}])[0].get("adjclose") or [None] * len(d["timestamp"])
            px = pd.DataFrame(dict(ticker=t, date=[day(a) for a in d["timestamp"]], open=q.get("open"), high=q.get("high"),
                                   low=q.get("low"), close=q.get("close"), adjclose=adj, volume=q.get("volume")))
            sp = pd.DataFrame([dict(ticker=t, date=day(v["date"]), numerator=v.get("numerator"), denominator=v.get("denominator"),
                                    ratio=v["numerator"] / v["denominator"]) for v in (ev.get("splits") or {}).values() if v.get("denominator")])
            dv = pd.DataFrame([dict(ticker=t, date=day(v["date"]), amount=v["amount"]) for v in (ev.get("dividends") or {}).values()])
            meta = d.get("meta", {})
            return px, sp, dv, dict(ticker=t, currency=meta.get("currency"), exchange=meta.get("exchangeName"),
                                    first_trade=day(meta["firstTradeDate"]) if meta.get("firstTradeDate") else None,
                                    instrument=meta.get("instrumentType"))
        except Exception:
            time.sleep(1 + 2 * i)
    return None, None, None, dict(ticker=t, error="fetch failed")


def shares_hist(t):
    """Yahoo fundamentals-timeseries: reported share counts (usually only the last ~4-5 years)."""
    p1, p2 = int(dt.datetime(2015, 1, 1).timestamp()), int(time.time())
    typ = "quarterlyBasicAverageShares,annualBasicAverageShares,quarterlyOrdinarySharesNumber,annualOrdinarySharesNumber"
    for i in range(3):
        try:
            u = (f"https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{urllib.parse.quote(t.replace('.', '-'))}"
                 f"?type={typ}&period1={p1}&period2={p2}&crumb={urllib.parse.quote(CRUMB)}")
            with _op.open(urllib.request.Request(u, headers=YUA), timeout=25) as r:
                res = json.loads(r.read())["timeseries"]["result"]
            out = []
            for x in res:
                k = x["meta"]["type"][0]
                for v in x.get(k) or []:
                    if v and v.get("reportedValue"): out.append(dict(ticker=t, type=k, as_of=v["asOfDate"].replace("-", ""), shares=v["reportedValue"]["raw"]))
            return out
        except Exception:
            time.sleep(1 + 2 * i)
    return []


def main():
    log = {"fetched_at_kst": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds"), "crumb_ok": bool(CRUMB)}
    uni, SH = naver_list(); tick = sorted(SH)
    print("naver tickers", len(tick), flush=True)
    with cf.ThreadPoolExecutor(4) as ex: R = list(ex.map(chart_raw, tick))
    spy = chart_raw("SPY"); fxr = chart_raw("KRW=X")
    P_ = pd.concat([r[0] for r in R if r[0] is not None], ignore_index=True)
    S_ = pd.concat([r[1] for r in R if r[1] is not None and len(r[1])], ignore_index=True)
    D_ = pd.concat([r[2] for r in R if r[2] is not None and len(r[2])], ignore_index=True)
    M_ = pd.DataFrame([r[3] for r in R])
    uni = uni.merge(M_, on="ticker", how="left", suffixes=("", "_yahoo"))
    P_.to_parquet(os.path.join(DATA, "us_prices_daily.parquet"), index=False)
    S_.to_parquet(os.path.join(DATA, "us_splits.parquet"), index=False)
    D_.to_parquet(os.path.join(DATA, "us_dividends.parquet"), index=False)
    uni.to_parquet(os.path.join(DATA, "us_universe_shares.parquet"), index=False)
    spy[0].to_parquet(os.path.join(DATA, "spy_daily.parquet"), index=False)
    if spy[2] is not None and len(spy[2]): spy[2].to_parquet(os.path.join(DATA, "spy_dividends.parquet"), index=False)
    fxr[0].to_parquet(os.path.join(DATA, "usdkrw_daily.parquet"), index=False)
    log["naver_tickers"] = len(tick); log["yahoo_failed"] = [r[3]["ticker"] for r in R if r[0] is None]

    # ---- offline replay on the saved files ----
    D, S, rows = bo.main(DATA, RES)
    log["used_tickers(>300 closes)"] = D["n"]

    # signals: every eligible (ticker, day) with its 6-1 trend, rank and that day's market cap
    dates, tk = D["dates"], D["tick"]
    ii, jj = np.where(S["E"])
    sig = pd.DataFrame(dict(date=np.array(dates)[ii], ticker=np.array(tk)[jj], mom6_1=S["SIG"][ii, jj],
                            mcap_usd_est=S["capm"][ii, jj], split_adj_close=D["P"][ii, jj]))
    sig["rank"] = sig.groupby("date")["mom6_1"].rank(ascending=False, method="first")
    sig.to_parquet(os.path.join(DATA, "signals_eligible_daily.parquet"), index=False)
    pd.DataFrame(dict(date=dates, top20_minus_bottom20_20d=S["spread"], crash_flag=S["crash"],
                      buy_blocked_next_day=S["crash"])).to_csv(os.path.join(DATA, "crash_signal_daily.csv"), index=False)

    # ---- the original pit_us7.run() on the same matrices: must give the same numbers ----
    starts = list(range(bo.FIRST, D["T"] - bo.WIN, bo.STEP)); worst = 0.0
    for sname, st in bo.SCEN:
        for a in starts:
            c1, f1, t1 = pit_us7.run(D["P"], D["LOT"], D["DIV"], D["alive"], S["E"], S["SIG"], S["crash"], D["fx"], dates,
                                     a, a + bo.WIN, st, bo.DEP, topn=3, stop=None)
            c2, f2, t2 = bo.run(D, S, a, a + bo.WIN, st, bo.DEP)
            worst = max(worst, float(np.max(np.abs(c1 - c2))), abs(t1 - t2))
    log["offline_vs_pit_us7_max_abs_diff_krw"] = worst

    # ---- code checks ----
    chk = {}
    cr = S["crash"]; runs, k = [], 0
    while k < len(cr):
        if cr[k]:
            e = k
            while e + 1 < len(cr) and cr[e + 1]: e += 1
            runs.append((dates[k], dates[e], e - k + 1)); k = e + 1
        else: k += 1
    sp = S["spread"]; trig = [dates[i] for i in range(len(sp)) if not np.isnan(sp[i]) and sp[i] < -0.10]
    chk["1_crash_pause"] = {"trigger_days": len(trig), "blocked_runs(first_flag, last_flag, rows)": runs[:40],
                            "isolated_trigger_run_lengths": sorted(set(r[2] for r in runs))}
    rr = pd.DataFrame(rows)
    chk["2_max_holdings_by_scenario"] = rr.groupby("scenario")["max_holdings"].max().to_dict()
    tr_all = pd.concat([pd.read_csv(os.path.join(RES, f)) for f in os.listdir(RES) if f.startswith("trades_")])
    chk["3_delist_sells"] = int((tr_all["reason"] == "delisted/no-more-data").sum())
    ends = {t: max(d for d in g["date"]) for t, g in P_[P_["close"].notna()].groupby("ticker")}
    chk["3_tickers_whose_data_ends_before_last_day"] = {t: e for t, e in ends.items() if t in tk and e < dates[-1]}
    # dividends vs splits: are Yahoo dividend amounts already split-adjusted?
    ex = {}
    for t in ("AAPL", "NVDA", "TSLA", "WMT", "AVGO", "GOOGL", "AMZN"):
        g = D_[D_["ticker"] == t].sort_values("date"); s = S_[S_["ticker"] == t]
        if len(g): ex[t] = {"splits": s[["date", "ratio"]].values.tolist(), "dividends_first5": g.head(5)[["date", "amount"]].values.tolist(),
                            "dividends_last5": g.tail(5)[["date", "amount"]].values.tolist()}
    chk["5_dividend_vs_split_examples"] = ex
    json.dump(chk, open(os.path.join(RES, "code_checks.json"), "w"), ensure_ascii=False, indent=1, default=str)

    # ---- historical share counts for names that ever came near the $50B line ----
    near = sorted({tk[j] for j in np.where((S["capm"] >= 2.5e10).any(0))[0]})
    with cf.ThreadPoolExecutor(4) as ex_: H = list(ex_.map(shares_hist, near))
    sh = pd.DataFrame([x for h in H for x in h])
    if len(sh): sh.to_parquet(os.path.join(DATA, "us_shares_history_yahoo.parquet"), index=False)
    log["shares_history_tickers_asked"] = len(near); log["shares_history_tickers_got"] = int(sh["ticker"].nunique()) if len(sh) else 0
    log["shares_history_earliest"] = sh["as_of"].min() if len(sh) else None
    json.dump(log, open(os.path.join(OUT, "export_log.json"), "w"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps(log, ensure_ascii=False, default=str)[:2000])


if __name__ == "__main__":
    main()
