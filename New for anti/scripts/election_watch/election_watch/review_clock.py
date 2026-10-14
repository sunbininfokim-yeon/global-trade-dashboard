"""Validate today's reviewed catalogs without re-dating historical captures."""
from datetime import datetime, timezone, date


def validation_day(fallback, *catalogs, today=None):
    ceiling=date.fromisoformat(today or datetime.now(timezone.utc).date().isoformat())
    days=[date.fromisoformat(fallback)]
    def visit(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('reviewed_on','ballot_reviewed_on') and isinstance(item,str):
                    day=date.fromisoformat(item)
                    if day>ceiling:raise ValueError('future catalog review')
                    days.append(day)
                else:visit(item)
        elif isinstance(value,list):
            for item in value:visit(item)
    for catalog in catalogs:visit(catalog)
    return max(days).isoformat()
