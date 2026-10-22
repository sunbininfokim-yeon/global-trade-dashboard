"""Conservative, deterministic admission of complete identified official text.

Retrieval tags are not legal applicability. Unsupported/draft/ambiguous evidence
stays in the catalogue, never silently becomes a search document or a mail.
"""
import hashlib
import json
import re
from urllib.parse import urlparse
from catalogue import identity
from collect import normalized, official_url, ORDER

RULES = {
 'coal': r'\b(?:batu\s*bara|coal)\b', 'nickel_mining': r'\b(?:nikel|nickel|feronikel)\b',
 'palm_oil': r'\b(?:sawit|cpo|palm oil)\b', 'biofuel': r'\b(?:bahan bakar nabati|biofuel|biodiesel|bioetanol)\b',
 'bauxite': r'\b(?:bauksit|alumina|aluminium|aluminum)\b', 'copper': r'\btembaga\b',
 'tin': r'\btimah\b(?!\s+hitam)', 'cobalt': r'\bkobalt\b', 'manganese': r'\bmangan\b',
 'iron_steel': r'\b(?:besi|baja)\b', 'silica': r'\b(?:silika|kuarsa)\b',
 'gold_silver': r'\b(?:emas|perak)\b', 'rare_earths': r'\b(?:logam|unsur) tanah jarang\b'
}
MINING = r'\b(?:pertambangan|mineral|minerba)\b'
COMMON = r'\b(?:perlindungan dan pengelolaan lingkungan hidup|perizinan berusaha|penanaman modal|perseroan terbatas|ketenagakerjaan|penerimaan negara bukan pajak|perpajakan|tata ruang|kebijakan dan pengaturan (?:ekspor|impor))\b'
ISSUERS = {'national':'Pemerintah Pusat','esdm':'Kementerian Energi dan Sumber Daya Mineral',
 'kemendag':'Kementerian Perdagangan','kemenperin':'Kementerian Perindustrian',
 'pertanian':'Kementerian Pertanian','kemenkeu':'Kementerian Keuangan'}
HEADER = re.compile(r'\b(?:UNDANG[- ]UNDANG|PERATURAN\s+(?:PEMERINTAH|PRESIDEN|MENTERI|DAERAH|GUBERNUR)|INSTRUKSI\s+PRESIDEN)\b',re.I)

class Held(ValueError):
    pass

def topics(text):
    # "Sumber Daya Mineral" in an issuer name is not a mining subject.
    text=re.split(r'\btentang\b',text,flags=re.I)[-1]
    found={key for key,pattern in RULES.items() if re.search(pattern,text,re.I)}
    if re.search(MINING,text,re.I):
        found.update(set(RULES)-{'palm_oil','biofuel'})
    if re.search(COMMON,text,re.I):
        found.update(RULES)
    return sorted(found)

def key(meta):
    number=str(meta.get('document_number') or '')
    if not re.fullmatch(r'[0-9]{1,6}',number) or int(number)<1:
        raise Held('unsupported_or_missing_document_number')
    if type(meta.get('document_year')) is not int or not 1900<=meta['document_year']<=2100:
        raise Held('missing_document_year')
    return (meta.get('issuer_key') if meta.get('issuer_level')=='national' else meta.get('jurisdiction'),
            meta.get('document_type'),str(int(number)),meta['document_year'])

def prepare(row, source):
    m=row['metadata']; parsed=identity(m['title'])
    expected=key(parsed)
    if row.get('match_status')=='ambiguous' or len(row.get('matches',[]))>1:
        raise Held('ambiguous_existing_identity')
    if any(parsed.get(k)!=m.get(k) for k in ('document_type','document_number','document_year','issuer_key','issuer_level','jurisdiction')):
        raise Held('catalogue_identity_conflict')
    if parsed['issuer_level']=='national':
        if parsed['issuer_key'] not in ISSUERS:raise Held('unresolved_issuer')
        jurisdiction='Indonesia'; issuer=ISSUERS[parsed['issuer_key']]
    elif parsed['issuer_level']=='provincial' and parsed['jurisdiction'] and parsed['document_type'] in ('Perda','Pergub'):
        jurisdiction=parsed['jurisdiction'];issuer='Pemerintah Provinsi '+jurisdiction
    else:
        raise Held('unresolved_issuer_or_jurisdiction')
    url=m.get('detail_url') or m.get('download_url')
    if not url or not official_url(url) or not official_url(m.get('page_url','')) or urlparse(m['page_url']).hostname!=urlparse(source['url']).hostname:
        raise Held('no_identified_official_source')
    tags=topics(m['title'])
    if not tags:raise Held('unclassified_topic')
    existing=row.get('matched_document')
    if existing:
        if (existing['document_type'],str(int(existing['document_number'])) if re.fullmatch(r'[0-9]+',existing['document_number']) else existing['document_number'],existing['document_year'])!=expected[1:]:
            raise Held('existing_identity_conflict')
        if existing['issuer_level']!=parsed['issuer_level'] or existing['jurisdiction']!=jurisdiction:
            raise Held('existing_jurisdiction_conflict')
    doc_id=existing['document_id'] if existing else 'idn-auto-'+hashlib.sha256(json.dumps(expected).encode()).hexdigest()[:24]
    stage=next((s for s in ORDER if s in tags),'mineral_mining')
    return dict(document_id=doc_id,url=url,title=m['title'],title_ko=existing['title_ko'] if existing else '공식 원문 · '+m['title'],
      issuer_name=issuer,issuer_level=parsed['issuer_level'],jurisdiction=jurisdiction,
      document_type=parsed['document_type'],document_number=expected[2],document_year=expected[3],
      topics=tags,primary_stage=stage,identity_phrases=[str(parsed['document_number']),str(parsed['document_year'])],
      scope_note=existing['scope_note'] if existing else 'Automatically identified official text; retrieval tags only. Current legal effect and project/national/regional applicability remain unverified.',
      expected_identity=expected)

def validate_document(doc, entry, row):
    if doc.get('content_kind')!='official_text' or doc.get('text_truncated') is not False:
        raise Held('complete_official_text_unavailable')
    text=normalized(doc['text_content']); start=HEADER.search(text[:8000])
    if not start:raise Held('final_document_heading_missing')
    if re.search(r'\bRANCANGAN\b',text[max(0,start.start()-500):start.start()],re.I):raise Held('draft_heading')
    heading=text[start.start():start.start()+6000]
    actual=identity(heading)
    if key(actual)!=tuple(entry['expected_identity']) or actual['issuer_level']!=entry['issuer_level']:
        raise Held('final_document_identity_mismatch')
    common=sorted(set(entry['topics']) & set(topics(re.split(r'\b(?:MEMUTUSKAN|Menimbang)\b',heading,maxsplit=1,flags=re.I)[0])))
    if not common:raise Held('topic_not_supported_by_document_heading')
    if doc['country_code']!='IDN' or doc['legal_status']!='unverified' or hashlib.sha256(doc['text_content'].encode()).hexdigest()!=doc['content_hash']:
        raise Held('invalid_document_artifact')
    doc['topics']=common
    doc['automatic_admission']={'version':1,'metadata_hash':row['metadata_hash'],'source_id':row['source_id'],
      'source_record_id':row['source_record_id'],'source_page':row['metadata']['page_url'],
      'heading_identity_verified':True,'legal_effect_verified':False,'translation':'original_title_not_machine_translation'}
    return doc
