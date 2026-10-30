#!/usr/bin/env python3
"""Extract a reviewed HTML evidence region for a state release review.

The output is a review artifact, never a poll observation or an approval.
No existing catalog, state packet or public output is modified.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from election_watch.poll_html_evidence import FORMAT, canonical_region
from election_watch.polls import atomic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--html', type=Path, required=True)
    parser.add_argument('--document', type=Path, required=True,
                        help='URL, selector {tag,id}, start_text and end_text, reviewed explicitly')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in (args.html.resolve(), args.document.resolve()):
        parser.error('output must not overwrite input')
    document = json.loads(args.document.read_text())
    url = urlparse(document['url'])
    if url.scheme != 'https' or not url.hostname or url.username or url.password:
        parser.error('document must identify a public HTTPS release URL')
    if args.html.stat().st_size > 3 * 1024 * 1024:
        parser.error('HTML exceeds the primary release capture limit')
    body = args.html.read_bytes()
    text = canonical_region(body, document)
    document.update(format=FORMAT, sha256=hashlib.sha256(text.encode()).hexdigest())
    atomic(args.output, {'schema': 'usa_poll_html_evidence_review_v1',
        'status': 'requires_release_and_quality_review', 'signal_eligible': False,
        'document': document, 'raw_body_sha256': hashlib.sha256(body).hexdigest(),
        'evidence_text': text})
    print('HTML evidence extracted; release/quality review and state packet required')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
