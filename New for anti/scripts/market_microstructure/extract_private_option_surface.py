"""Derive daily IV features from an existing private snapshot; never store raw chains."""
import argparse
import base64
import gzip
import hashlib
import json
import math
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from option_direction_model import write
from research_pr791_evaluation import git_json

GH = "gh"
REPOSITORY = "sunbininfokim-yeon/krx-month-paste"


def api(path):
    return json.loads(subprocess.check_output([GH,"api",f"repos/{REPOSITORY}/"+path]))


def number(v):
    try: v=float(v)
    except (ValueError,TypeError): return None
    return v if math.isfinite(v) else None


def surface_day(rows, spot, expiry):
    latest={};conflicts=set()
    for r in rows:
        if r.get("session")!="regular" or r.get("quality")!="observed" or str(r.get("expiry_or_contract_month"))!=str(expiry): continue
        t=r.get("option_type");k=number(r.get("strike"))
        if t not in ("call","put") or k is None or k<=0: continue
        key=(t,k);prev=latest.get(key)
        if prev and str(prev.get("collected_at") or "")==str(r.get("collected_at") or "") and prev.get("implied_volatility")!=r.get("implied_volatility"):
            conflicts.add(key)
        if prev is None or str(r.get("collected_at") or "")>=str(prev.get("collected_at") or ""):
            latest[key]=r
    if conflicts: return {"status":"unavailable","reason":"same_time_conflicting_IV"}
    quotes={key:r for key,r in latest.items() if number(r.get("implied_volatility")) is not None and 1<=number(r["implied_volatility"])<=150}
    common={k for t,k in quotes if ("call",k) in quotes and ("put",k) in quotes}
    calls=[k for t,k in quotes if t=="call"];puts=[k for t,k in quotes if t=="put"]
    if not common or not calls or not puts: return {"status":"unavailable","reason":"insufficient_IV_quotes"}
    atm=min(common,key=lambda k:abs(k/spot-1));put=min(puts,key=lambda k:abs(k/spot-.95));call=min(calls,key=lambda k:abs(k/spot-1.05))
    if max(abs(atm/spot-1),abs(put/spot-.95),abs(call/spot-1.05))>.015:
        return {"status":"unavailable","reason":"quotes_too_far_from_fixed_moneyness"}
    support=[]
    for t,k in [("call",atm),("put",atm),("put",put),("call",call)]:
        r=quotes[t,k]
        support.append({"option_type":t,"strike":k,"iv_pct":number(r["implied_volatility"]),
                        "contract_code":r.get("contract_code"),"collected_at":r.get("collected_at")})
    ca,pa,pw,cw=[q["iv_pct"] for q in support]
    return {"status":"observed_research","expiry_month":expiry,"index_close":spot,"support":support,
            "features":[(pw-pa)/100,(cw-ca)/100,(pa-ca)/100],"n_valid_IV_quotes":len(quotes)}


def extract_part(part, references):
    blob=api("git/blobs/"+part["sha"]);raw=base64.b64decode(blob["content"])
    content=gzip.decompress(raw);by_day=defaultdict(list)
    for line in content.splitlines():
        if line.strip():
            row=json.loads(line)
            if row.get("session")=="regular": by_day[row["date"]].append(row)
    points={}
    for day,rows in by_day.items():
        if day not in references:
            points[day]={"status":"unavailable","reason":"missing_spot_or_front_month_reference"};continue
        spot,expiry=references[day];points[day]=surface_day(rows,spot,expiry)
    return {"path":part["path"],"git_blob":part["sha"],"sha256":hashlib.sha256(raw).hexdigest(),
            "points":points,"regular_rows":sum(map(len,by_day.values()))}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-ref",default="3a27fa40");parser.add_argument("--public-ref",required=True)
    parser.add_argument("--gh",default=GH);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    globals()["GH"]=args.gh
    commit=api("commits/"+args.private_ref)["sha"]
    tree=api("git/trees/"+commit+"?recursive=1")
    if tree.get("truncated"): raise ValueError("private tree truncated")
    parts=[r for r in tree["tree"] if r["path"].startswith("data/normalized/kospi200_option_oi/") and r["path"].endswith("part.jsonl.gz")]
    index,index_sha=git_json(args.public_ref,"kospi200_index_daily_v1.json")
    deriv,deriv_sha=git_json(args.public_ref,"krx_deriv_flow_v1.json")
    closes={r["date"]:number(r["close"]) for r in index["rows"]}
    references={d:(closes[d],exp) for d,exp in zip(deriv["dates"],deriv["option_oi"]["expiry"])
                if d in closes and closes[d] and closes[d]>0 and exp}
    points={};receipts=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for i,result in enumerate(pool.map(lambda p:extract_part(p,references),parts),1):
            for day,value in result.pop("points").items():
                if day in points: raise ValueError("surface date duplicated across hive partitions")
                points[day]=value
            receipts.append(result)
            if i%12==0: print("processed",i,"of",len(parts),flush=True)
    report={"status":"research_only","private_source":{"repository":REPOSITORY,"commit":commit},
        "public_ref":args.public_ref,"public_sha256":{"index":index_sha,"deriv":deriv_sha},
        "fields":["put95_minus_atm_put_iv","call105_minus_atm_call_iv","atm_put_minus_call_iv"],
        "receipts":receipts,"points":dict(sorted(points.items())),
        "limitations":["No new KRX queries; existing private normalized rows read in memory only",
                       "Fixed spot moneyness, not delta matching or foreign positioning",
                       "Reported IV without bid/ask validation; exact expiration dates unavailable",
                       "Public front-month tag used as expiry reference; regular-session observed quotes only"]}
    write(args.output,report)
    valid=[d for d,p in points.items() if p["status"]=="observed_research"]
    print("surface dates",len(valid),"last",max(valid) if valid else None)


if __name__=="__main__":main()
