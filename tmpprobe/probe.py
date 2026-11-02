import json, time, urllib.request, urllib.error
codes = "140490,440139,440140,440131,440121,440122,230660,121490,140420,440200,230800,382600"
for period in ("2024",):
    for rep, part, flow in (("392", "360,458", "M"),):
        time.sleep(6)
        url = f"https://comtradeapi.un.org/public/v1/preview/C/A/HS?reporterCode={rep}&period={period}&partnerCode={part}&cmdCode={codes}&flowCode={flow}"
        try:
            b = json.loads(urllib.request.urlopen(url, timeout=90).read())
            rows = sorted(b.get("data", []), key=lambda x: -(x.get("netWgt") or 0))
            for x in rows:
                w = x.get("netWgt") or 0; v = x.get("primaryValue") or 0; q = x.get("qty") or 0
                print("ROW", rep, x["partnerCode"], x["cmdCode"], round(w/1e6), "kt", round(q/1e6), x.get("qtyUnitAbbr"), round(v/max(w,1)*1000, 1), "$/t")
        except urllib.error.HTTPError as e:
            print("ERR", e.code, e.read()[:200])
# Exporter side to Japan, same codes
time.sleep(6)
url = f"https://comtradeapi.un.org/public/v1/preview/C/A/HS?reporterCode=360,458&period=2024&partnerCode=392&cmdCode={codes}&flowCode=X"
b = json.loads(urllib.request.urlopen(url, timeout=90).read())
for x in sorted(b.get("data", []), key=lambda x: -(x.get("netWgt") or 0)):
    w = x.get("netWgt") or 0; v = x.get("primaryValue") or 0
    print("EXP", x["reporterCode"], x["cmdCode"], round(w/1e6), "kt", round(v/max(w,1)*1000, 1), "$/t", x.get("isNetWgtEstimated"))
