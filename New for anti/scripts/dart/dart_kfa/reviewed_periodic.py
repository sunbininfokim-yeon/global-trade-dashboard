"""Validate reviewed KRX KIND and DART periodic report locators."""
from datetime import date
import re
from urllib.parse import parse_qs, urlsplit


REPORT_WINDOWS = {"11011": "annual", "11013": "first_quarter", "11012": "half_year_ytd", "11014": "nine_month_ytd"}


def reviewed_periodic_source(source, as_of):
    url = urlsplit(source["url"])
    filing, form, filed = source["filing_id"], source["form"], source["filed"]
    filed_date = date.fromisoformat(filed)
    if (url.scheme != "https" or url.fragment or filed_date < date.fromisoformat(as_of)
            or not re.fullmatch(r"[0-9]{14}", filing) or not filing.startswith(filed_date.strftime("%Y%m%d"))
            or form not in REPORT_WINDOWS):
        raise ValueError("invalid:reviewed_periodic_filing")
    if source["provider"] == "KRX_KIND":
        if (url.netloc != "kind.krx.co.kr" or url.query
                or not re.fullmatch(rf"/external/{filed.replace('-', '/')}/[0-9]{{6}}/{filing}/{form}\.htm", url.path)):
            raise ValueError("invalid:reviewed_kind_periodic_filing")
    elif source["provider"] == "DART":
        query = parse_qs(url.query, keep_blank_values=True)
        numeric = {"dcmNo", "eleId", "offset", "length"}
        if (url.netloc != "dart.fss.or.kr" or url.path != "/report/viewer.do" or set(query) != numeric | {"rcpNo", "dtd"}
                or query["rcpNo"] != [filing] or query["dtd"] != ["dart4.xsd"]
                or any(len(query[k]) != 1 or not re.fullmatch(r"[0-9]{1,10}", query[k][0]) for k in numeric)):
            raise ValueError("invalid:reviewed_dart_periodic_filing")
    else:
        raise ValueError("invalid:reviewed_periodic_provider")
    return dict(source)
