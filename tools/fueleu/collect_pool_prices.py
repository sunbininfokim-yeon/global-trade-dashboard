"""FuelEU pooling price history from OceanScore's public monthly OPX commentary.

There is no exchange or official price for FuelEU compliance surplus; it moves
in bilateral pooling deals. The only key-free series found is the OceanScore
Pool-Price Index (OPX), published once a month as a prose commentary. This
reads those pages and pulls out the headline index, the observed offer range
and any prior-month value the text restates, keeping the sentence each number
came from.

OceanScore's terms restrict redistributing information from its products, and
whether that covers the public commentary is unconfirmed. Output therefore goes
to source_data/ (git-ignored). Do not commit it or publish it on the site
until that is settled.

Run: python3 collect_pool_prices.py            # fetch and write source_data/
     python3 collect_pool_prices.py --offline  # re-parse saved pages only
"""
import argparse
import hashlib
import html
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "source_data"
PAGE_URL = "https://oceanscore.com/insights/oceanscore-pool-price-index-market-commentary-{slug}/"
INDEX_URL = "https://oceanscore.com/pool-price-index/"
FIRST_MONTH = (2025, 7)  # OPX launched in summer 2025
MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]
# The 2025 compliance cycle closed with the pooling deadline at the end of
# April 2026; from May 2026 the headline tracks 2026 surplus.
CYCLE_SWITCH = date(2026, 5, 1)

EUR = r"€\s?(\d{2,4}(?:[.,]\d{1,2})?)"
UNIT = r"(?:\s*(?:/|per)\s*(?:ton(?:ne)?\s+of\s+)?t?\s?CO₂e|\s*/\s*tCO₂e)?"


def number(text):
    return float(text.replace(",", "."))


def plain_text(raw):
    raw = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw))).strip()


def article_body(raw):
    """Commentary text only: after the byline, before the share footer."""
    text = plain_text(raw)
    start = text.find("Posted on")
    if start < 0:
        raise ValueError("byline not found")
    end = text.find("Share this post", start)
    return text[start:end if end > 0 else len(text)]


def published(raw):
    m = re.search(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})', raw)
    if m:
        return m.group(1)
    m = re.search(r"Posted on (\w+ \d{1,2}, \d{4})", plain_text(raw))
    return datetime.strptime(m.group(1), "%B %d, %Y").date().isoformat() if m else None


def sentences(body):
    # Split on sentence ends, but not inside decimals such as €95.80.
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+(?=[A-Z])", body) if s.strip()]


YEAR_RE = re.compile(r"(20\d\d)\s+(?:compliance\s+)?(?:surplus|compliance balance|cycle)|compliance balances?\s+(20\d\d)", re.I)


def stated_year(sentence, at):
    """The compliance year written closest before position `at`.

    Pages open with a table of contents ("... Spillover Effects Into 2026
    Surplus ... OPX for Compliance Balance 2025 dropped to €200"), so the
    nearest mention, not the first, is the one that labels the number.
    """
    before = [m for m in YEAR_RE.finditer(sentence) if m.start() < at]
    m = before[-1] if before else next(YEAR_RE.finditer(sentence), None)
    return int(m.group(1) or m.group(2)) if m else None


def is_headline_value(sentence, v, month):
    """False for 'down from €X', range bounds and values tied to another month."""
    before, after = sentence[:v.start()], sentence[v.end():]
    if re.search(r"from\s*$", before):
        return False
    if re.search(r"(?:rang\w*|between)[^€]{0,40}$", before) or re.match(r"\s*(?:/\s*tCO₂e)?\s*(?:to|–|-|and)\s*€", after):
        return False
    other = re.match(r"[^.€]{0,30}?\bin\s+(" + "|".join(MONTHS) + r")\b", after, re.I)
    return not (other and other.group(1).lower() != MONTHS[month - 1])


def month_of(slug):
    name, year = slug.rsplit("-", 1)
    return int(year), MONTHS.index(name) + 1


def previous_month(year, month):
    return (year - 1, 12) if month == 1 else (year, month - 1)


