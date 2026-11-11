"""Round 11: find a Korean rule that works on point-in-time candidates (no survivorship from using today's list).
Universe each day = stocks whose market cap that day (close x today's shares) was >= 1 trillion / 300 billion won.
Rules (page mechanics: daily check, whole shares, next-day fills, costs and tax, -12% stop, halted days untradable):
  momentum (6-1) as before - baseline that failed
  momentum without the top 10% (ChatGPT K2: avoid the most extreme winners)
  52-week-high closeness
  1-month reversal: buy the biggest losers of the last 21 days (Korean stocks tend to reverse)
  low volatility: lowest 60-day volatility
  mega caps: the largest companies by market cap that day (top 10 / top 20)
  mega caps + 6-1 trend among the 30 largest
Compared with KODEX 200 bought with the same deposits."""
import json, datetime as dt
import concurrent.futures as cf
import numpy as np
import signals4
from signals import matrix, KST
from signals4 import evaluate
from signals6 import rankpct
from signals8 import hist_kr
from signals10 import listed_caps

def main():
    signals4.STEP = 63
    SH = listed_caps(); codes = sorted(SH)
    with cf.ThreadPoolExecutor(8) as ex: H = list(ex.map(hist_kr, codes))
    keep = [k for k, h in enumerate(H) if len(h[0]) > 60]; codes = [codes[k] for k in keep]; H = [H[k] for k in keep]
    kc, _ = hist_kr("069500"); kd = sorted(kc); K = np.array([kc[d] for d in kd])
    P = matrix([h[0] for h in H], kd); T, n = P.shape
    V = np.zeros(P.shape); alive = np.zeros(P.shape, bool)
    for j, (c, v) in enumerate(H):
        ds = sorted(c)
        for i, d in enumerate(kd):
            if ds[0] <= d <= ds[-1]: alive[i, j] = True; V[i, j] = v.get(d, 0)
    trad = alive & (V > 0); age = np.cumsum(alive, axis=0)
    cap = np.nan_to_num(P) * np.array([SH[c] for c in codes])[None, :]
    base = alive & (age >= 253)
    E1 = base & (cap >= 1e12); E3 = base & (cap >= 3e11)
    m6 = np.full(P.shape, np.nan); m6[126:] = P[105:-21] / P[:-126] - 1
    r21 = np.full(P.shape, np.nan); r21[21:] = P[21:] / P[:-21] - 1
    hi = np.full(P.shape, np.nan)
    for i in range(251, T): hi[i] = P[i] / np.nanmax(P[i - 251:i + 1], axis=0)
    lr = np.diff(np.log(P), axis=0, prepend=np.nan)
    vol = np.full(P.shape, np.nan)
    for i in range(60, T): vol[i] = np.nanstd(lr[i - 59:i + 1], axis=0)
    caprank = np.full(P.shape, np.nan)
    for i in range(T):
        ok = base[i] & (cap[i] > 0)
        if ok.any(): order = np.argsort(-np.where(ok, cap[i], -1)); caprank[i, order[:ok.sum()]] = np.arange(ok.sum())
    def R(E, sig, topn=10, lock=10, daily=True):
        return {"kind": "mom6", "SIG": np.where(E, sig, np.nan), "mask": E, "topn": topn, "lock": lock, "trad": trad, "alive": alive, "daily": daily}
    rk1 = rankpct(np.where(E1, m6, np.nan)); rk3 = rankpct(np.where(E3, m6, np.nan))
    top30 = base & (caprank < 30); top10 = base & (caprank < 10); top20 = base & (caprank < 20)
    rules = {
        "추세 (지금 방식) · 1조+": R(E1, m6),
        "추세, 상위 10% 빼고 · 1조+": R(E1, np.where(rk1 <= 0.9, m6, np.nan)),
        "추세, 상위 10% 빼고 · 3천억+": R(E3, np.where(rk3 <= 0.9, m6, np.nan)),
        "52주 최고가 근접 · 1조+": R(E1, hi),
        "추세 · 1조+ · 매달 교체": R(E1, m6, daily=False),
        "1달 낙폭 큰 종목 (반전) · 1조+ · 매달 교체": R(E1, -r21, daily=False),
        "1달 낙폭 큰 종목 (반전) · 3천억+ · 매달 교체": R(E3, -r21, daily=False),
        "덜 출렁이는 종목 · 1조+ · 매달 교체": R(E1, -vol, daily=False),
        "초대형주 상위 10개 · 매달 교체": R(top10, -caprank, 10, daily=False),
        "초대형주 상위 20개 · 매달 교체": R(top20, -caprank, 20, daily=False),
        "초대형 30개 중 추세 상위 10": R(top30, m6),
        "초대형 30개 중 추세 상위 10 · 매달 교체": R(top30, m6, daily=False),
    }
    res = {"updatedAt": dt.datetime.now(KST).isoformat(timespec="seconds"), "stocks": n,
           "avgUniverse": {"1조+": int(E1.sum(1)[260:].mean()), "3천억+": int(E3.sum(1)[260:].mean())}, "KR": {}}
    for lab, st, dp in (("7만 원 + 매달 10만 원", 70000, 100000), ("300만 원", 3000000, 0), ("1000만 원", 10000000, 0)):
        print(lab, flush=True)
        res["KR"][lab], res["span"] = evaluate(P, kd, list(codes), K, "mom6", st, dp, {}, rules)
        json.dump(res, open("signals11.json", "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
