"""HTML cells survive extraction; changed releases never inherit approval."""
import copy
from pathlib import Path
import unittest
from urllib.error import URLError

from election_watch.poll_html_evidence import canonical_region, html_region_fingerprint, FORMAT
from election_watch.poll_primary_supplements import merge_primary_supplements
from election_watch.polls import read

ROOT = Path(__file__).resolve().parents[1]
DOC = {'url': 'https://pollster.example/release-2026', 'format': FORMAT,
       'selector': {'tag': 'main', 'id': 'poll'},
       'start_text': '2026 general election poll',
       'end_text': 'Sponsored by Example News.'}
HTML = b'''<nav>Changing headlines</nav><main id="poll"><h1>2026 general election poll</h1>
<br/><table><tr><th>Candidate</th><th>Percent</th></tr><tr><td>Candidate D</td><td>51</td></tr>
<tr><td>Candidate R</td><td>38</td></tr></table><script>invalid numbers 90 10</script>
<p>800 likely voters; October 10-12, 2026.</p><p>Sponsored by Example News.</p>
<aside>Related articles change daily</aside></main>'''


class Response:
    status = 200
    def __init__(self, url, body): self.url, self.body = url, body
    def geturl(self): return self.url
    def read(self, n): return self.body[:n]
    def __enter__(self): return self
    def __exit__(self, *args): pass


class HTMLEvidenceTests(unittest.TestCase):
    def entry(self):
        # Existing reviewed schema, synthetic document; no state config mutation.
        entry = copy.deepcopy(read(ROOT/'config/usa_polls/primary_supplements_2026.json')['records'][0])
        document = {**copy.deepcopy(DOC), 'sha256': html_region_fingerprint(HTML, DOC)}
        entry['documents'] = [document]
        return entry

    def merge(self, entry, body=HTML, provider=(), approved=True, opener=None):
        return merge_primary_supplements(list(provider),
            {'schema': 'usa_reviewed_primary_poll_supplements_v1', 'cycle': 2026, 'records': [entry]},
            '2026-10-16', opener=opener or (lambda req, **kw: Response(req.full_url, body)),
            reviewed_entries=[entry] if approved else [])

    def test_table_cells_are_separated_and_scripts_omitted(self):
        text = canonical_region(HTML, DOC)
        self.assertIn('Candidate D 51 Candidate R 38', text)
        self.assertNotIn('invalid numbers', text)
        self.assertNotIn('Related articles', text)

    def test_navigation_related_and_whitespace_changes_do_not_break_evidence(self):
        changed = HTML.replace(b'Changing headlines', b'New unrelated news').replace(
            b'Related articles change daily', b'Other poll links').replace(b'<td>51', b'<td>\n 51')
        self.assertEqual(html_region_fingerprint(HTML, DOC), html_region_fingerprint(changed, DOC))

    def test_evidence_change_is_reference_only_and_preserves_original_dates(self):
        entry = self.entry()
        rows, receipts = self.merge(entry, HTML.replace(b'<td>51', b'<td>52'))
        self.assertEqual(receipts[0]['status'], 'carried_forward_reference_only')
        self.assertEqual(receipts[0]['documents'][0]['status'], 'changed_review_required')
        self.assertEqual(rows[0]['end_date'], entry['record']['end_date'])
        self.assertEqual(rows[0]['answers'], entry['record']['answers'])

    def test_block_redesign_or_ambiguous_boundaries_never_means_zero_polls(self):
        for body in (b'Access denied', HTML.replace(b'id="poll"', b'id="new"'), HTML+HTML,
                     HTML.replace(b'</main>', b''), HTML.replace(b'<table>', b'<table>'+DOC['start_text'].encode())):
            with self.subTest(body=body[:40]):
                rows, receipts = self.merge(self.entry(), body)
                self.assertEqual(receipts[0]['status'], 'carried_forward_reference_only')
                self.assertEqual(len(rows), 1)
                self.assertEqual(receipts[0]['documents'][0]['status'], 'unavailable')

    def test_same_api_wave_deduplicated_and_conflicting_values_rejected(self):
        entry = self.entry()
        provider = copy.deepcopy(entry['record']); provider['id'] = 'later-api-id'
        rows, receipts = self.merge(entry, provider=[provider])
        self.assertEqual(len(rows), 1)
        self.assertEqual(receipts[0]['provider_duplicate_ids'], ['later-api-id'])
        provider['answers'][0]['pct'] += 1
        with self.assertRaisesRegex(ValueError, 'wave_conflict'):
            self.merge(entry, provider=[provider])

    def test_exact_entry_review_required_no_publisher_blanket_approval(self):
        with self.assertRaisesRegex(ValueError, 'unreviewed primary document'):
            self.merge(self.entry(), approved=False)

    def test_network_failure_keeps_reference(self):
        def unavailable(*a, **kw): raise URLError('offline')
        rows, receipts = self.merge(self.entry(), opener=unavailable)
        self.assertEqual(receipts[0]['status'], 'carried_forward_reference_only')
        self.assertEqual(rows[0]['start_date'], self.entry()['record']['start_date'])


if __name__ == '__main__': unittest.main()
