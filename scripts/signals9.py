"""Round 9: survivorship check for Korea, as ChatGPT asked.
Earlier tests used today's ~200 large caps for the whole past. Here the candidate list is rebuilt for every day from
ALL Korean common stocks that were trading then - today's listings plus every KOSPI/KOSDAQ company delisted since 2018
(KIND list) - and keeps the 250 most traded (60-day average trading value) as that day's universe.
Delisted stocks are sold at their last traded price (including the liquidation-trading days); halted days (no volume)
cannot be traded, so a stop-loss waits until trading resumes. Same rules, same windows, both universes, no sector cap
(sector names are only known for today's list)."""
import json, re, time, datetime as dt, urllib.request, urllib.parse
import concurrent.futures as cf
import numpy as np
from signals import matrix, signal, KST, UA
from signals4 import evaluate
from signals6 import rankpct
from signals8 import hist_kr

def get(u, data=None, hdr=None):
    req = urllib.request.Request(u, data=urllib.parse.urlencode(data).encode() if data else None, headers={**UA, **(hdr or {})})
    with urllib.request.urlopen(req, timeout=30) as r: return r.read()

def listed():
    out = []
    for mk in ("KOSPI", "KOSDAQ"):
        for page in range(1, 40):
            try: d = json.loads(get(f"https://m.stock.naver.com/api/stocks/marketValue/{mk}?page={page}&pageSize=100"))
            except Exception: time.sleep(2); continue
            xs = d.get("stocks") or []
            if not xs: break
            for s in xs:
                code, name = s.get("itemCode") or "", s.get("stockName") or ""
                if s.get("stockEndType") != "stock" or not code.endswith("0") or "스팩" in name or re.search(r"우[BC]?$", name): continue
                out.append(code)
            time.sleep(0.2)
    return out

def delisted():
    b = get("https://kind.krx.co.kr/investwarn/delcompany.do", {"method": "searchDelCompanySub", "currentPageSize": "3000", "pageIndex": "1",
            "orderMode": "1", "orderStat": "D", "marketType": "", "searchCorpName": "", "fromDate": "2018-01-01", "toDate": "2026-11-11"},
            {"Referer": "https://kind.krx.co.kr/investwarn/delcompany.do?method=searchDelCompanyMain"}).decode("utf-8", "replace")
    out = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", b, re.S):
        m = re.search(r"companysummary_open\('(\d{5})'\)", r); mk = re.search(r"alt='(유가증권|코스닥)'", r)
        if m and mk and "스팩" not in r: out.append(m.group(1) + "0")
    return out

def build(P, V, M, elig, lock):
    T, n = P.shape
    E = elig
    m6 = np.full(P.shape, np.nan); m712 = np.full(P.shape, np.nan)
    m6[126:] = P[105:-21] / P[:-126] - 1
    m712[252:] = P[126:-126] / P[:-252] - 1
    m6 = np.where(E, m6, np.nan); m712 = np.where(E, m712, np.nan)
    rk = rankpct(m6); sigD = np.where(np.isnan(m712), rk, 0.75 * rk + 0.25 * rankpct(m712))
    r = np.full(P.shape, np.nan); r[1:] = P[1:] / P[:-1] - 1
    mx = np.full(P.shape, np.nan)
    for i in range(21, T): mx[i] = np.nanmax(np.where(E[i], r[i - 20:i + 1], np.nan), axis=0)
    q90 = np.nanpercentile(np.where(np.isnan(mx), np.nan, mx), 90, axis=1)
    lottery = mx > q90[:, None]
    crash = np.zeros(T, bool)
    for i in range(272, T):
        s = m6[i - 20]; ok = ~np.isnan(s) & ~np.isnan(P[i]) & ~np.isnan(P[i - 20])
        if ok.sum() < 20: continue
        q = np.nanpercentile(s[ok], [20, 80]); ret = P[i] / P[i - 20] - 1
        if np.nanmean(ret[ok & (s >= q[1])]) - np.nanmean(ret[ok & (s <= q[0])]) < -0.10: crash[i:i + 6] = True
    crash = crash[:T]
    base_mask = E & ~lottery & ~crash[:, None]
    return {"지금 규칙": {"kind": "mom6", "lock": lock, "SIG": sigD, "mask": base_mask},
            "6개월 추세만 (덧붙인 규칙 없이)": {"kind": "mom6", "lock": lock, "SIG": rk, "mask": E}}

def main():
    u = json.load(open("universe.json"))
    today = list(u["KR"])
    L = listed(); D = delisted()
    codes = sorted(set(L) | set(D) | set(today))
    print("listed", len(L), "delisted", len(D), "total", len(codes), flush=True)
    with cf.ThreadPoolExecutor(8) as ex: H = list(ex.map(hist_kr, codes))
    keep = [k for k, h in enumerate(H) if len(h[0]) > 60]
    codes = [codes[k] for k in keep]; H = [H[k] for k in keep]
    kc, _ = hist_kr("069500"); kd = sorted(kc)
    P = matrix([h[0] for h in H], kd); K = np.array([kc[d] for d in kd])
    T, n = P.shape
    V = np.zeros(P.shape); alive = np.zeros(P.shape, bool); first = np.zeros(n, int)
    for j, (c, v) in enumerate(H):
        ds = sorted(c); a, b = ds[0], ds[-1]
        for i, d in enumerate(kd):
            if a <= d <= b: alive[i, j] = True; V[i, j] = v.get(d, 0)
    trad = alive & (V > 0)
    tv = np.where(alive, np.nan_to_num(P) * V, 0); cs = np.cumsum(tv, axis=0)
    avg60 = np.zeros(P.shape); avg60[60:] = (cs[60:] - cs[:-60]) / 60
    age = np.cumsum(alive, axis=0)
    pit = np.zeros(P.shape, bool)
    for i in range(T):
        ok = alive[i] & (age[i] >= 253)
        if ok.sum() == 0: continue
        th = np.sort(avg60[i][ok])[::-1][min(249, ok.sum() - 1)]
        pit[i] = ok & (avg60[i] >= th)
    surv = alive & np.isin(np.array(codes), today)[None, :] & (age >= 253)
    sec = list(codes)   # no sector cap in either universe
    delisted_set = set(D)
    res = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "windowYears": 3,
           "counts": {"listedToday": len(L), "delistedSince2018": len(D), "withPrices": n,
                      "everInPitUniverse": int(pit.any(0).sum()), "delistedEverInPit": int(sum(1 for j in np.where(pit.any(0))[0] if codes[j] in delisted_set))}}
    out = {}
    for uname, E in (("오늘 대형주 200개를 과거에도 사용 (이전 방식)", surv), ("그날 실제 거래 상위 250개 (상장폐지 포함)", pit)):
        R = build(P, V, K, E, 10)
        for v in R.values(): v["trad"] = trad; v["alive"] = alive
        out[uname] = {}
        for lab, st, dp in (("7만 원 + 매달 10만 원", 70000, 100000), ("300만 원", 3000000, 0), ("1000만 원", 10000000, 0)):
            print(uname, lab, flush=True)
            out[uname][lab], res["span"] = evaluate(P, kd, sec, K, "mom6", st, dp, {}, R)
            res["KR"] = out
            json.dump(res, open("signals9.json", "w"), ensure_ascii=False, indent=1)
    json.dump(res, open("signals9.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
