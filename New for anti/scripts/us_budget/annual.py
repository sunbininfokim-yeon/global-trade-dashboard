"""Regenerate annual OMB history/proposal from official linked XLSX files.

The reviewed snapshot is a fallback, never an input to new monetary amounts.
New layouts, absent values and inconsistent vintages fail closed.
"""
from collections import defaultdict
from decimal import Decimal
from html.parser import HTMLParser
from io import BytesIO
import hashlib
import re
from urllib.parse import urljoin, urlparse

import openpyxl

PAGES = ["https://www.whitehouse.gov/omb/information-resources/budget/historical-tables/",
         "https://www.whitehouse.gov/omb/information-resources/budget/supplemental-materials/"]
PATTERNS = {"summary": "hist01z1", "receipts": "hist02z1", "types": "hist08z1",
            "mandatory": "hist08z5", "discretionary": "hist08z7", "accounts": "outlays"}
MILLION = Decimal(1000000)
THOUSAND = Decimal(1000)


class AnnualError(ValueError):
    pass


def money(value, scale=MILLION):
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise AnnualError(f"Missing or nonnumeric OMB amount: {value!r}")
    value = Decimal(str(value))
    if not value.is_finite():
        raise AnnualError("Nonfinite OMB amount")
    return value * scale


def close(a, b, tolerance=Decimal("0.01")):
    if abs(a - b) > tolerance:
        raise AnnualError(f"OMB reconciliation failed: {a} != {b}")


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self.links.extend(v for k, v in attrs if k == "href" and v)


def discover(get):
    found = defaultdict(dict)
    for page in PAGES:
        parser = Links()
        parser.feed(get(page).decode("utf-8"))
        for href in parser.links:
            url = urljoin(page, href)
            parts = urlparse(url)
            if parts.scheme != "https" or parts.hostname != "www.whitehouse.gov":
                continue
            for key, prefix in PATTERNS.items():
                match = re.fullmatch(r"/wp-content/uploads/(\d{4}/\d{2})/" + prefix + r"_fy(\d{4})\.xlsx", parts.path)
                if match:
                    publication, fy = match.groups()
                    group = found[(int(fy), publication)]
                    if key in group and group[key] != url:
                        raise AnnualError("Ambiguous official workbook link")
                    group[key] = url
    if not found:
        raise AnnualError("No official OMB workbook links found")
    # Never fall back silently to an older complete FY if the newest is partial.
    fy, publication = max(found)
    urls = found[(fy, publication)]
    if set(urls) != set(PATTERNS):
        raise AnnualError("Newest OMB publication has an incomplete workbook set")
    return dict(proposal_fy=fy, publication=publication, urls=urls)


def load(manifest, get):
    tables, sources = {}, []
    for key, url in manifest["urls"].items():
        raw = get(url)
        book = openpyxl.load_workbook(BytesIO(raw), data_only=True, read_only=False)
        tables[key] = list(book.active.values)
        sources.append(dict(id=key, url=url, sha256=hashlib.sha256(raw).hexdigest(),
                            original_unit="thousand USD" if key == "accounts" else "billion USD" if key == "types" else "million USD"))
        book.close()
    return tables, sources


def dated_rows(rows):
    out = {}
    for row in rows:
        match = re.fullmatch(r"(\d{4})( estimate)?", str(row[0]).strip())
        if match:
            fy, estimate = match.groups()
            if int(fy) in out:
                raise AnnualError("Duplicate OMB fiscal-year row")
            out[int(fy)] = (row, bool(estimate))
    return out


def column(rows, fy, estimate):
    matches = [i for i, name in enumerate(rows[2]) if str(name).strip() == f"{fy}{' estimate' if estimate else ''}"]
    if len(matches) != 1:
        raise AnnualError(f"OMB FY{fy} {'estimate' if estimate else 'actual'} column unavailable")
    return matches[0]


def row_at(rows, index, expected):
    if rows[index][0] != expected:
        raise AnnualError(f"OMB layout changed at {expected!r}")
    return rows[index]


