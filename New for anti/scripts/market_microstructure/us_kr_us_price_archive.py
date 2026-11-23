"""Independent, immutable prospective receipts for the US price factor."""

import json
import os
import re
import tempfile
from pathlib import Path

import pandas as pd


SCHEMA = 'us-kr-us-price-first-v1'


def first_path(root, target, model_id):
    if not re.fullmatch(r'[0-9a-f]{64}', model_id):
        raise ValueError('invalid US price factor model ID')
    return Path(root) / target / 'us_price' / model_id / 'first.json'


def archive_us_price(root, target, source, us_day, cutoff, factor):
    """Reuse today's first result on retries, including a later failed fetch."""
    path = first_path(root, target, factor['model_id'])
    if path.exists():
        return json.loads(path.read_text()), path
    generated = pd.Timestamp(factor.get('generated_at'))
    if (factor['status'] != 'available' or factor.get('as_of') != us_day
            or generated.tzinfo is None or generated > pd.Timestamp(cutoff)):
        return None, None
    record = {
        'schema_version': SCHEMA,
        'target_date': target,
        'KR_source_date': source,
        'US_source_date': us_day,
        'forecast_cutoff_KST': cutoff,
        'generated_at': factor['generated_at'],
        'factor': factor,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent) as temporary:
        json.dump(record, temporary, ensure_ascii=False, allow_nan=False, indent=2)
        temporary.write('\n')
        temporary.flush()
        try:
            os.link(temporary.name, path)
        except FileExistsError:
            return json.loads(path.read_text()), path
    return record, path
