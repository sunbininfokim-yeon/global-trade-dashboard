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
    for t in lists:
        name = t.get("list_nm") or ""
        if any(k in name for k in ("보험계약마진", "CSM", "주요경영", "경영지표", "보험손익", "지급여력", "손해율", "합산", "보험계약부채")):
            print("   table", t.get("list_no"), name)
            if any(k in name for k in ("보험계약마진", "CSM", "주요경영", "경영지표", "보험계약부채")) and comps:
                q = f"financeCd={comps[0]['finance_cd']}&listNo={t.get('list_no')}&term=Q&startBaseMm=202501&endBaseMm=202612"
                rows = call("statisticsInfoSearch", q).get("list") or []
                accts = {}
                for r in rows:
                    accts.setdefault(r.get("account_cd"), r.get("account_nm"))
                print("      accounts:", list(accts.items())[:40])
sys.exit(0)
