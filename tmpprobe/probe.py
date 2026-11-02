import os, urllib.request, urllib.parse
key = urllib.parse.unquote(os.environ.get("K", ""))
print("key set:", bool(key), len(key))
for op, extra in (("nitemtrade/getNitemtradeList", {"cntyCd": "ID"}), ("nitemtrade/getNitemtradeList", {"cntyCd": "MY"})):
    for hs in ("140490", "1404909000", "1404901000", "14049090"):
        q = dict(serviceKey=key, strtYymm="202501", endYymm="202503", hsSgn=hs, **extra)
        url = "https://apis.data.go.kr/1220000/" + op + "?" + urllib.parse.urlencode(q)
        try:
            body = urllib.request.urlopen(url, timeout=60).read().decode("utf-8", "replace")
        except Exception as e:
            body = f"ERR {e}"
        print("==", op, extra, hs); print(body[:1500])
