"""Validate the export-control catalogue against the weekly survey contract.

A row the screen paints has to be checkable again next Monday: dates parse,
the commodity slug is one this survey watches, and `high` is not hanging off
a news homepage. The script prints one line per problem and exits 1.
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

from .catalogue import DIRECTORY as CATALOGUE
from .catalogue import load as load_catalogue
from .universe import load as load_universe

LEVELS = {"prohibited", "restricted", "watch", "lifted"}
MEASURES = {"ban", "quota", "duty", "licensing", "state_trading", "levy", "min_price"}
CONFIDENCE = {"high", "medium", "low"}
MONTH = re.compile(r"^\d{4}-\d{2}$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
HS = re.compile(r"^\d{4}(\d{2}){0,3}$")  # 4, 6, 8 or 10 digits, no guesses pasted as text
ISO3 = re.compile(r"^[A-Z]{3}$")
ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# A news write-up can support medium. It cannot support high.
NEWS_HOSTS = {
    "bloomberg.com", "reuters.com", "nst.com.my", "infobae.com",
    "palmoilmagazine.com", "lexology.com", "globaltradealert.org",
    "huandacocoa.com", "fertilizerdaily.com", "metal.com",
    "caalley.com", "taxguru.in", "a2ztaxcorp.net", "ppt.ru", "klerk.ru",
}

# Official hosts that still publish the PDF over http.
HTTP_OK_HOSTS = {"static.government.ru", "government.ru", "english.mofcom.gov.cn"}


def _host(url):
    host = (urlsplit(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _parse_day(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def validate_document(doc, universe, today=None):
    today = today or date.today()
    errors = []
    keys = set(universe.get("commodity_keys") or [])
    if doc.get("schema_version") != "export-controls-v2":
        errors.append("schema_version must be export-controls-v2")
    # Categories are whatever modules the manifest lists; adding a group is a
    # new file plus a manifest line, not an edit here.
    categories = set(doc.get("categories") or {})
    if not categories:
        errors.append("manifest lists no category modules")
    module_of = doc.get("module_of") or {}
    if not MONTH.match(str(doc.get("as_of") or "")):
        errors.append("as_of must be YYYY-MM")
    if doc.get("status") not in {"curated_seed", "weekly_survey"}:
        errors.append("status must be curated_seed or weekly_survey")

    controls = doc.get("controls")
    if not isinstance(controls, list):
        return errors + ["controls must be a list"]

    seen = set()
    for c in controls:
        cid = c.get("id") or "?"
        prefix = cid

        def err(msg, _prefix=prefix):
            errors.append(f"{_prefix}: {msg}")

        if not ID.match(str(cid)):
            err("id must be lowercase slug")
        elif cid in seen:
            err("duplicate id")
        seen.add(cid)

        if not ISO3.match(str(c.get("iso") or "")):
            err("iso must be ISO3")
        if c.get("category") not in categories:
            err("category")
        elif module_of.get(cid, c.get("category")) != c.get("category"):
            err(f"category {c.get('category')} filed in {module_of[cid]}.json")
        if c.get("level") not in LEVELS:
            err("level")
        if c.get("measure_type") not in MEASURES:
            err("measure_type")
        if c.get("confidence") not in CONFIDENCE:
            err("confidence")
        if not MONTH.match(str(c.get("since") or "")):
            err("since must be YYYY-MM")
        for field in ("effective_from", "verified_at", "verified_as_of"):
            if not DAY.match(str(c.get(field) or "")):
                err(f"{field} must be YYYY-MM-DD")
        commodities = c.get("commodities") or []
        if not commodities:
            err("commodities empty")
        for slug in commodities:
            if slug not in keys:
                err(f"commodity {slug} is outside the survey universe")
        for hs in c.get("hs_prefixes") or []:
            if not HS.match(str(hs)):
                err(f"hs prefix {hs} is not a digit code")

        url = c.get("url") or ""
        parts = urlsplit(url)
        host = _host(url)
        if parts.scheme not in {"http", "https"} or not host:
            err("url must be http(s)")
        elif parts.scheme == "http" and host not in HTTP_OK_HOSTS:
            err("url should be https")
        if c.get("confidence") == "high":
            if host in NEWS_HOSTS or host.endswith(".medium.com"):
                err("high confidence cannot cite a news host")
            if parts.path in {"", "/"}:
                err("high confidence needs a document path, not a homepage")

        if c.get("level") == "lifted":
            lifted = _parse_day(c.get("lifted_at"))
            if lifted is None:
                err("lifted row needs lifted_at YYYY-MM-DD")
            elif c.get("effective_to") != c.get("lifted_at"):
                err("effective_to must equal lifted_at")
            elif (today - lifted).days > 372:
                err("lifted more than 12 months ago; delete the row")
        if c.get("until"):
            if not DAY.match(str(c.get("until"))):
                err("until must be YYYY-MM-DD")
            elif c.get("effective_to") != c.get("until"):
                err("effective_to must equal until")
        if "needs_reconfirm" in c and not isinstance(c["needs_reconfirm"], bool):
            err("needs_reconfirm must be a boolean")
        if not (c.get("measure_ko") and c.get("source")):
            err("measure_ko and source are required")
    return errors


def main(argv=None):
    catalogue_path = CATALOGUE
    if argv:
        catalogue_path = Path(argv[0])
    doc = load_catalogue(catalogue_path)
    errors = validate_document(doc, load_universe())
    if errors:
        print(f"{len(errors)} problem(s) in {catalogue_path}")
        for line in errors:
            print(f"  {line}")
        return 1
    print(f"ok {len(doc['controls'])} controls")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
