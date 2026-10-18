"""Discover official catalogue links; candidates are not ingested as laws.

One hop from reviewed manifest records, bounded and sequential. Keep the
source page/hash and parent IDs so reviewers can accept/reject each candidate.
"""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from collect import fetch, html_content, official_url


def catalogue_links(data, source_url):
    if data.startswith(b'%PDF'):
        return []
    _, soup = html_content(data)
    found = {}
    for a in soup.select('a[href]'):
        url = urljoin(source_url, a['href'])
        path = urlparse(url).path
        label = ' '.join(a.get_text(' ', strip=True).split())
        if not official_url(url) or not 15 <= len(label) <= 2000:
            continue
        if not (path.startswith('/dok/') or '/dokumen/' in path or '/produk-hukum/' in path):
            continue
        if label.lower() in ('download dokumen', 'lihat abstrak'):
            continue
        found[url] = {'url': url, 'label': label}
    return list(found.values())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--document-id', action='append', required=True)
    p.add_argument('--output-dir', required=True)
    args = p.parse_args()
    out = Path(args.output_dir).resolve()
    repo = Path(__file__).resolve().parents[2]
    if out == repo or repo in out.parents or (out / 'candidates.json').exists():
        p.error('use a new directory outside repository')
    if len(args.document_id) > 20:
        p.error('at most 20 seeds')
    manifest = json.loads(Path(__file__).with_name('sources.json').read_text())
    seeds = [e for e in manifest if e['document_id'] in args.document_id]
    if {e['document_id'] for e in seeds} != set(args.document_id):
        p.error('unknown manifest ID')
    out.mkdir(parents=True)
    (out / 'raw').mkdir()
    result = {'checked_at': datetime.now(timezone.utc).isoformat(), 'seeds': [], 'candidates': [], 'failures': []}
    seen, blocked = set(), set()
    for seed in seeds:
        try:
            host = urlparse(seed['url']).hostname
            if host in blocked:
                raise ValueError('host_blocked_earlier_in_run')
            data, url, digest = fetch(seed['url'], out / 'raw')
            result['seeds'].append({'document_id': seed['document_id'], 'url': url, 'raw_sha256': digest})
            for link in catalogue_links(data, url):
                if link['url'] in seen:
                    continue
                seen.add(link['url'])
                result['candidates'].append({**link, 'discovered_from': seed['document_id'], 'seed_url': url,
                                             'seed_sha256': digest, 'review_status': 'candidate'})
        except Exception as exc:
            if getattr(getattr(exc, 'response', None), 'status_code', None) in (403, 429):
                blocked.add(urlparse(seed['url']).hostname)
            result['failures'].append({'document_id': seed['document_id'], 'error': str(exc)[:300]})
        tmp = out / 'candidates.json.tmp'
        tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        tmp.replace(out / 'candidates.json')
        time.sleep(3)
    print(json.dumps({'seeds': len(result['seeds']), 'candidates': len(result['candidates']), 'failures': len(result['failures'])}))


if __name__ == '__main__':
    main()
