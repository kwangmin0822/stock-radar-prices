import json,sys
sys.path.insert(0,"scripts")
import fetch_stats as f
out={}
for c in ["005930","006800"]:
    n=f.naver(c); y=f.yahoo(c+".KS")
    out[c]={"naver_vol":f.vol(n),"yahoo_vol":f.vol(y),"naver_n":len(n),"naver_head":n[:5],"naver_tail":n[-15:],
      "naver_bigmoves":[(i,n[i-1],n[i]) for i in range(1,len(n)) if n[i-1] and abs(n[i]/n[i-1]-1)>0.12][:10]}
json.dump(out,open("debug.json","w"),indent=1)