# Indices are guarded by source labels; totals are checked against the PBD.
DISC = [(6, "Total national defense", "국방", [4, 5]), (8, "International affairs", "국제관계", []),
        (12, "Total general science, space and technology", "과학·우주·기술", [10, 11]),
        (13, "Energy", "에너지", []), (14, "Natural resources and environment", "자연자원·환경", []),
        (15, "Agriculture", "농업", []), (16, "Commerce and housing credit", "상업·주택 신용", []),
        (21, "Total transportation", "교통", [18, 19, 20]), (22, "Community and regional development", "지역개발", []),
        (26, "Total education, training, employment and social services", "교육·훈련·고용·사회서비스", [24, 25]),
        (27, "Health", "보건", []), (28, "Medicare", "Medicare · 재량분", []),
        (32, "Total income security", "소득보장", [30, 31]), (33, "Social security", "Social Security · 재량분", []),
        (34, "Veterans benefits and services", "보훈 급여·서비스", []), (35, "Administration of justice", "사법·법집행", []),
        (36, "General government", "일반행정", []), (37, "Allowances", "계획 조정액 · Allowances", [])]
MANDATORY = [(5, "Education, training, employment, and social services", "교육·훈련·고용·사회서비스", []),
             (12, "Total health", "보건 · Medicaid 등", list(range(7, 12))), (13, "Medicare", "Medicare", []),
             (26, "Total income security", "소득보장", list(range(15, 26))), (27, "Social Security", "Social Security", []),
             (31, "Total veterans benefits and services", "보훈 급여·서비스", [29, 30]),
             (47, "Total other mandatory programs", "기타 의무지출", [34, 35, 36, 37, 38, 39, 40, 41, 42, 44, 45, 46])]


def tree_check(node):
    if node["children"]:
        for key in ("value", "prior"):
            close(sum(c[key] for c in node["children"]), node[key])
        for child in node["children"]:
            tree_check(child)


def node(key, name, children):
    return dict(id=key, name=name, children=children,
                value=sum((c["value"] for c in children), Decimal(0)),
                prior=sum((c["prior"] for c in children), Decimal(0)))


def receipt_groups(rows):
    """Keep the annual five-category taxonomy stable across OMB and MTS."""
    names = {"Individual Income Taxes": ("0", "개인소득세"),
             "Social Insurance and Retirement Receipts:": ("1", "사회보험·퇴직 부담금"),
             "Corporation Income Taxes": ("2", "법인세"), "Excise Taxes": ("3", "소비세"),
             "Estate and Gift Taxes": ("4", "기타 세입 · 관세·상속세 등"),
             "Customs Duties": ("4", "기타 세입 · 관세·상속세 등"),
             "Miscellaneous Receipts": ("4", "기타 세입 · 관세·상속세 등")}
    if {r["name"] for r in rows} != set(names):
        raise AnnualError("Treasury receipt taxonomy changed")
    grouped = {}
    for row in rows:
        key, label = names[row["name"]]
        entry = grouped.setdefault(key, dict(id=key, name=label, value=Decimal(0)))
        entry["value"] += money(row["value"], Decimal(1))
    return [grouped[key] for key in sorted(grouped)]


AGENCY_NAMES = {"001": "입법부", "002": "사법부", "005": "농무부 USDA", "006": "상무부",
                "007": "국방부 군사사업", "009": "보건복지부 HHS", "010": "내무부", "011": "법무부",
                "012": "노동부", "014": "국무부", "015": "재무부", "016": "사회보장청 SSA", "017": "사회보장청 SSA",
                "018": "교육부", "019": "에너지부 DOE", "020": "환경보호청 EPA", "021": "교통부",
                "023": "총무청 GSA", "024": "국토안보부", "025": "주택도시개발부 HUD", "026": "항공우주국 NASA",
                "027": "인사관리처", "028": "중소기업청 SBA", "029": "보훈부 VA", "100": "대통령실",
                "184": "국제원조 사업", "200": "기타 국방 민간사업", "202": "육군 공병대 민간사업",
                "900": "계획 조정액", "902": "공통 차감 수입", "930": "보고 기준 미만 기타 수입"}


