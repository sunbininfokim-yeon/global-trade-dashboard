"""Prepare a reviewed local OCR observation; never downloads, embeds or writes DB."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from pypdf import PdfReader
from collect import official_url, normalized, verify_identity, classify_pdf


def prepare(entry, pdf_bytes, ocr_bytes, review, page_count):
    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
    ocr_hash = hashlib.sha256(ocr_bytes).hexdigest()
    data = json.loads(ocr_bytes)
    if (not official_url(entry['url']) or not pdf_bytes.startswith(b'%PDF')
            or len(pdf_bytes) > 12 * 1024 * 1024 or not 1 <= page_count <= 25
            or review.get('pdf_sha256') != pdf_hash or review.get('ocr_sha256') != ocr_hash
            or review.get('method') != 'identity_and_selected_pages'
            or not isinstance(review.get('note'), str) or len(review['note']) < 40
            or not review.get('pages') or any(type(p) is not int or p < 1 or p > page_count for p in review['pages'])):
        raise ValueError('Invalid or stale reviewed OCR source')
    if data.get('engine') != 'Apple Vision VNRecognizeTextRequest' or data.get('language_correction') is not False:
        raise ValueError('Unrecognized OCR engine/settings')
    pages = data.get('pages', [])
    if [p.get('page') for p in pages] != list(range(1, page_count + 1)):
        raise ValueError('Missing or duplicate OCR page')
    for p in pages:
        lines = p.get('lines', [])
        if not lines or p.get('text') != '\n'.join(x['text'] for x in lines):
            raise ValueError('Missing or inconsistent OCR text')
        if any(not 0 <= x.get('confidence', -1) <= 1 for x in lines):
            raise ValueError('Invalid OCR confidence')
    text = normalized('\n'.join(p['text'] for p in pages))
    if not 150 <= len(text) <= 300000 or classify_pdf(text) != 'official_text' or not verify_identity(text, entry):
        raise ValueError('OCR identity/final text not verified')
    observed = datetime.now(timezone.utc).isoformat()
    return {
        **{k: entry[k] for k in ['document_id','title','title_ko','issuer_name','issuer_level','jurisdiction','document_type','document_number','document_year','topics','primary_stage']},
        'country_code':'IDN','scope_note':entry['scope_note'] + ' Local OCR-derived retrieval text; figures, tables and wording require the original PDF. Full transcription has not been manually verified.',
        'source_url':entry['url'],'text_source_url':entry['url'],'observed_at':observed,
        'content_kind':'official_text','text_content':text,'text_truncated':False,
        'content_hash':hashlib.sha256(text.encode()).hexdigest(),'raw_sha256':pdf_hash,'raw_text_sha256':pdf_hash,
        'body_status':'local_ocr_selected_pages_reviewed','legal_status':'unverified',
        'status_note':'공식 PDF의 로컬 OCR 검색용 본문입니다. 전체 전사·숫자·표·현행 효력은 미확인입니다.',
        'ocr_review':{**review,'engine':data['engine'],'page_count':page_count,'language':data.get('language'),
                     'low_confidence_lines':sum(x['confidence'] < .8 for p in pages for x in p['lines']),
                     'full_transcription_verified':False},
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['manifest','document-id','pdf-file','ocr-json','review-file','output-dir']:
        p.add_argument('--' + name, required=True)
    a = p.parse_args(); out = Path(a.output_dir).resolve(); repo = Path(__file__).resolve().parents[2]
    if out.exists() or out == repo or repo in out.parents:
        p.error('Use a new directory outside repository')
    entries = [d for d in json.loads(Path(a.manifest).read_text()) if d['document_id'] == a.document_id]
    if len(entries) != 1:
        p.error('Expected one reviewed manifest identity')
    raw = Path(a.pdf_file).read_bytes()
    doc = prepare(entries[0],raw,Path(a.ocr_json).read_bytes(),json.loads(Path(a.review_file).read_text()),len(PdfReader(a.pdf_file).pages))
    out.mkdir(mode=0o700, parents=True)
    target = out / 'collection.json'
    target.write_text(json.dumps({'checked_at':doc['observed_at'],'documents':[doc],'failures':[]},ensure_ascii=False,indent=2));target.chmod(0o600)
    print(json.dumps({'document_id':doc['document_id'],'pages':doc['ocr_review']['page_count'],'characters':len(doc['text_content']),'legal_status':doc['legal_status']}))


if __name__ == '__main__':
    main()
