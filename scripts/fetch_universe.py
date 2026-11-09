"""Daily: build the Korean candidate universe from Naver -> universe.json, and add the codes to tickers.json.
Picks KOSPI+KOSDAQ common stocks with market cap >= MIN_CAP and enough daily trading value,
then pulls fundamentals (PER, forward PER, PBR, ROE, operating margin, debt ratio, dividend yield) and industry."""
import json, re, time, datetime as dt, urllib.request, urllib.parse
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

DEBUG = {}
def industry_name(no):
    """name of a Naver industry group number, via the mobile API"""
    try:
        d = get(f"https://m.stock.naver.com/api/stocks/industry/{no}?page=1&pageSize=1")
        g = d.get("groupInfo") or {}
        return g.get("name") or g.get("groupName") or ""
    except Exception as e:
        DEBUG.setdefault("indErr", str(e)); return ""

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
    ("지주·건설", ["건설", "지주", "부동산", "복합기업"]), ("상사·무역", ["무역회사", "상사"]), ("미디어", ["방송", "광고", "출판", "미디어", "엔터"]),
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

TODAY = dt.datetime.now(KST).date()
def next_date(text):
    """earliest date today or later found in a blob of text (YYYY-MM-DD, YYYY.MM.DD or YYYYMMDD)"""
    best = None
    for y, m, d in re.findall(r"(20\d\d)[-./]?(\d\d)[-./]?(\d\d)", text):
        try: x = dt.date(int(y), int(m), int(d))
        except ValueError: continue
        if x >= TODAY and (best is None or x < best): best = x
    return best.isoformat() if best else None

def fundamentals(code, ind_names):
    r = {}
    try:
        g = get(f"https://m.stock.naver.com/api/stock/{code}/integration")
        ti = {x.get("code"): x.get("value") for x in g.get("totalInfos", [])}
        r.update(pe=num(ti.get("per")), forwardPE=num(ti.get("cnsPer")), pb=num(ti.get("pbr")),
                 dividendYield=num(ti.get("dividendYieldRatio")),
                 high52=num(ti.get("highPriceOf52Weeks")), low52=num(ti.get("lowPriceOf52Weeks")))
        no = str(g.get("industryCode") or "")
        if no and no not in ind_names: ind_names[no] = industry_name(no)
        ind = ind_names.get(no, "")
        r["industry"] = ind
        ir = g.get("irScheduleInfo")
        if ir:
            DEBUG.setdefault("irSample", json.dumps(ir, ensure_ascii=False)[:600])
            r["earnDate"] = next_date(json.dumps(ir, ensure_ascii=False))
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

# ---------------- US: Naver lists (Korean names, sector) + Yahoo fundamentals ----------------
MIN_US_CAP = 10e9          # $10B
MAX_US = 300
US_SECTOR = [("반도체", ["반도체"]), ("IT 하드웨어", ["하드웨어", "전자", "통신장비", "컴퓨터"]), ("인터넷·소프트웨어", ["소프트웨어", "인터넷", "IT서비스", "게임", "양방향"]),
    ("통신", ["통신서비스", "무선통신"]), ("결제", ["결제", "카드"]), ("금융", ["은행", "보험", "증권", "금융", "자본시장", "리츠", "부동산투자"]),
    ("자동차", ["자동차"]), ("제약·바이오", ["제약", "바이오", "생명", "건강", "의료"]), ("2차전지·화학", ["화학"]), ("철강·소재", ["금속", "광업", "철강", "소재", "포장", "종이"]),
    ("방산·조선·중공업", ["항공우주", "국방", "기계", "건설장비", "전기장비", "산업"]), ("에너지·유틸리티", ["석유", "가스", "에너지", "유틸리티", "전력"]),
    ("운송", ["운송", "철도", "항공", "해운", "물류", "트럭"]), ("소비·유통", ["소매", "식품", "음료", "담배", "가정", "의류", "섬유", "소비", "유통", "개인"]),
    ("미디어", ["미디어", "엔터", "방송", "광고"]), ("여행·레저", ["호텔", "레스토랑", "레저", "여행", "카지노"]), ("지주·건설", ["건설", "복합", "지주"])]
def us_sector(ind):
    for sec, keys in US_SECTOR:
        if any(k in (ind or "") for k in keys): return sec
    return "기타"

def us_listing():
    out = []
    for ex in ("NYSE", "NASDAQ"):
        for page in range(1, 6):
            try: d = get(f"https://api.stock.naver.com/stock/exchange/{ex}/marketValue?page={page}&pageSize=100")
            except Exception as e: print("us list fail", ex, page, e); break
            xs = d.get("stocks") or []
            if not xs: break
            stop = False
            for s in xs:
                cap = num(s.get("marketValue"))
                cap = cap * 1000 if cap else None          # Naver gives thousands of USD
                if not cap or cap < MIN_US_CAP: stop = True; break
                if s.get("stockEndType") != "stock": continue
                ind = (s.get("industryCodeType") or {}).get("industryGroupKor") or ""
                out.append({"t": s.get("symbolCode") or s.get("reutersCode"), "name": s.get("stockName"), "cap": cap,
                            "price": num(s.get("closePrice")), "industry": ind, "dividendYield": num(s.get("dividendYield")),
                            "nation": (s.get("nationType") or "")})
            if stop: break
            time.sleep(0.3)
    seen, uniq = set(), []
    for x in sorted(out, key=lambda x: -x["cap"]):
        if x["t"] and x["t"] not in seen: seen.add(x["t"]); uniq.append(x)
    return uniq[:MAX_US]

