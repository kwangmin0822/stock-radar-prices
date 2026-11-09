"""Does the radar's score actually predict returns? Uses this repo's own git history as the archive:
every daily commit of universe.json (fundamentals, price) + stats.json (momentum, volatility) is a snapshot.
For each snapshot date, rebuild a score close to the page's (value / quality / 6-month trend percentiles,
50:50 market and same-sector ranks), split stocks into 5 groups, and measure each group's return
1 month and 3 months later. Results go to score_check.json; the monthly review reads it."""
import json, subprocess, datetime as dt, statistics as st

KST = dt.timezone(dt.timedelta(hours=9))

def git(*a): return subprocess.run(["git", *a], capture_output=True, text=True).stdout

def snapshots():
    """one (date, universe, stats) per day, from git history"""
    out = {}
    for line in git("log", "--format=%H %cI", "--", "universe.json").splitlines():
        sha, when = line.split()
        d = when[:10]
        if d in out: continue
        try:
            u = json.loads(git("show", f"{sha}:universe.json"))
            s_sha = git("rev-list", "-1", f"--before={when}", "HEAD", "--", "stats.json").strip()
            s = json.loads(git("show", f"{s_sha}:stats.json")) if s_sha else {}
        except Exception:
            continue
        out[d] = (u, s)
    return dict(sorted(out.items()))

def pct(vals):
    ok = sorted(v for v in vals.values() if v is not None)
    if len(ok) < 2: return {k: 50.0 for k, v in vals.items() if v is not None}
    return {k: 100.0 * sum(1 for x in ok if x < v) / (len(ok) - 1) for k, v in vals.items() if v is not None}

def scores(u, s):
    res = {}
    for mkt in ("KR", "US"):
        rows = u.get(mkt) or {}
        pre = "KR-" if mkt == "KR" else "US-"
        feats = {}
        for t, x in rows.items():
            k = pre + t
            pe, fpe, pb = x.get("pe"), x.get("forwardPE"), x.get("pb")
            roe = x.get("roe")
            if roe is not None and roe < 0: continue           # loss makers are excluded on the page
            feats[k] = {"ey": 100 / pe if pe and pe > 0 else None, "fey": 100 / fpe if fpe and fpe > 0 else None,
                        "bp": 1 / pb if pb and pb > 0 else None, "fcf": x.get("fcfYield"),
                        "roe": min(roe, 40) if roe is not None else None, "opm": x.get("operatingMargin"),
                        "lev": -x["debtToEquity"] if x.get("debtToEquity") is not None else None,
                        "lv": -s.get("vol", {}).get(k) if s.get("vol", {}).get(k) else None,
                        "m": (s.get("hi52", {}).get(k) if mkt == "KR" else s.get("m6s", {}).get(k)) or s.get("p26", {}).get(k, s.get("p52", {}).get(k)), "sec": x.get("sector") or "기타", "price": x.get("price")}
        groups = {"value": ["ey", "fey", "bp", "fcf"], "quality": ["roe", "opm", "lev", "lv"], "mom": ["m"]}
        R = {}
        for f, keys in groups.items():
            for key in keys:
                m = pct({k: v[key] for k, v in feats.items()})
                if f != "mom":
                    secs = {}
                    for k, v in feats.items(): secs.setdefault(v["sec"], []).append(k)
                    for ks in secs.values():
                        if len(ks) < 5: continue
                        r = pct({k: feats[k][key] for k in ks})
                        for k in ks:
                            if k in m and k in r: m[k] = (m[k] + r[k]) / 2
                R[key] = m
        for k in feats:
            sub = []
            for f, keys in groups.items():
                xs = [R[key][k] for key in keys if k in R[key]]
                if xs: sub.append(sum(xs) / len(xs))
            if sub: res[k] = {"score": sum(sub) / len(sub), "price": feats[k]["price"]}
    return res

def main():
    snaps = snapshots()
    dates = list(snaps)
    S = {d: scores(*snaps[d]) for d in dates}
    out = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "snapshots": len(dates),
           "from": dates[0] if dates else None, "to": dates[-1] if dates else None, "horizons": {}}
    for label, days in (("1개월", 30), ("3개월", 91)):
        buckets = {i: [] for i in range(5)}
        n_dates = 0
        for d in dates:
            target = (dt.date.fromisoformat(d) + dt.timedelta(days=days)).isoformat()
            later = next((x for x in dates if x >= target), None)
            if not later: continue
            now, fut = S[d], S[later]
            ks = [k for k in now if k in fut and now[k]["price"] and fut[k]["price"]]
            if len(ks) < 50: continue
            ks.sort(key=lambda k: now[k]["score"])
            q = len(ks) / 5
            for i, k in enumerate(ks):
                buckets[min(4, int(i // q))].append((fut[k]["price"] / now[k]["price"] - 1) * 100)
            n_dates += 1
        if n_dates:
            out["horizons"][label] = {"dates": n_dates, "groups": {f"{'하위' if i == 0 else '상위' if i == 4 else str(i + 1) + '구간'}": round(st.mean(v), 2) for i, v in buckets.items() if v},
                                      "spread": round(st.mean(buckets[4]) - st.mean(buckets[0]), 2) if buckets[4] and buckets[0] else None}
    out["note"] = "점수 하위 20% → 상위 20% 그룹별 이후 평균 수익률(%). 상위가 꾸준히 높아야 점수가 쓸모 있다는 뜻. 뉴스 점수는 포함 안 됨. 기록이 쌓일수록 정확해짐."
    json.dump(out, open("score_check.json", "w"), ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
