"""Exact, reviewed HTML evidence regions (including table cells), without an API.

This extracts evidence, not a guessed poll schema. A state-owned release review
still supplies candidate identities, question n, dates, population and toplines.
"""
import hashlib
from html.parser import HTMLParser

from .polls import require

FORMAT = 'reviewed_html_region_v1'
VOID = frozenset(('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
                  'link', 'meta', 'param', 'source', 'track', 'wbr'))
IGNORED = frozenset(('script', 'style', 'template', 'noscript'))


def canonical_region(body, document):
    """One tag/id and unique reviewed text boundaries; fail closed on redesign."""
    selector = document['selector']
    require(set(selector) == {'tag', 'id'} and selector['tag'] in ('main', 'article', 'div', 'section', 'table')
            and isinstance(selector['id'], str) and selector['id'], 'invalid HTML evidence selector')
    start, end = document['start_text'], document['end_text']
    require(isinstance(start, str) and isinstance(end, str) and len(start) >= 15 and len(end) >= 15
            and start != end, 'invalid HTML evidence boundaries')

    class Region(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack = []; self.regions = []; self.current = None; self.depth = None

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == selector['tag'] and attrs.get('id') == selector['id']:
                require(self.current is None, 'nested HTML evidence selector')
                self.current = []; self.depth = len(self.stack)
            if tag not in VOID:
                self.stack.append(tag)

        def handle_endtag(self, tag):
            if tag in VOID:
                return
            if tag in self.stack:
                index = len(self.stack) - 1 - self.stack[::-1].index(tag)
                if self.current is not None and index <= self.depth:
                    self.regions.append(' '.join(' '.join(self.current).split()))
                    self.current = None; self.depth = None
                del self.stack[index:]

        def handle_data(self, data):
            if self.current is not None and not IGNORED.intersection(self.stack):
                self.current.append(data)

    parser = Region(); parser.feed(body.decode('utf-8')); parser.close()
    require(parser.current is None and len(parser.regions) == 1, 'missing/ambiguous/unclosed HTML evidence region')
    text = parser.regions[0]
    require(text.count(start) == text.count(end) == 1, 'missing/ambiguous HTML evidence boundary')
    left, right = text.index(start), text.index(end)
    require(right > left, 'reversed HTML evidence boundaries')
    evidence = text[left:right + len(end)]
    require(len(evidence) >= 100, 'HTML evidence too short')
    return evidence


def html_region_fingerprint(body, document):
    return hashlib.sha256(canonical_region(body, document).encode('utf-8')).hexdigest()