def agency_accounts(rows, fy, estimate):
    """Agency/bureau/account trees, separately for each BEA category.

    Agency codes, not names, define identity. These are outlays, not enacted BA.
    """
    header = rows[0]
    fields = ["Agency Code", "Agency Name", "Bureau Code", "Bureau Name", "Account Code", "Account Name", "Treasury Agency Code", "CGAC Agency Code", "BEA Category", str(fy), str(fy-1)]
    if any(header.count(k) != 1 for k in fields):
        raise AnnualError("OMB agency/account headers changed")
    ix = {k: header.index(k) for k in fields}
    kinds = {"Discretionary": "discretionary", "Mandatory": "mandatory", "Net interest": "interest"}
    groups, totals = {}, {k: Decimal(0) for k in kinds.values()}
    for row in rows[1:]:
        category = kinds.get(row[ix["BEA Category"]])
        if category is None:
            raise AnnualError("Unknown agency BEA category")
        value, prior = money(row[ix[str(fy)]], THOUSAND), money(row[ix[str(fy-1)]], THOUSAND)
        totals[category] += value
        if not value and not prior:
            continue
        ac, an, bc, bn, code, name = [str(row[ix[k]]) for k in fields[:6]]
        treasury_code, cgac = str(row[ix["Treasury Agency Code"]]), str(row[ix["CGAC Agency Code"]])
        key = (category, ac, bc, code, treasury_code, cgac)
        entry = groups.setdefault(key, dict(name=name, agency_name=an, bureau_name=bn, value=Decimal(0), prior=Decimal(0)))
        if (entry["name"], entry["agency_name"], entry["bureau_name"]) != (name, an, bn):
            raise AnnualError("Conflicting names for an agency/bureau/account key")
        entry["value"] += value
        entry["prior"] += prior
    trees = {}
    for category in kinds.values():
        agencies = {}
        for (kind, ac, bc, code, treasury_code, cgac), item in groups.items():
            if kind != category:
                continue
            agency = agencies.setdefault(ac, dict(name=item["agency_name"], bureaus={}))
            bureau = agency["bureaus"].setdefault(bc, dict(name=item["bureau_name"], accounts=[]))
            bureau["accounts"].append(dict(id=f"{category}-{ac}-{bc}-{treasury_code}-{cgac}-{code}", name=item["name"], code=code,
                                             treasury_agency_code=treasury_code, cgac_agency_code=cgac,
                                             value=item["value"], prior=item["prior"], children=[]))
        roots = []
        for ac, agency in agencies.items():
            bureaus = [node(f"{category}-{ac}-{bc}", bureau["name"], bureau["accounts"])
                       for bc, bureau in agency["bureaus"].items()]
            root = node(f"agency-{ac}-{category}", AGENCY_NAMES.get(ac, agency["name"]), bureaus)
            root.update(code=ac, source_name=agency["name"])
            tree_check(root)
            roots.append(root)
        close(sum((r["value"] for r in roots), Decimal(0)), totals[category])
        trees[category] = roots
    return dict(fy=fy, status="proposal_estimate" if estimate else "actual", metric="outlays",
                baseline_fy=fy-1, baseline_status="estimate" if estimate else "actual", totals=totals, **trees)


