#!/usr/bin/env python3
"""Fetch public pages for manual source review (Cook ratings, poll releases).

The cloud agent sandbox cannot reach most publisher hosts; Actions runners can.
Each URL is saved twice -- the raw response and, when Playwright is present,
the rendered DOM plus its visible text -- with a receipt (final URL, status,
sha256). Nothing here parses or publishes data: a reviewer reads the files and
writes the reviewed input by hand, citing the receipt.
"""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36'
MAX_BYTES = 20 * 1024 * 1024


def slug(url, index):
    p = urlparse(url)
    base = re.sub(r'[^A-Za-z0-9]+', '-', f'{p.hostname}{p.path}').strip('-')[:80]
    return f'{index:02d}-{base}'


def fetch_raw(url):
    with urlopen(Request(url, headers={'User-Agent': UA}), timeout=60) as response:
        body = response.read(MAX_BYTES + 1)
        return response.status, response.geturl(), response.headers.get('Content-Type', ''), body[:MAX_BYTES]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--urls', required=True, help='whitespace-separated https URLs')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    urls = [u for u in args.urls.split() if u]
    if not urls or any(urlparse(u).scheme != 'https' for u in urls):
        raise SystemExit('https URLs only')
    args.out.mkdir(parents=True, exist_ok=True)
    try:
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start(); browser = pw.chromium.launch()
    except Exception as exc:  # rendered copy is optional
        print('playwright unavailable:', type(exc).__name__); pw = browser = None
    receipts = []
    for index, url in enumerate(urls, 1):
        name = slug(url, index); row = {'url': url, 'fetched_at': datetime.now(timezone.utc).isoformat()}
        try:
            status, final, ctype, body = fetch_raw(url)
            ext = '.pdf' if body.startswith(b'%PDF-') else '.html'
            (args.out / f'{name}.raw{ext}').write_bytes(body)
            row.update({'status': status, 'final_url': final, 'content_type': ctype,
                        'raw_file': f'{name}.raw{ext}', 'raw_sha256': hashlib.sha256(body).hexdigest(), 'raw_bytes': len(body)})
        except Exception as exc:
            row['raw_error'] = f'{type(exc).__name__}: {exc}'[:300]
        if browser and not row.get('raw_file', '').endswith('.pdf'):
            try:
                page = browser.new_page(user_agent=UA)
                page.goto(url, wait_until='networkidle', timeout=90000)
                page.wait_for_timeout(3000)
                html = page.content().encode(); text = page.inner_text('body').encode()
                (args.out / f'{name}.rendered.html').write_bytes(html)
                (args.out / f'{name}.txt').write_bytes(text)
                row.update({'rendered_final_url': page.url, 'rendered_file': f'{name}.rendered.html',
                            'text_file': f'{name}.txt', 'text_sha256': hashlib.sha256(text).hexdigest()})
                page.close()
            except Exception as exc:
                row['render_error'] = f'{type(exc).__name__}: {exc}'[:300]
        receipts.append(row); print(json.dumps({k: v for k, v in row.items() if k != 'fetched_at'}))
    if browser: browser.close(); pw.stop()
    (args.out / 'receipts.json').write_text(json.dumps(receipts, indent=2, ensure_ascii=False) + '\n')
    return 0 if any('raw_file' in r or 'text_file' in r for r in receipts) else 1


if __name__ == '__main__':
    raise SystemExit(main())
