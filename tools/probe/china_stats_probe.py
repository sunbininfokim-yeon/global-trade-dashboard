"""One-off: can GitHub Actions reach China's NBS province data? Not merged."""
import json, urllib.parse, urllib.request

H = {"User-Agent": "Mozilla/5.0", "Referer": "https://data.stats.gov.cn/easyquery.htm?cn=E0103"}

def get(url, data=None):
    req = urllib.request.Request(url, data=data, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
            print("OK", r.status, len(body), url[:120]); return body
    except Exception as e:
        print("FAIL", url[:120], e); return None

for u in ["https://data.stats.gov.cn/", "https://www.stats.gov.cn/sj/zxfb/",
          "https://www.stats.gov.cn/sj/ndsj/"]:
    get(u)

def tree(node):
    b = get("https://data.stats.gov.cn/easyquery.htm",
            urllib.parse.urlencode({"id": node, "dbcode": "fsnd", "wdcode": "zb", "m": "getTree"}).encode())
    return json.loads(b) if b else []

top = tree("zb")
for t in top:
    print(t["id"], t["name"])
# Agriculture subtree: print two levels.
for t in top:
    if "农业" in t["name"]:
        for c in tree(t["id"]):
            print(" ", c["id"], c["name"])
            for g in tree(c["id"]):
                print("   ", g["id"], g["name"])

# One query: first leaf under the crops branch, all provinces, last 10 years.
def query(code):
    wds = json.dumps([])
    dfwds = json.dumps([{"wdcode": "zb", "valuecode": code}, {"wdcode": "sj", "valuecode": "LAST10"}])
    u = ("https://data.stats.gov.cn/easyquery.htm?m=QueryData&dbcode=fsnd&rowcode=reg&colcode=sj&wds="
         + urllib.parse.quote(wds) + "&dfwds=" + urllib.parse.quote(dfwds))
    b = get(u)
    if b:
        d = json.loads(b)["returndata"]
        print("nodes", len(d["datanodes"]), d["datanodes"][:3])
        print([w for w in d["wdnodes"] if w["wdcode"] == "zb"][0]["nodes"][:6])
import sys
for code in sys.argv[1:]:
    query(code)
