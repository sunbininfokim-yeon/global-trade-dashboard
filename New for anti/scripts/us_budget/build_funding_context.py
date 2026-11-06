"""Validate and publish reviewed funding context, independently of money refreshes.

No network, automatic political inference, or changes to monetary datasets.
"""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
PROFILE = Path(__file__).with_name('funding_context_review.json')
OUTPUT = ROOT / 'public/data/us_budget/funding_context_v1.json'
HOSTS = {'www.govinfo.gov','www.whitehouse.gov','www.cbo.gov','www.crfb.org','www.steptoe.com',
         'rollcall.com','appropriations.house.gov','democrats-appropriations.house.gov'}


def check(condition):
    if not condition:
        raise ValueError("Invalid reviewed funding context")


def validate(d):
    check(d['schema_version']==1 and isinstance(d['fiscal_year'],int))
    reviewed=date.fromisoformat(d['reviewed_on'])
    check(reviewed<=date.fromisoformat(d['review_valid_until']))
    sources={s['id']:s for s in d['sources']}
    check(len(sources)==len(d['sources']))
    for s in sources.values():
        u=urlparse(s['url'])
        check(u.scheme=='https' and u.hostname in HOSTS and not u.username)
        check(date.fromisoformat(s['published_on'])<=reviewed)
    f=d['funding']
    check(f['kind']=='continuing_resolution')
    check(f['bill_id'].split('-')[0]==f['public_law_number'].split('-')[0])
    check(date.fromisoformat(f['starts_on'])<=reviewed<=date.fromisoformat(f['general_deadline']))
    check(date.fromisoformat(f['law_verified_on'])<=reviewed)
    check(len(f['law_sha256'])==64 and int(f['law_sha256'],16)>=0)
    p=d['procedure']
    check(date.fromisoformat(p['as_of'])<=reviewed)
    check(all(type(p[k]) is int and 0<=p[k]<=p['total_bills'] for k in ['house_passed','senate_passed']))
    for record in [f,p]+d['issues']:
        check(record['sources'] and set(record['sources'])<=sources.keys())
    for issue in d['issues']:
        check(issue['state'] in {'unresolved_at_source','addressed_in_cr'})
        check(date.fromisoformat(issue['as_of'])<=reviewed)
        check(all(date.fromisoformat(sources[k]['published_on'])<=date.fromisoformat(issue['as_of']) for k in issue['sources']))
    return d


def build(profile=PROFILE, law_path=None):
    d=validate(json.loads(Path(profile).read_text()))
    if law_path:
        from funding import verify_measure
        law=json.loads(PROFILE.with_name('funding_review.json').read_text())['measures']
        record=next(m for m in law if m['public_law_number']==d['funding']['public_law_number'])
        check(record['bill_id']==d['funding']['bill_id'])
        check(record['general_deadline']==d['funding']['general_deadline'])
        check(record['fiscal_year']==d['fiscal_year'])
        raw=Path(law_path).read_bytes()
        check(hashlib.sha256(raw).hexdigest()==d['funding']['law_sha256'])
        check(verify_measure(record,raw,d['funding']['law_verified_on'])['verification_status']=='verified')
    return (json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',action='store_true')
    p.add_argument('--law-file',type=Path)
    a=p.parse_args();raw=build(law_path=a.law_file)
    if a.check:check(OUTPUT.read_bytes()==raw)
    else:
        OUTPUT.parent.mkdir(parents=True,exist_ok=True)
        OUTPUT.write_bytes(raw)
    print('Reviewed funding context validated')
