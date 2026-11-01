"""One-off: can GitHub Actions reach China's NBS yearbook tables? Not merged."""
import re, urllib.request

H = {"User-Agent": "Mozilla/5.0"}

def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=H), timeout=60) as r:
            b = r.read(); print("OK", r.status, len(b), url); return b
    except Exception as e:
        print("FAIL", url, e); return None

idx = get("https://www.stats.gov.cn/sj/ndsj/")
if idx:
    t = idx.decode("utf-8", "ignore")
    links = sorted(set(re.findall(r'href="([^"]*ndsj/\d{4}/[^"]*)"', t)))
    print("yearbook links:", links[:40])
for y in (2024, 2023, 2015, 2005):
    for path in (f"https://www.stats.gov.cn/sj/ndsj/{y}/indexch.htm",
                 f"https://www.stats.gov.cn/sj/ndsj/{y}/left.htm"):
        b = get(path)
        if b:
            t = b.decode("utf-8", "ignore")
            rows = re.findall(r'<a[^>]*href="([^"]+)"[^>]*>([^<]*(?:农作物|粮食|小麦|玉米|稻谷|大豆)[^<]*)</a>', t)
            print(y, path.rsplit('/',1)[-1], len(t), rows[:25])
# Latest grain announcement listing
b = get("https://www.stats.gov.cn/sj/zxfb/")
if b:
    t = b.decode("utf-8", "ignore")
    print(re.findall(r'href="([^"]+)"[^>]*>([^<]*粮食[^<]*)<', t)[:10])
