import json, time, urllib.request, urllib.error
base = "https://comtradeapi.un.org/public/v1/preview/C/{f}/HS?reporterCode={r}&period={p}&partnerCode=360,458&cmdCode=140490&flowCode=M"
for f, p, r in (("A", "2024", "410"), ("A", "2024", "392"), ("M", "202506", "410"), ("A", "2024", "410,392")):
    time.sleep(8)
    url = base.format(f=f, p=p, r=r)
    try:
        b = json.loads(urllib.request.urlopen(url, timeout=60).read())
        print("OK", f, p, r, "count", b.get("count"))
        for x in b.get("data", [])[:20]:
            print("ROW", x["reporterCode"], x["partnerCode"], x["period"], x.get("netWgt"), x.get("qty"), x.get("qtyUnitAbbr"), x.get("primaryValue"), x.get("customsCode"), x.get("motCode"), x.get("partner2Code"))
    except urllib.error.HTTPError as e:
        print("ERR", f, p, r, e.code, e.read()[:300])
