"""Shared release-envelope validation for real-time macro analysis."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


VINTAGES = {"first", "second", "third", "revised", "current"}
QUALITIES = {"observed", "parsed", "manual_review", "missing"}


def parse_timestamp(value: str) -> datetime:
    """Parse an ISO timestamp and require a timezone."""
    if not value:
        raise ValueError("timestamp is required")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp must include timezone: {value}")
    return parsed.astimezone(timezone.utc)


def validate_release_envelope(row: dict[str, Any]) -> list[str]:
    """Return contract errors without mutating the source record."""
    errors: list[str] = []
    required = (
        "source_id",
        "release_id",
        "published_at",
        "reference_period",
        "vintage",
        "source_url",
        "quality",
        "retrieved_at",
    )
    for key in required:
        if row.get(key) in (None, ""):
            errors.append(f"missing:{key}")
    for key in ("published_at", "retrieved_at"):
        if row.get(key):
            try:
                parse_timestamp(str(row[key]))
            except ValueError as exc:
                errors.append(f"invalid:{key}:{exc}")
    if row.get("vintage") not in VINTAGES:
        errors.append(f"invalid:vintage:{row.get('vintage')}")
    if row.get("quality") not in QUALITIES:
        errors.append(f"invalid:quality:{row.get('quality')}")
    url = str(row.get("source_url") or "")
    if url and not url.startswith("https://"):
        errors.append("invalid:source_url:https_required")
    return errors


def available_as_of(row: dict[str, Any], as_of: str) -> bool:
    """True only when a release was public by the decision timestamp."""
    if validate_release_envelope(row):
        return False
    return parse_timestamp(str(row["published_at"])) <= parse_timestamp(as_of)


def point_in_time_rows(rows: Iterable[dict[str, Any]], as_of: str) -> list[dict[str, Any]]:
    """Filter releases to information genuinely available at ``as_of``."""
    return [dict(row) for row in rows if available_as_of(row, as_of)]
