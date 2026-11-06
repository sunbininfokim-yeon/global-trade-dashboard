"""Temporary: dump ECOS 901Y009 (all CPI items, monthly) and 901Y010 to JSON for offline work."""
import json, os, urllib.request
key = os.environ["ECOS_API_KEY"]
out = {}
for stat in ("901Y009", "901Y010"):
    rows, start = [], 1
    while True:
        url = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/{start}/{start+9999}/{stat}/M/202212/202610"
        with urllib.request.urlopen(url, timeout=120) as r:
            d = json.loads(r.read())
        block = d.get("StatisticSearch") or {}
        got = block.get("row") or []
        rows += got
        total = block.get("list_total_count", 0)
        print(stat, start, len(got), total, flush=True)
        if not got or len(rows) >= total:
            break
        start += 10000
    items, start = [], 1
    while True:
        url = f"https://ecos.bok.or.kr/api/StatisticItemList/{key}/json/kr/{start}/{start+999}/{stat}"
        with urllib.request.urlopen(url, timeout=120) as r:
            blk = json.loads(r.read()).get("StatisticItemList") or {}
        items += blk.get("row") or []
        if len(items) >= blk.get("list_total_count", 0) or not blk.get("row"):
            break
        start += 1000
    annual = []
    for y in range(2019, 2026):
        url = f"https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/2000/{stat}/A/{y}/{y}"
        with urllib.request.urlopen(url, timeout=120) as r:
            annual += (json.loads(r.read()).get("StatisticSearch") or {}).get("row") or []
    print(stat, "annual", len(annual), flush=True)
    out[stat] = {"rows": rows, "items": items, "annual": annual}
json.dump(out, open("ecos_cpi_dump.json", "w"), ensure_ascii=False)
