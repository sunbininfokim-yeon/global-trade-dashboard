#!/usr/bin/env python3
"""Translate public Israel research text once with Gemini; publish cache offline."""
import argparse
import json
from pathlib import Path
from build_israel_analysis import atomic
from election_watch.israel_translation import api_key, collect_texts, translate, validate_translations

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, default=ROOT/'config/israel/2026')
    parser.add_argument('--env-file', type=Path, help='Read key locally; never copy it into outputs')
    parser.add_argument('--model', default='gemini-3.8-flash')
    parser.add_argument('--check', action='store_true', help='Check existing translation cache without any API call')
    args = parser.parse_args()
    context = json.loads((args.input_dir/'coalition_context.json').read_text())
    items = collect_texts(args.input_dir, context)
    path = args.input_dir/'ko_translations.json'
    partial = path.with_suffix('.pending.json')
    previous = json.loads(partial.read_text()) if partial.exists() else json.loads(path.read_text()) if path.exists() else None
    if args.check:
        validate_translations(previous or {}, items)
        print(json.dumps({'status': 'ok', 'translations': len(items), 'api_called': False}))
        return
    def save_progress(value):
        atomic(partial, value)
        print(json.dumps({'translated_so_far': len(value['translations']), 'target': len(items)}), flush=True)
    doc = translate(items, api_key(args.env_file), args.model, previous=previous, on_batch=save_progress)
    atomic(path, doc)
    partial.unlink(missing_ok=True)
    print(json.dumps({'status': 'ok', 'translations': len(items), 'provider': doc['provider'],
                      'model': doc['model'], 'api_batches': len(doc['usage'])}))


if __name__ == '__main__':
    main()
