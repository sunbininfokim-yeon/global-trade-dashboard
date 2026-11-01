"""Evidence-linked funding laws and reviewed, version-specific CBO estimates.

Discovery is a candidate queue, never automatic legal interpretation. A
source failure preserves reviewed facts and makes incomplete coverage visible.
"""
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re

INDEX = "https://www.archives.gov/federal-register/laws/current.html"
REVIEW = Path(__file__).with_name("funding_review.json")


class Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def normalized(raw):
    parser = Text()
    parser.feed(raw.decode("utf-8"))
    return re.sub(r"-\s+(\d)", r"-\1", " ".join(" ".join(parser.parts).split()))


def bill_id(value):
    if not re.fullmatch(r"\d{3}-(?:hr|s|hjres|sjres)-[1-9]\d*", value):
        raise ValueError("Bill identity requires Congress, type and number")
    return value


def verify_measure(profile, raw, checked):
    number = profile["public_law_number"]
    congress, law = number.split("-")
    text = normalized(raw)
    if f"Congress Public Law {law}]" not in text or f"Public Law {number}" not in text:
        raise ValueError("Official law header does not match the reviewed identity")
    if not re.search(rf"\[{congress}(?:st|nd|rd|th) Congress Public Law {law}\]", text):
        raise ValueError("Wrong Congress in law header")
    canonical = bill_id(profile["bill_id"])
    c, kind, n = canonical.split("-")
    labels = {"hr": r"H\.R\.", "s": r"S\.", "hjres": r"H\.J\.\s*Res\.", "sjres": r"S\.J\.\s*Res\."}
    if c != congress or not re.search(rf"\[{labels[kind]}\s*{n}\]", text):
        raise ValueError("Law and bill identities differ")
    if profile["title"] not in text or "Be it enacted" not in text:
        raise ValueError("Reviewed law title unavailable")
    enacted = datetime.strptime(profile["enacted_on"], "%Y-%m-%d").strftime("%B %d, %Y").replace(" 0", " ")
    if f"Approved {enacted}." not in text:
        raise ValueError("Official enactment date differs")
    section = re.search(r"Sec\. 106\.(.*?)Sec\. 107\.", text, re.I)
    if not section or "whichever of the following first occurs" not in section[1]:
        raise ValueError("Continuing-resolution termination rule changed")
    deadline = datetime.strptime(profile["general_deadline"], "%Y-%m-%d").strftime("%B %d, %Y").replace(" 0", " ")
    if deadline not in section[1]:
        raise ValueError("General CR deadline changed")
    base = re.search(r"Sec\. 101\.(.*?)Sec\. 102\.", text, re.I)
    if not base:
        raise ValueError("CR appropriation references unavailable")
    chunks = dict(re.findall(r"\((\d{1,2})\) The (.*?)(?=\(\d{1,2}\) The |$)", base[1]))
    if len(chunks) != len(profile["areas"]):
        raise ValueError("CR funding-area references changed")
    for area in profile["areas"]:
        chunk = chunks.get(str(area["item"]), "")
        if f"Public Law {area['base_law']}" not in chunk:
            raise ValueError("CR base-law reference changed")
        if area["base_division"] and f"division {area['base_division']} of Public Law {area['base_law']}" not in chunk:
            raise ValueError("CR base-law division changed")
    result = dict(profile)
    digest = hashlib.sha256(raw).hexdigest()
    result.update(verification_status="verified" if digest == profile["reviewed_raw_sha256"] else "needs_review",
                  checked_at=checked, source_sha256=digest, current_effect_status="not_determined",
                  current_effect_note="일반 기한은 후속 입법이나 조항별 예외로 달라질 수 있으며 현재 효력 전체를 확정하지 않습니다.")
    return result


def validate_cost(profile):
    bill_id(profile["bill_id"])
    if profile["version_match"] != "related_draft_not_verified_as_enacted":
        raise ValueError("CBO draft must not be promoted to an enacted-law estimate")
    effects = profile["budget_effects"]
    years = effects["years"]
    if not years or years != list(range(years[0], years[-1]+1)):
        raise ValueError("Nonconsecutive CBO fiscal years")
    keys = ["outlays_million", "revenues_million", "deficit_million"]
    if any(len(effects[k]) != len(years) for k in keys):
        raise ValueError("CBO estimate columns differ")
    for out, revenue, deficit in zip(*(effects[k] for k in keys)):
        if Decimal(str(out)) - Decimal(str(revenue)) != Decimal(str(deficit)):
            raise ValueError("CBO deficit effect does not reconcile")
    for total in effects["cumulative"]:
        indices = [i for i, year in enumerate(years) if total["start"] <= year <= total["end"]]
        for key in keys:
            if sum(effects[key][i] for i in indices) != total[key]:
                raise ValueError("CBO cumulative estimate does not reconcile")
    return profile


class IndexTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.row, self.cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr": self.row = []
        if tag in ("td", "th") and self.row is not None: self.cell = []

    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        if tag == "tr" and self.row is not None:
            self.rows.append(self.row)
            self.row = None


def discovery(raw, reviewed):
    parser = IndexTable()
    parser.feed(raw.decode("utf-8"))
    rows = [r for r in parser.rows if len(r) >= 4 and re.fullmatch(r"\d{3}-\d+", r[0])]
    if not rows:
        raise ValueError("Official public-law index layout unavailable")
    # Candidate detection only. Empty candidates never prove no other funding law.
    candidates = []
    for law, number, description, approved, *_ in rows:
        if law in reviewed or not re.search(r"appropriat|continuing resolution", description, re.I):
            continue
        candidates.append(dict(public_law_number=law, bill_reference=number, title=description,
                               date_approved_reference=approved, status="needs_review"))
    return candidates


def collect(get, previous=None, now=None, profile=None):
    checked = now or datetime.now(timezone.utc).isoformat()
    previous = previous or {}
    profile = profile or json.loads(REVIEW.read_text())
    old = {r["public_law_number"]: r for r in previous.get("measures", [])}
    measures = []
    for record in profile["measures"]:
        try:
            measures.append(verify_measure(record, get(record["govinfo_url"]), checked))
        except Exception:
            held = dict(old.get(record["public_law_number"], record))
            held.update(verification_status="source_unavailable", last_attempt_at=checked,
                        current_effect_status="not_determined")
            measures.append(held)
    try:
        raw = get(INDEX)
        reviewed = {r["public_law_number"] for r in measures}
        # A current-session index can drop older unreviewed laws. Keep that
        # review queue until a reviewed profile actually resolves an identity.
        pending = {r["public_law_number"]: dict(r) for r in previous.get("discovery", {}).get("candidates", [])
                   if r["public_law_number"] not in reviewed}
        for candidate in discovery(raw, reviewed):
            old_candidate = pending.get(candidate["public_law_number"], {})
            pending[candidate["public_law_number"]] = dict(candidate,
                first_seen_at=old_candidate.get("first_seen_at", checked), last_seen_at=checked)
        candidates = list(pending.values())
        watch = dict(status="checked", source_url=INDEX, checked_at=checked,
                     response_sha256=hashlib.sha256(raw).hexdigest(), candidates=candidates)
    except Exception:
        watch = dict(previous.get("discovery", {}), status="source_unavailable", source_url=INDEX,
                     last_attempt_at=checked, candidates=previous.get("discovery", {}).get("candidates", []))
    costs = []
    old_costs = {r["id"]: r for r in previous.get("cost_estimates", [])}
    known = {r["public_law_number"]: r["bill_id"] for r in measures}
    for cost in profile["cost_estimates"]:
        validate_cost(cost)
        if known.get(cost["public_law_number"]) != cost["bill_id"]:
            raise ValueError("CBO relation has no matching reviewed law/bill identity")
        record = dict(cost, review_status="reviewed_snapshot", reviewed_on=profile["reviewed_on"])
        # The reviewed text is usable with its own date/version. A blocked direct
        # download is exposed, never presented as a fresh PDF hash verification.
        prior = old_costs.get(cost["id"], {})
        record["direct_fetch_status"] = prior.get("direct_fetch_status", cost.get("direct_fetch_status", "not_checked"))
        record["last_attempt_at"] = prior.get("last_attempt_at")
        if prior.get("latest_download_sha256"):
            record.update(latest_download_sha256=prior["latest_download_sha256"],
                          latest_download_at=prior.get("latest_download_at"))
        due = date.fromisoformat(cost.get("retry_not_before", profile["reviewed_on"]))
        if prior.get("last_attempt_at"):
            due = max(due, datetime.fromisoformat(prior["last_attempt_at"]).date() + timedelta(days=7))
        if datetime.fromisoformat(checked).date() >= due:
            record["last_attempt_at"] = checked
            try:
                raw = get(cost["source_url"])
                if not raw.startswith(b"%PDF"):
                    raise ValueError("CBO source is not a PDF")
                record.update(direct_fetch_status="downloaded_requires_review", latest_download_sha256=hashlib.sha256(raw).hexdigest(),
                              latest_download_at=checked)
            except Exception:
                record["direct_fetch_status"] = "source_unavailable"
        costs.append(record)
    return dict(schema_version=1, coverage="reviewed_subset", scope=profile["scope"], measures=measures,
                discovery=watch, cost_estimates=costs,
                limitations=["관련 법률 목록은 전수 수집이 아닙니다.", "CR 일반 기한은 조항별 예외와 후속 입법 검토가 필요합니다.",
                             "CBO 초안 추정은 확정법 금액·실제 지급액과 구분합니다."])
