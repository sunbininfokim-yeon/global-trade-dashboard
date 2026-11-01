"""One-off: what does an NBS yearbook contents page look like from Actions? Not merged."""
import re, urllib.request

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60) as r:
        return r.read()

for y in (2024, 2005):
    b = get(f"https://www.stats.gov.cn/sj/ndsj/{y}/left.htm")
    print(y, "head bytes:", b[:300])
    for enc in ("utf-8", "gb18030"):
        try:
            t = b.decode(enc); print("decoded as", enc); break
        except UnicodeDecodeError:
            continue
    print("hrefs:", re.findall(r'href\s*=\s*["\']?([^"\' >]+)', t, re.I)[:15])
    for word in ("农业", "农作物", "粮食"):
        i = t.find(word)
        print(word, i, repr(t[max(0, i - 400):i + 600]) if i >= 0 else "")
