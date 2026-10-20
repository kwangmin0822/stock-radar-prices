import json,urllib.request
UA={"User-Agent":"Mozilla/5.0 Chrome/124","Referer":"https://finance.naver.com/"}
def g(u):
    try:
        return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=10).read())
    except Exception as e: return str(e)
out={"naver_poll":g("https://polling.finance.naver.com/api/realtime/domestic/stock/006800"),
 "naver_basic":g("https://m.stock.naver.com/api/stock/006800/basic"),
 "yahoo":g("https://query1.finance.yahoo.com/v8/finance/chart/006800.KS?interval=1d&range=5d")}
json.dump(out,open("debug.json","w"),ensure_ascii=False,indent=1)