def parse_page(raw, slug):
    """Return observations for one commentary page.

    headline: the month's index value. prior_month: a value the text restates
    for the previous month ("down from €X in May"), used only to fill months
    whose own page is missing.
    """
    year, month = month_of(slug)
    body = article_body(raw)
    pub = published(raw)
    default_cycle = 2025 if date(year, month, 1) < CYCLE_SWITCH else 2026
    found = []
    offer = None
    for s in sentences(body):
        if offer is None:
            r = re.search(r"(?:rang\w*|between)[^.]*?" + EUR + r"\s*(?:/\s*tCO₂e)?\s*(?:to|–|-|and)\s*" + EUR, s)
            if r:
                offer = (number(r.group(1)), number(r.group(2)))
        if not re.search(r"\bOPX\b|Pool-Price Index|\bindex\b", s):
            continue
        values = list(re.finditer(EUR + UNIT, s))
        if not values:
            continue
        head = next((v for v in values if is_headline_value(s, v, month)), None)
        cycle = stated_year(s, head.start() if head else values[0].start())
        if head is not None:
            found.append({"kind": "headline", "year": year, "month": month,
                          "compliance_year": cycle or default_cycle,
                          "compliance_year_basis": "stated" if cycle else "inferred_by_cycle",
                          "value_eur_per_tco2e": number(head.group(1)), "evidence": s[:400]})
        for v in values:
            prior = re.match(r"\s*in\s+(" + "|".join(MONTHS) + r")\b", s[v.end():], re.I)
            if re.search(r"from\s*$", s[:v.start()]) and prior:
                py, pm = previous_month(year, month)
                if MONTHS[pm - 1] == prior.group(1).lower():
                    found.append({"kind": "prior_month", "year": py, "month": pm,
                                  "compliance_year": cycle or (2025 if date(py, pm, 1) < CYCLE_SWITCH else 2026),
                                  "compliance_year_basis": "stated" if cycle else "inferred_by_cycle",
                                  "value_eur_per_tco2e": number(v.group(1)), "evidence": s[:400]})
    # A page can restate its own headline ("hit a new low of €193"); keep the first per cycle.
    seen, out = set(), []
    for o in found:
        key = (o["kind"], o["year"], o["month"], o["compliance_year"])
        if key not in seen:
            seen.add(key)
            out.append(o)
    for o in out:
        o.update({"source_slug": slug, "source_url": PAGE_URL.format(slug=slug), "published": pub})
        if o["kind"] == "headline" and offer and o["compliance_year"] == default_cycle:
            o["offer_low_eur"], o["offer_high_eur"] = offer
    if not any(o["kind"] == "headline" for o in out):
        raise ValueError(f"{slug}: no OPX headline found")
    return out


def build_series(observations):
    """One point per (month, compliance year): the month's own page wins over a restatement."""
    best = {}
    for o in observations:
        key = (o["year"], o["month"], o["compliance_year"])
        if key not in best or (best[key]["kind"] == "prior_month" and o["kind"] == "headline"):
            best[key] = o
    series = {}
    for (y, m, cy), o in sorted(best.items()):
        series.setdefault(str(cy), []).append({
            "month": f"{y}-{m:02d}", "value_eur_per_tco2e": o["value_eur_per_tco2e"],
            "offer_low_eur": o.get("offer_low_eur"), "offer_high_eur": o.get("offer_high_eur"),
            "basis": "monthly_commentary" if o["kind"] == "headline" else "restated_in_next_commentary",
            "compliance_year_basis": o["compliance_year_basis"],
            "source_url": o["source_url"], "published": o["published"]})
    return series


def fetch(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (research; global-trade-dashboard)"})
    with urlopen(req, timeout=30) as res:
        return res.read()


def slugs_until(today):
    y, m = FIRST_MONTH
    while (y, m) <= (today.year, today.month):
        yield f"{MONTHS[m - 1]}-{y}"
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def latest_topbar(raw):
    """The site header shows the current OPX, e.g. 'OPX (2026) €95,80'."""
    m = re.search(r"OPX \((20\d\d)\)\s*€\s?(\d{2,4}(?:[.,]\d{1,2})?)", plain_text(raw))
    return {"compliance_year": int(m.group(1)), "value_eur_per_tco2e": number(m.group(2))} if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="re-parse pages already in source_data/pages")
    args = ap.parse_args()
    pages = OUT / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    today = date.today()
    observations, missing, failed, receipts = [], [], [], []
    for slug in slugs_until(today):
        path = pages / f"{slug}.html"
        if not args.offline:
            try:
                path.write_bytes(fetch(PAGE_URL.format(slug=slug)))
            except HTTPError as exc:
                if exc.code != 404:
                    raise
                missing.append(slug)
                continue
            time.sleep(1)
        if not path.exists():
            missing.append(slug)
            continue
        raw = path.read_bytes()
        receipts.append({"slug": slug, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
        try:
            observations += parse_page(raw.decode("utf-8"), slug)
        except ValueError as exc:
            failed.append(str(exc))
    topbar = None
    if not args.offline:
        idx = fetch(INDEX_URL)
        (pages / "pool-price-index.html").write_bytes(idx)
        topbar = latest_topbar(idx.decode("utf-8"))
    result = {"schema": "fueleu_pool_prices_v1",
              "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "source": "OceanScore Pool-Price Index (OPX), public monthly commentary",
              "source_index_url": INDEX_URL,
              "price_type": "index_of_public_offers", "unit": "EUR/tCO2e",
              "redistribution": "unconfirmed_do_not_publish",
              "note": "Offer-based index, not executed trades. No official FuelEU surplus price exists.",
              "series": build_series(observations), "latest_topbar": topbar,
              "observations": observations, "missing_pages": missing,
              "parse_failures": failed, "receipts": receipts}
    (OUT / "pool_prices.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    for cy, points in result["series"].items():
        print(f"CB{cy}: " + ", ".join(f"{p['month']} €{p['value_eur_per_tco2e']:g}" for p in points))
    print(f"missing pages: {missing or 'none'}; parse failures: {failed or 'none'}; topbar: {topbar}")


if __name__ == "__main__":
    main()
