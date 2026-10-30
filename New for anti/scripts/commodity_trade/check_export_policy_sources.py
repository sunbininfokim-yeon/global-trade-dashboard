"""Monitor allowlisted official policy documents; never auto-certify legal status.

Run separately from monthly statistics. HTML availability/hash changes are
technical signals, not proof a restriction was enacted, renewed or repealed.
"""
from datetime import datetime, timezone
from hashlib import sha256
import argparse
from pathlib import Path
from urllib.parse import urlsplit

from bilateral_provider import read_http
from pipeline_store import atomic_json, read_json, single_writer

ROOT = Path(__file__).resolve().parent
ALLOWED_HOSTS = {'esdm.go.id', 'www.esdm.go.id', 'setkab.go.id', 'www.ekon.go.id', 'ekon.go.id'}


def check_documents(documents, previous=None, *, http=read_http, max_requests=4):
    sources = dict((previous or {}).get('sources', {}))
    now = datetime.now(timezone.utc).isoformat()
    attempted = 0
    for document in documents:
        url = document['url']
        u = urlsplit(url)
        if u.scheme != 'https' or u.hostname not in ALLOWED_HOSTS or u.username or u.password or u.query or u.fragment:
            raise ValueError('policy source not allowlisted')
        if attempted >= max_requests:
            break
        attempted += 1
        old = sources.get(url, {})
        entry = {**old, 'checked_at': now, 'rule_id': document['rule_id'],
                 'current_legal_status_verified': False}
        try:
            body = http(url, headers={'User-Agent': 'CommodityTradePolicyMonitor/1.0', 'Accept': 'text/html'}, timeout=20)
            text = body.decode('utf-8', errors='replace')
            if len(body) < 200 or '<html' not in text.lower() or any(t in text.lower() for t in ('verify you are human', 'just a moment...', 'captcha')):
                raise ValueError('not policy HTML')
            digest = sha256(body).hexdigest()
            # Even a stable response does not refresh the legal-review date.
            changed = old.get('sha256') is not None and old['sha256'] != digest
            entry.update(status='changed' if changed else 'unchanged' if old.get('sha256') else 'baseline',
                         sha256=digest, last_success_at=now, review_required=True)
        except (OSError, ValueError):
            entry.update(status='unavailable', review_required=True)
        sources[url] = entry
    return {'schema': 'export-policy-source-checks-v1', 'checked_at': now,
            'requests': attempted, 'sources': sources,
            'note_ko': '변경·접속 상태만 자동 확인합니다. 법적 효력·최신 개정·허가 여부는 확인하지 않습니다.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--documents', type=Path, default=ROOT / 'config/export_policy_documents.json')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--max-requests', type=int, default=4)
    args = p.parse_args()
    if not 0 <= args.max_requests <= 20:
        p.error('max-requests must be 0..20')
    with single_writer(str(args.out) + '.lock'):
        result = check_documents(read_json(args.documents)['documents'], read_json(args.out), max_requests=args.max_requests)
        atomic_json(args.out, result)
    print({'requests': result['requests'], 'statuses': [x['status'] for x in result['sources'].values()]})


if __name__ == '__main__':
    main()
