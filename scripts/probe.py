import json, urllib.request
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36","Accept":"application/json,text/plain,*/*","Referer":"https://m.stock.naver.com/"}
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=15) as r: return r.read().decode("utf-8","replace")[:20000]
    except Exception as e: return "ERR "+str(e)
urls=["https://m.stock.naver.com/api/stock/024110/basic","https://m.stock.naver.com/api/stocks/industry/024110","https://m.stock.naver.com/api/stock/024110/integration","https://api.stock.naver.com/stock/EQNR/finance/annual".replace("EQNR","TSM"),"https://api.stock.naver.com/stock/AAPL.O/finance/annual","https://api.stock.naver.com/stock/AAPL.O/integration","https://m.stock.naver.com/api/stocks/marketValue/KOSPI?page=1&pageSize=3",
"https://m.stock.naver.com/api/stocks/marketValue/KOSDAQ?page=1&pageSize=2",
"https://m.stock.naver.com/api/stock/024110/finance/annual",
"https://m.stock.naver.com/api/stock/024110/integration",
"https://api.stock.naver.com/stock/exchange/NASDAQ/marketValue?page=1&pageSize=2",
"https://api.stock.naver.com/stock/exchange/NYSE/marketValue?page=1&pageSize=2",
"https://api.stock.naver.com/stock/EQNR/finance/annual",
"https://api.stock.naver.com/stock/EQNR/integration"]
json.dump({u:get(u) for u in urls},open("probe.json","w"),ensure_ascii=False,indent=1)
