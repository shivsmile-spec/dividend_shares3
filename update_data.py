import json, re, requests, time
from datetime import datetime, timedelta, date

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
s=requests.Session(); s.headers.update({"User-Agent":UA,"Accept":"application/json,text/plain,*/*","Accept-Language":"en-US,en;q=0.9","Referer":"https://www.nseindia.com/"})
try: s.get("https://www.nseindia.com/",timeout=20)
except: pass
today=date.today(); end=today+timedelta(days=90)
url=f"https://www.nseindia.com/api/corporate-actions?index=equities&from_date={today.strftime('%d-%m-%Y')}&to_date={end.strftime('%d-%m-%Y')}"
r=s.get(url,timeout=30); r.raise_for_status(); raw=r.json()
items=raw if isinstance(raw,list) else raw.get("data",raw.get("records",[]))
events=[]
for x in items:
    text=" ".join(str(x.get(k,"")) for k in ("purpose","subject","details","description"))
    if "dividend" not in text.lower(): continue
    sym=x.get("symbol") or x.get("Symbol") or x.get("SYMBOL")
    ex=x.get("exDate") or x.get("ex_date") or x.get("exdate")
    rec=x.get("recordDate") or x.get("record_date") or x.get("recorddate")
    if not sym or not ex: continue
    def parse(sv):
        if not sv:return None
        for f in ("%d-%b-%Y","%d-%B-%Y","%d-%m-%Y","%d/%m/%Y"):
            try:return datetime.strptime(str(sv),f).date().isoformat()
            except:pass
        return None
    exi=parse(ex)
    if not exi or exi<today.isoformat(): continue
    m=re.search(r"(?:Rs\.?|₹|INR)\s*([\d,]+(?:\.\d+)?)",text,re.I) or re.search(r"dividend[^\d]*([\d,]+(?:\.\d+)?)",text,re.I)
    amt=float(m.group(1).replace(",","")) if m else None
    if amt is None: continue
    events.append({"symbol":sym,"company":x.get("companyName") or x.get("company_name") or x.get("company") or "","dividend":amt,"exDate":exi,"recordDate":parse(rec)})
# De-duplicate
seen=set(); clean=[]
for e in sorted(events,key=lambda z:(z["exDate"],z["symbol"])):
    k=(e["symbol"],e["exDate"])
    if k not in seen: seen.add(k); clean.append(e)
# Add price and RSI from Yahoo chart endpoint
def yahoo(sym):
    try:
        u=f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}.NS?range=6mo&interval=1d"
        q=requests.get(u,headers={"User-Agent":UA},timeout=15).json()["chart"]["result"][0]
        closes=[v for v in q["indicators"]["quote"][0]["close"] if v is not None]
        price=q["meta"].get("regularMarketPrice",closes[-1])
        n=14
        if len(closes)<n+1:return price,None
        gains=[];loss=[]
        for i in range(1,len(closes)): 
            d=closes[i]-closes[i-1];gains.append(max(d,0));loss.append(max(-d,0))
        ag=sum(gains[:n])/n;al=sum(loss[:n])/n
        for i in range(n,len(gains)): ag=(ag*(n-1)+gains[i])/n;al=(al*(n-1)+loss[i])/n
        rr=100 if al==0 else 100-100/(1+ag/al)
        return price,rr
    except:return None,None
for e in clean:
    p,rr=yahoo(e["symbol"]);e["price"]=p;e["rsi"]=rr;e["dividendYield"]=(e["dividend"]/p*100) if p else 0
    time.sleep(.1)
out={"updated":datetime.now().strftime("%d %b %Y, %I:%M %p IST"),"events":clean}
with open("data/dividends.json","w",encoding="utf-8") as f:json.dump(out,f,ensure_ascii=False,indent=2)
print("Saved",len(clean),"events")
