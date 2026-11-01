"""One-off: which NBS yearbooks carry provincial crop tables, and in what format? Not merged."""
import re, urllib.request

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
        return r.read()

for y in range(2005, 2026):
    base = f"https://www.stats.gov.cn/sj/ndsj/{y}/"
    try:
        t = get(base + "left.htm").decode("gb18030", "ignore")
    except Exception as e:
        print(y, "FAIL", e); continue
    items = re.findall(r"href\s*=\s*['\"]([^'\"]+)['\"][^>]*>\s*([^<]*)<", t)
    hits = [(h, n.strip()) for h, n in items if ("地区" in n) and any(w in n for w in ("农作物", "农产品", "粮食"))]
    print(y, hits)
    if y in (2012, 2024) and hits:
        h = hits[0][0]
        try:
            b = get(base + h)
            print("   fetched", h, len(b), b[:120])
            if h.lower().endswith(("htm", "html")):
                tt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b.decode("gb18030", "ignore")))
                print("   ", tt[:700])
        except Exception as e:
            print("   FAIL", h, e)