class Yahoo:
    def __init__(self):
        import http.cookiejar
        self.cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))
        self.h = {"User-Agent": UA["User-Agent"]}
        try: self.op.open(urllib.request.Request("https://fc.yahoo.com", headers=self.h), timeout=15)
        except Exception: pass
        self.crumb = self.op.open(urllib.request.Request("https://query2.finance.yahoo.com/v1/test/getcrumb", headers=self.h), timeout=15).read().decode()
    def summary(self, t):
        mods = "financialData,defaultKeyStatistics,summaryDetail,calendarEvents,price"
        u = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{t.replace('.', '-')}?modules={mods}&crumb={urllib.parse.quote(self.crumb)}"
        for i in range(3):
            try:
                return json.loads(self.op.open(urllib.request.Request(u, headers=self.h), timeout=15).read())["quoteSummary"]["result"][0]
            except Exception as e:
                err = e; time.sleep(1 + 2 * i)
        raise err

def rv(d, k):
    v = (d or {}).get(k)
    return v.get("raw") if isinstance(v, dict) else v

def us_fund(y, x):
    q = y.summary(x["t"])
    fd, ks, sd, ce, pr = (q.get(k) or {} for k in ("financialData", "defaultKeyStatistics", "summaryDetail", "calendarEvents", "price"))
    cap = rv(pr, "marketCap") or x["cap"]
    fcf = rv(fd, "freeCashflow")
    de = rv(fd, "debtToEquity")
    ed = [e.get("fmt") for e in ((ce.get("earnings") or {}).get("earningsDate") or []) if isinstance(e, dict)]
    country = None
    pct = lambda v: round(v * 100, 2) if isinstance(v, (int, float)) else None
    return {"pe": rv(sd, "trailingPE"), "forwardPE": rv(sd, "forwardPE") or rv(ks, "forwardPE"), "pb": rv(ks, "priceToBook"),
            "roe": pct(rv(fd, "returnOnEquity")), "operatingMargin": pct(rv(fd, "operatingMargins")),
            "debtToEquity": round(de / 100, 3) if isinstance(de, (int, float)) else None,
            "fcfYield": round(fcf / cap * 100, 2) if fcf and cap else None,
            "dividendYield": pct(rv(sd, "dividendYield")) if rv(sd, "dividendYield") is not None else x.get("dividendYield"),
            "earnDate": next((d for d in ed if d and d >= TODAY.isoformat()), None), "marketCap": int(cap)}

def us_universe():
    xs = us_listing()
    try: y = Yahoo()
    except Exception as e:
        print("yahoo crumb fail", e); DEBUG["yahooErr"] = str(e); y = None
    US = {}
    def one(x):
        f = {}
        if y:
            try: f = us_fund(y, x)
            except Exception as e: f = {"err": str(e)[:80]}
        return x, f
    with cf.ThreadPoolExecutor(4) as ex:
        for x, f in ex.map(one, xs):
            sec = us_sector(x["industry"])
            US[x["t"]] = {"name": x["name"], "price": x["price"], "industry": x["industry"], "sector": sec, "fin": sec in ("금융",),
                          "marketCap": int(x["cap"]), **f}
            if sec == "금융": US[x["t"]].update(operatingMargin=None, debtToEquity=None, fcfYield=None)
    DEBUG["usFundOK"] = sum(1 for v in US.values() if v.get("roe") is not None)
    return US

def us_probe():
    out = {}
    try:
        d = get("https://api.stock.naver.com/stock/exchange/NYSE/marketValue?page=1&pageSize=3")
        out["list"] = d
        rc = (d.get("stocks") or [{}])[0].get("reutersCode")
        if rc:
            out["integration"] = get(f"https://api.stock.naver.com/stock/{rc}/integration")
            out["annual"] = get(f"https://api.stock.naver.com/stock/{rc}/finance/annual")
    except Exception as e:
        out["err"] = str(e)
    json.dump(out, open("us_probe.json", "w"), ensure_ascii=False, indent=1)

def main():
    US = us_universe()
    try: ind_names = industries()
    except Exception as e: print("industry list fail", e); DEBUG["upjongErr"] = str(e); ind_names = {}
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
               "count": len(KR), "countUS": len(US), "KR": KR, "US": US, "debug": DEBUG}, open("universe.json", "w"), ensure_ascii=False, indent=0, sort_keys=True)
    tk = json.load(open("tickers.json"))
    tk["KR"] = sorted(set(tk["KR"]) | set(KR))
    tk["US"] = sorted(set(tk["US"]) | set(US))
    json.dump(tk, open("tickers.json", "w"), indent=1)
    print(f"universe KR {len(KR)} (from {len(cands)} over {MIN_CAP_EOK}억), industries {len(ind_names)}")

if __name__ == "__main__":
    main()
