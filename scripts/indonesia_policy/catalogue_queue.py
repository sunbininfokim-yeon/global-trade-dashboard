"""Turn the full reconciliation report into a review queue, not an ingest manifest.

Hints only prioritize reviews; nonmatching titles remain queued. No AI or fetches.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

HINTS = {
 'coal':r'\bbatu\s*bara\b|\bbatubara\b|\bcoal\b',
 'mining':r'\bminerba\b|\bmineral\b|\btambang\b|\bpertambangan\b|\bnikel\b|\bsmelter\b|\bbijih\b|\bferonikel\b|\bbauksit\b',
 'palm_oil':r'\bsawit\b|\bcpo\b|\bperkebunan\b',
 'biofuel':r'\bbiofuel\b|\bbiodiesel\b|\bbioenergi\b|\bbahan bakar nabati\b|\bbioetanol\b',
 'cross_sector':r'\blingkungan\b|\bkehutanan\b|\btanah\b|\btata ruang\b|\bperizinan\b|\binvestasi\b|\bpenanaman modal\b|\bperseroan\b|\bkontrak\b|\bpajak\b|\bpenerimaan negara\b|\bro[yj]alti\b|\bekspor\b|\bimpor\b|\bsubsidi\b|\bfasilitas\b|\btenaga kerja\b|\bketenagakerjaan\b|\benergi\b'
}
def build(data):
 if data.get('status',{}).get('country')!='IDN':raise ValueError('Not an IDN report')
 queue=[]
 for row in data['items']:
  m=row['metadata'];matches=row['matches'];status=row['match_status']
  if status=='url_match' and matches[0]['content_kind']=='official_text' and not matches[0]['text_truncated']:continue
  action={'unmatched':'review_new_metadata','identity_candidate':'review_identity_and_source','ambiguous':'resolve_identity','url_match':'recover_known_text'}[status]
  parts=[m.get(k) for k in ['issuer_key','jurisdiction','document_type','document_number','document_year']]
  group=hashlib.sha256(json.dumps(parts,sort_keys=True).encode()).hexdigest() if parts[0] and all(parts[i] for i in [2,3,4]) else None
  queue.append(dict(source_id=row['source_id'],source_record_id=row['source_record_id'],title=m['title'],
                    action=action,review_status='unreviewed',topic_hints=[k for k,v in HINTS.items() if re.search(v,m['title'],re.I)],
                    possible_same_identity_group=group,source_page=m['page_url'],detail_url=m.get('detail_url'),download_url=m.get('download_url'),
                    external_attachment=bool(m.get('external_attachment')),matches=matches))
 queue.sort(key=lambda x:(not bool(x['topic_hints']),x['source_id'],x['source_record_id']))
 return dict(country='IDN',purpose='Human review candidates; not laws or legal applicability findings',records=queue,
             total=len(queue),with_topic_hints=sum(bool(x['topic_hints']) for x in queue))
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('report',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 repo=Path(__file__).resolve().parents[2];out=a.output.resolve()
 if out==repo or repo in out.parents or out.exists():p.error('use a new output file outside repository')
 result=build(json.loads(a.report.read_text()));out.parent.mkdir(parents=True,exist_ok=True,mode=0o700);out.write_text(json.dumps(result,ensure_ascii=False,indent=2));out.chmod(0o600)
 print(json.dumps({k:result[k] for k in ['country','total','with_topic_hints']}))