def accounts(rows, fy):
    header = rows[0]
    required = ["Agency Code", "Bureau Code", "Account Code", "Account Name", "Bureau Name", "Subfunction Code", "BEA Category", str(fy), str(fy-1)]
    if any(header.count(k) != 1 for k in required):
        raise AnnualError("OMB account headers changed")
    ix = {k: header.index(k) for k in required}
    sums, groups = defaultdict(Decimal), defaultdict(list)
    for row in rows[1:]:
        value = money(row[ix[str(fy)]], THOUSAND)
        prior = money(row[ix[str(fy-1)]], THOUSAND)
        category, sub = row[ix["BEA Category"]], row[ix["Subfunction Code"]]
        if category not in ("Mandatory", "Discretionary", "Net interest"):
            raise AnnualError("Unknown OMB BEA category")
        sums[category] += value
        if category == "Discretionary" and sub in ("051", "053", "054"):
            key = tuple(str(row[ix[k]]) for k in ("Agency Code", "Bureau Code", "Bureau Name"))
            groups[(sub, key)].append((row, value, prior))

    def bureaus(sub):
        result = []
        for (code, key), data in groups.items():
            if code != sub:
                continue
            by_account = {}
            for row, value, prior in data:
                account = str(row[ix["Account Code"]])
                identity = "-".join([key[0], key[1], account])
                entry = by_account.setdefault(identity, dict(id=identity, name=row[ix["Account Name"]], code=account,
                                                             value=Decimal(0), prior=Decimal(0), children=[]))
                if entry["name"] != row[ix["Account Name"]]:
                    raise AnnualError("Conflicting names for an OMB account code")
                entry["value"] += value
                entry["prior"] += prior
            children = [r for r in by_account.values() if r["value"] or r["prior"]]
            if children:
                result.append(node("-".join(key[:2]), key[2], children))
        return result
    defense = [node("military-051", "국방부 군사사업 (051)", bureaus("051")),
               node("other-defense", "기타 국방", [node("sub-053", "핵무기·원자력 국방 활동 (053)", bureaus("053")),
                                                        node("sub-054", "기타 국방 관련 활동 (054)", bureaus("054"))])]
    return sums, defense


def programs(rows, specs, fy, estimate):
    ci, pi = column(rows, fy, estimate), column(rows, fy-1, estimate if estimate else False)
    result = []
    for index, label, ko, children in specs:
        row = row_at(rows, index, label)
        # A printed dotted allowance is not a numeric observation; omit it and
        # require the remaining items to reconcile to the published total.
        if label == "Allowances" and not isinstance(row[ci], (int, float)):
            continue
        child_rows = [dict(id=f"{index}-{k}", name=rows[k][0], value=money(rows[k][ci]),
                           prior=money(rows[k][pi]), children=[]) for k in children]
        result.append(dict(id=str(index+1), name=ko, value=money(row[ci]), prior=money(row[pi]), children=child_rows))
    return result


