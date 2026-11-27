#!/usr/bin/env python3
"""One-off: list FISIS statistic tables for insurers and find the ones that carry
보험계약마진(CSM). Prints table numbers and account codes only (no key)."""
import json
import os
import sys
import urllib.request

KEY = os.environ.get("FISIS_API_KEY", "").strip()
URL = "https://fisis.fss.or.kr/openapi/{api}.json?lang=kr&auth={key}&{q}"


def call(api, q):
    with urllib.request.urlopen(urllib.request.Request(URL.format(api=api, key=KEY, q=q), headers={"User-Agent": "Mozilla/5.0"}), timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))["result"]


for part in ("H", "I"):
    comps = call("companySearch", f"partDiv={part}").get("list") or []
    print(f"== partDiv {part}: {len(comps)} companies; e.g.", [(c.get("finance_cd"), c.get("finance_nm")) for c in comps[:6]])
    lists = call("statisticsListSearch", f"lrgDiv={part}").get("list") or []
    print(f"   {len(lists)} tables")
    print("   ALL:", " | ".join(f"{t.get('list_no')} {t.get('list_nm')}" for t in lists))
    for t in lists:
        name = t.get("list_nm") or ""
        if any(k in name for k in ("보험계약", "CSM", "마진", "요약", "주요", "IFRS17", "부채")) and "이전" not in name and comps:
            cd = next((c["finance_cd"] for c in comps if "삼성" in (c.get("finance_nm") or "") or "DB" in (c.get("finance_nm") or "")), comps[0]["finance_cd"])
            q = f"financeCd={cd}&listNo={t.get('list_no')}&term=Q&startBaseMm=202506&endBaseMm=202612"
            try:
                rows = call("statisticsInfoSearch", q).get("list") or []
            except Exception as exc:  # noqa: BLE001
                print("   ", t.get("list_no"), "ERR", exc); continue
            accts = {}
            for r in rows:
                accts.setdefault(r.get("account_cd"), (r.get("account_nm"), r.get("a"), r.get("base_month")))
            print("   ACCT", t.get("list_no"), name, list(accts.items())[:25])
sys.exit(0)
