#!/usr/bin/env python3
"""Detect changes in public poll sources; never extract new vote percentages.

Reviewed baselines live in the input registry. A changed document remains changed
on every run until its content is reviewed and the baseline is deliberately updated.
"""
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import io
from pathlib import Path
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from election_watch.polls import atomic, read, https_url, require, digest

ROOT = Path(__file__).resolve().parent
MAX_BYTES = 12 * 1024 * 1024


class VisibleText(HTMLParser):
    def __init__(self, article_only=False):
        super().__init__()
        self.hidden = 0
        self.text = []
        self.links = []
        self.article_only = article_only
        self.capture_depth = 0

    def handle_starttag(self, tag, attrs):
        if self.article_only:
            if tag == 'div' and (self.capture_depth or 'entry-content' in dict(attrs).get('class', '').split()):
                self.capture_depth += 1
            if not self.capture_depth:
                return
        if tag in ('script', 'style'):
            self.hidden += 1
        if tag == 'a':
            self.links.extend(v for k, v in attrs if k == 'href' and v)

    def handle_endtag(self, tag):
        if self.article_only and tag == 'div' and self.capture_depth:
            self.capture_depth -= 1
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, text):
        if not self.hidden and (not self.article_only or self.capture_depth):
            self.text.append(text)


def fingerprint(blob, kind):
    if kind in ('html', 'html_article'):
        parser = VisibleText(article_only=kind == 'html_article')
        parser.feed(blob.decode('utf-8', errors='replace'))
        require(bool(parser.text), 'missing HTML content')
        blob = re.sub(r'\s+', ' ', ' '.join(parser.text + sorted(set(parser.links)))).encode()
    elif kind == 'xlsx':
        # Ignore volatile ZIP metadata/style changes. Preserve cells, formulas and labels.
        ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            require(sum(i.file_size for i in z.infolist()) <= 80 * 1024 * 1024, 'xlsx expanded size')
            strings = []
            if 'xl/sharedStrings.xml' in z.namelist():
                strings = [''.join(t.itertext()) for t in ET.fromstring(z.read('xl/sharedStrings.xml'))]
            values = []
            for name in sorted(n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', n)):
                for c in ET.fromstring(z.read(name)).findall('.//m:c', ns):
                    v = c.find('m:v', ns)
                    value = v.text if v is not None else ''.join(c.itertext())
                    if c.get('t') == 's' and value:
                        value = strings[int(value)]
                    values.append((name, c.get('r'), value, c.findtext('m:f', default='', namespaces=ns)))
            blob = repr(values).encode()
    elif kind != 'pdf':
        raise ValueError('unsupported fingerprint format')
    return hashlib.sha256(blob).hexdigest()


def fetch(url):
    require(https_url(url), 'HTTPS required')
    request = urllib.request.Request(url, headers={'User-Agent': 'ElectionPollSourceMonitor/1.0'})
    with urllib.request.urlopen(request, timeout=25) as response:
        require(https_url(response.url), 'redirect must remain HTTPS')
        blob = response.read(MAX_BYTES + 1)
        require(0 < len(blob) <= MAX_BYTES, 'empty or oversized document')
        return blob


def check_document(entry, fetcher=fetch):
    try:
        actual = fingerprint(fetcher(entry['url']), entry['format'])
        expected = entry.get('reviewed_fingerprint')
        return {'url': entry['url'], 'status': ('unreviewed_baseline' if not expected else
                'unchanged' if expected == actual else 'changed'), 'fingerprint': actual}
    except Exception as exc:
        # Do not echo request headers, credentials or server response bodies.
        return {'url': entry['url'], 'status': 'error', 'error_type': type(exc).__name__}


def monitor(data, fetcher=fetch):
    result = {'schema': 'usa_poll_monitor_v1',
              'checked_at': datetime.now(timezone.utc).isoformat(), 'input_fingerprint': digest(data),
              'sources': {}, 'discovery': []}
    for sid, source in data['sources'].items():
        checks = [check_document(e, fetcher) for e in source.get('watch_documents', [])]
        statuses = {c['status'] for c in checks}
        status = next((s for s in ('error', 'changed', 'unreviewed_baseline') if s in statuses),
                      'unchanged' if checks else 'not_checked')
        result['sources'][sid] = {'status': status, 'documents': checks}
    result['discovery'] = [check_document(e, fetcher) for e in data['discovery_pages']]
    result['error_count'] = sum(c['status'] == 'error' for s in result['sources'].values()
                                for c in s['documents']) + sum(c['status'] == 'error' for c in result['discovery'])
    result['needs_review'] = any(s['status'] in ('changed', 'unreviewed_baseline') for s in result['sources'].values()) or any(
        c['status'] in ('changed', 'unreviewed_baseline') for c in result['discovery'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'config/usa_polls/2026.json')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = monitor(read(args.input))
    atomic(args.report, result)
    print({'source_count': len(result['sources']), 'error_count': result['error_count'],
           'needs_review': result['needs_review']})
    return 1 if result['error_count'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
