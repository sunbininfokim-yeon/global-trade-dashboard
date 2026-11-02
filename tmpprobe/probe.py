import json, urllib.request
base = "https://comtradeapi.un.org/public/v1/preview/C/{f}/HS?reporterCode=410,392&period={p}&partnerCode=360,458&cmdCode=140490&flowCode=M&partner2Code=0&customsCode=C00&motCode=0"
for f, p in (("A", "2022,2023,2024,2025"), ("M", "202501,202502,202503,202504,202505,202506")):
    try:
        b = json.loads(urllib.request.urlopen(base.format(f=f, p=p), timeout=60).read())
        print(f, p, "count", b.get("count"), b.get("error"))
        for r in b.get("data", [])[:40]:
            print(r["reporterCode"], r["partnerCode"], r["period"], r.get("netWgt"), r.get("qty"), r.get("qtyUnitAbbr"), r.get("primaryValue"))
    except Exception as e:
        print(f, "ERR", e)
