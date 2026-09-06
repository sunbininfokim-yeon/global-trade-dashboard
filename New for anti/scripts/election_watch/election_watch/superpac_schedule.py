"""Date-driven collection plan; reporting cycles never imply a ballot election."""
from datetime import datetime, timezone


def reporting_cycle(day=None):
    year = (day or datetime.now(timezone.utc).date()).year
    return year + year % 2


def collection_plan(day, cadence='daily', force=False, cycle=None):
    if cadence not in ('daily', 'weekly'):
        raise ValueError('cadence must be daily or weekly')
    if not force and cadence == 'weekly' and day.weekday() != 6:
        return []
    current = cycle or reporting_cycle(day)
    if current < 2010 or current % 2:
        raise ValueError('cycle must be even and >= 2010')
    # Revisit the preceding cycle monthly for late/amended reports; retain older assets.
    cycles = [current]
    if cycle is None and ((cadence == 'daily' and day.day == 1) or (cadence == 'weekly' and day.day <= 7)):
        cycles.append(current - 2)
    return cycles
