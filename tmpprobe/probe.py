import json, time, urllib.request, urllib.error
NAMES = {"410": "KOR", "392": "JPN", "156": "CHN", "704": "VNM", "764": "THA", "528": "NLD", "826": "GBR", "0": "WORLD"}
for rep in ("360", "458"):
    for period in ("2023", "2024"):
        time.sleep(8)
        url = f"https://comtradeapi.un.org/public/v1/preview/C/A/HS?reporterCode={rep}&period={period}&cmdCode=140490&flowCode=X"
        try:
            b = json.loads(urllib.request.urlopen(url, timeout=90).read())
            rows = sorted(b.get("data", []), key=lambda x: -(x.get("netWgt") or 0))
            print("OK", rep, period, "count", b.get("count"))
            for x in rows[:10]:
                w = x.get("netWgt") or 0; v = x.get("primaryValue") or 0
                print("ROW", rep, period, NAMES.get(str(x["partnerCode"]), x["partnerCode"]), round(w/1e6), "kt", round(v/max(w,1)*1000, 1), "$/t", x.get("partner2Code"), x.get("motCode"), x.get("customsCode"))
        except urllib.error.HTTPError as e:
            print("ERR", rep, period, e.code, e.read()[:200])
