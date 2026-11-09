"""Daily: build the Korean candidate universe from Naver -> universe.json, and add the codes to tickers.json.
Picks KOSPI+KOSDAQ common stocks with market cap >= MIN_CAP and enough daily trading value,
then pulls fundamentals (PER, forward PER, PBR, ROE, operating margin, debt ratio, dividend yield) and industry."""
import json, re, time, datetime as dt, urllib.request
import concurrent.futures as cf

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
      "Accept": "application/json,text/plain,*/*", "Referer": "https://m.stock.naver.com/"}
KST = dt.timezone(dt.timedelta(hours=9))
MIN_CAP_EOK = 3000          # 3,000억 원
MIN_TV_EOK = 10             # daily trading value >= 10억 원 (liquidity)
MAX_KR = 200                # biggest N that pass the filters

def raw(url, enc="utf-8"):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
        return r.read().decode(enc, "replace")

def get(url): return json.loads(raw(url))

def num(x):
    if x is None: return None
    s = re.sub(r"[^0-9.\-]", "", str(x))
    try: return float(s) if s not in ("", "-", ".") else None
    except ValueError: return None

def industries():
    """upjong number -> name from the Naver industry page"""
    h = raw("https://finance.naver.com/sise/sise_group.naver?type=upjong", "euc-kr")
    return {no: re.sub(r"\s+", " ", nm).strip() for no, nm in re.findall(r'type=upjong&(?:amp;)?no=(\d+)"\s*>([^<]+)<', h)}

# page sector list; first keyword hit wins
SECTOR_KEYS = [
    ("반도체", ["반도체"]), ("IT 하드웨어", ["전자장비", "디스플레이", "전자제품", "컴퓨터", "전기장비", "통신장비", "핸드셋", "사무용"]),
    ("인터넷·소프트웨어", ["소프트웨어", "인터넷", "게임", "IT서비스"]), ("통신", ["통신서비스", "무선통신", "다각화된통신"]),
    ("금융", ["은행", "보험", "증권", "카드", "금융", "창업투자"]), ("자동차", ["자동차", "타이어"]),
    ("제약·바이오", ["제약", "생물공학", "생명과학", "건강관리"]), ("2차전지·화학", ["화학", "전기제품"]),
    ("철강·소재", ["철강", "비철금속", "종이", "포장재", "건축자재"]), ("방산·조선·중공업", ["조선", "우주항공", "국방", "기계", "건축제품"]),
    ("에너지·유틸리티", ["석유", "가스", "전기유틸리티", "에너지", "복합유틸리티"]), ("운송", ["해운", "항공", "도로", "철도", "운송"]),
    ("소비·유통", ["식품", "음료", "담배", "화장품", "섬유", "의류", "백화점", "판매", "소매", "가정용", "레저용품", "교육", "생활용품"]),
    ("지주·건설", ["건설", "지주", "부동산"]), ("상사·무역", ["무역회사", "상사"]), ("미디어", ["방송", "광고", "출판", "미디어", "엔터"]),
    ("여행·레저", ["호텔", "레스토랑", "레저"]),
]
def sector_of(ind):
    for sec, keys in SECTOR_KEYS:
        if any(k in ind for k in keys): return sec
    return "기타"

def listing(market):
    out = []
    for page in range(1, 8):
        d = get(f"https://m.stock.naver.com/api/stocks/marketValue/{market}?page={page}&pageSize=100")
        xs = d.get("stocks") or []
        if not xs: break
        for s in xs:
            cap = num(s.get("marketValue"))       # 억 원
            if cap is None or cap < MIN_CAP_EOK: return out
            name = s.get("stockName") or ""
            code = s.get("itemCode") or ""
            if s.get("stockEndType") != "stock" or not code.endswith("0"): continue      # preferred shares end in 5/7/9/K
            if "스팩" in name or re.search(r"우[BC]?$", name): continue
            tv = num(s.get("accumulatedTradingValue"))   # 백만 원, today so far
            out.append({"code": code, "name": name, "market": market, "capEok": cap,
                        "price": num(s.get("closePrice")), "tvEok": (tv or 0) / 100})
        time.sleep(0.3)
    return out

def latest(cols, keys):
    """newest actual (non-consensus) value in a finance row"""
    for k in keys:
        v = num((cols.get(k) or {}).get("value"))
        if v is not None: return v
    return None

def fundamentals(code, ind_names):
    r = {}
    try:
        g = get(f"https://m.stock.naver.com/api/stock/{code}/integration")
        ti = {x.get("code"): x.get("value") for x in g.get("totalInfos", [])}
        r.update(pe=num(ti.get("per")), forwardPE=num(ti.get("cnsPer")), pb=num(ti.get("pbr")),
                 dividendYield=num(ti.get("dividendYieldRatio")),
                 high52=num(ti.get("highPriceOf52Weeks")), low52=num(ti.get("lowPriceOf52Weeks")))
        ind = ind_names.get(str(g.get("industryCode") or ""), "")
        r["industry"] = ind
    except Exception as e:
        print("integration fail", code, e)
    try:
        f = get(f"https://m.stock.naver.com/api/stock/{code}/finance/annual")["financeInfo"]
        keys = [t["key"] for t in f["trTitleList"] if t.get("isConsensus") == "N"][::-1]
        rows = {x["title"]: x["columns"] for x in f["rowList"]}
        r.update(roe=latest(rows.get("ROE", {}), keys), operatingMargin=latest(rows.get("영업이익률", {}), keys))
        debt = latest(rows.get("부채비율", {}), keys)
        r["debtToEquity"] = round(debt / 100, 3) if debt is not None else None
        r["dataDate"] = keys[0] if keys else None
    except Exception as e:
        print("finance fail", code, e)
    return r

def main():
    try: ind_names = industries()
    except Exception as e: print("industry list fail", e); ind_names = {}
    cands = listing("KOSPI") + listing("KOSDAQ")
    # liquidity: today's value can be small early in the session, so also keep the 120 biggest regardless
    cands.sort(key=lambda x: -x["capEok"])
    keep = [c for i, c in enumerate(cands) if i < 120 or c["tvEok"] >= MIN_TV_EOK][:MAX_KR]
    with cf.ThreadPoolExecutor(6) as ex:
        funds = list(ex.map(lambda c: fundamentals(c["code"], ind_names), keep))
    KR = {}
    for c, f in zip(keep, funds):
        ind = f.pop("industry", "")
        sec = sector_of(ind)
        KR[c["code"]] = {"name": c["name"], "market": c["market"], "marketCap": int(c["capEok"] * 1e8), "price": c["price"],
                         "industry": ind, "sector": sec, "fin": sec == "금융", **f}
        if sec == "금융":
            KR[c["code"]].update(operatingMargin=None, debtToEquity=None)
    json.dump({"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "minCapEok": MIN_CAP_EOK, "industries": len(ind_names),
               "count": len(KR), "KR": KR}, open("universe.json", "w"), ensure_ascii=False, indent=0, sort_keys=True)
    tk = json.load(open("tickers.json"))
    tk["KR"] = sorted(set(tk["KR"]) | set(KR))
    json.dump(tk, open("tickers.json", "w"), indent=1)
    print(f"universe KR {len(KR)} (from {len(cands)} over {MIN_CAP_EOK}억), industries {len(ind_names)}")

if __name__ == "__main__":
    main()