def build(tables, manifest, sources, completed, monthly):
    fy = manifest["proposal_fy"]
    publication = manifest["publication"]
    # Reject changed units and shifted table types before reading monetary cells.
    for key, prefix in [("summary", "Table 1.1"), ("receipts", "Table 2.1"), ("types", "Table 8.1"),
                        ("mandatory", "Table 8.5"), ("discretionary", "Table 8.7")]:
        if not str(tables[key][0][0]).startswith(prefix):
            raise AnnualError("Wrong OMB table")
        unit = "billions" if key == "types" else "millions"
        if unit not in str(tables[key][1][0]):
            raise AnnualError("OMB units changed")
    summaries = dated_rows(tables["summary"])
    receipts = dated_rows(tables["receipts"])
    types = dated_rows(tables["types"])
    actual_end = max(y for y, (_, estimate) in summaries.items() if not estimate)
    complete = completed["fiscal_ytd"]
    if not complete["complete_fy"]:
        raise AnnualError("Annual MTS supplement is not a complete fiscal year")
    last = max(actual_end, complete["fy"])
    budget = dict(years={}, receipts={}, types={}, discretionary={}, monthly=monthly)
    defense, agency_details = {}, {}
    for year in range(last-4, last+1):
        key = str(year)
        if year in summaries and not summaries[year][1]:
            row, _ = summaries[year]
            rec, out = money(row[1]), money(row[2])
            close(out-rec, -money(row[3]))
            budget["years"][key] = dict(fy=year, receipts=rec, outlays=out, deficit=out-rec,
                                         source=f"OMB FY{fy} 결산 실적 · {publication}", status="actual", vintage=publication)
        elif year == complete["fy"]:
            budget["years"][key] = {k: complete[k] for k in ("fy", "receipts", "outlays", "deficit")}
            budget["years"][key].update(source=f"Treasury MTS FY{year} 결산 실적", status="actual", vintage=completed["publication_date"])
        else:
            raise AnnualError(f"Missing completed FY{year}")
        if year in receipts and not receipts[year][1]:
            row, _ = receipts[year]
            budget["receipts"][key] = [dict(id=str(i), name=name, value=money(row[c])) for i, (c, name) in enumerate([
                (1, "개인소득세"), (3, "사회보험·퇴직 부담금"), (2, "법인세"), (6, "소비세"), (7, "기타 세입 · 관세·상속세 등")])]
            close(sum(r["value"] for r in budget["receipts"][key]), budget["years"][key]["receipts"], MILLION)
        elif year == complete["fy"]:
            budget["receipts"][key] = receipt_groups(complete["receipts_by_category"])
        if year in types and not types[year][1]:
            row, _ = types[year]
            fields = {"total": 1, "discretionary": 2, "defense": 3, "nondefense": 4, "mandatory": 6,
                      "socialSecurity": 8, "medicare": 9, "medicaid": 10, "meansTested": 11,
                      "otherMandatory": 12, "offsets": 13, "interest": 14}
            budget["types"][key] = {k: money(row[c], Decimal(10)**9) for k, c in fields.items()}
            sums, detail = accounts(tables["accounts"], year)
            disc = programs(tables["discretionary"], DISC, year, False)
            close(sum(r["value"] for r in disc), sums["Discretionary"])
            close(sum(r["value"] for r in detail), disc[0]["value"])
            budget["years"][key]["discretionaryExact"] = sums["Discretionary"]
            budget["discretionary"][key] = disc
            defense[key] = detail
            agency_details[key] = agency_accounts(tables["accounts"], year, False)
            for item in disc + detail:
                tree_check(item)
    budget[f"finance{complete['fy']}"] = complete["finance"]
    sums, detail = accounts(tables["accounts"], fy)
    agency_details[str(fy)] = agency_accounts(tables["accounts"], fy, True)
    disc = programs(tables["discretionary"], DISC, fy, True)
    mandatory = programs(tables["mandatory"], MANDATORY, fy, True)
    row, estimate = receipts[fy]
    if not estimate or not receipts[fy-1][1]:
        raise AnnualError("Proposal baseline is not a same-publication estimate")
    rec = money(row[8])
    out = sum(sums.values())
    disc[0]["children"] = detail
    mi, mpi = column(tables["mandatory"], fy, True), column(tables["mandatory"], fy-1, True)
    interest = [dict(id="interest", name="순이자", value=sums["Net interest"], prior=money(tables["mandatory"][55][mpi]),
                     children=[dict(id=f"int-{k}", name=tables["mandatory"][k][0], value=money(tables["mandatory"][k][mi]),
                                    prior=money(tables["mandatory"][k][mpi]), children=[]) for k in (50, 52, 53, 54)])]
    close(sum(r["value"] for r in disc), sums["Discretionary"])
    close(sum(r["value"] for r in mandatory), sums["Mandatory"])
    for item in disc + mandatory + interest:
        tree_check(item)
    proposal = dict(year=dict(fy=fy, receipts=rec, outlays=out, deficit=out-rec, estimate=True,
                             source=f"정부 예산안 · {publication} 제출본 추정 · 의회 최종 확정액 아님", status="proposal_estimate"),
                    receipts=[dict(id=str(i), name=name, value=money(row[c])) for i, (c, name) in enumerate([
                        (1, "개인소득세"), (3, "사회보험·퇴직 부담금"), (2, "법인세"), (6, "소비세"), (7, "기타 세입 · 관세·상속세 등")])],
                    types=dict(total=out, discretionary=sums["Discretionary"], mandatory=sums["Mandatory"], interest=sums["Net interest"]),
                    discretionary=disc, mandatory=mandatory, interest=interest,
                    baseline=f"FY{fy-1} 정부 추정 → FY{fy} 정부안 · 같은 {publication} 발표본")
    close(sum(r["value"] for r in proposal["receipts"]), rec)
    return dict(schema_version=2, normalized_unit="USD", publication=publication, proposal_fy=fy,
                budget=budget, defense=defense, proposal=proposal, sources=sources, agency_details=agency_details,
                enacted_budget=dict(status="not_collected", amount=None, metric="budget_authority",
                                    note="의회 확정 예산권한은 별도 공식 근거가 필요하며 지출 추정치로 채우지 않습니다."))
