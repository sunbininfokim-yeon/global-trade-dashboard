"""One-off: can GitHub Actions read NBS yearbook crop tables by province? Not merged."""
import re, urllib.request

H = {"User-Agent": "Mozilla/5.0"}

def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=60) as r:
            b = r.read(); print("OK", r.status, len(b), url); return b
    except Exception as e:
        print("FAIL", url, e); return None

def text(b):
    for enc in ("utf-8", "gb18030"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode("gb18030", "ignore")

for y in (2024, 2015, 2005):
    base = f"https://www.stats.gov.cn/sj/ndsj/{y}/"
    b = get(base + "left.htm")
    if not b:
        continue
    t = text(b)
    rows = re.findall(r'href="([^"]+)"[^>]*>\s*([^<]*(?:农作物|粮食|小麦|玉米|稻谷|大豆|播种面积)[^<]*)<', t)
    print(y, rows[:30])
    for href, name in rows:
        if "各地区" in name and ("产量" in name or "播种" in name):
            u = href if href.startswith("http") else base + href.lstrip("./")
            tb = get(u)
            if tb:
                tt = re.sub(r"<[^>]+>", " ", text(tb))
                tt = re.sub(r"\s+", " ", tt)
                print("   ", name, "|", tt[:900])
            break
