import json, time, urllib.request, urllib.error
url = "https://comtradeapi.un.org/public/v1/preview/C/A/HS?reporterCode=410&period=2024&partnerCode=360,458&cmdCode=440131,440132,440139,440140,440110,440121,440122,440200,230660,230800,230890,121490,140490,140420&flowCode=M"
try:
    b = json.loads(urllib.request.urlopen(url, timeout=90).read())
    rows = sorted(b.get("data", []), key=lambda x: -(x.get("netWgt") or 0))
    print("OK count", b.get("count"))
    for x in rows[:25]:
        w = x.get("netWgt") or 0; v = x.get("primaryValue") or 0
        print("ROW", x["partnerCode"], x["cmdCode"], round(w/1e3), "t", round(v/max(w,1)*1000, 1), "$/t")
except urllib.error.HTTPError as e:
    print("ERR", e.code, e.read()[:300])
