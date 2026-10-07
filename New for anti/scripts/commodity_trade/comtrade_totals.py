"""Select statistical totals explicitly; never choose by row order or maximum."""
import math

SCOPE = {"partner2Code": "0", "customsCode": "C00", "motCode": "0"}


def _code(value):
    text = str(value)
    return str(int(text)) if text.isdigit() else text


def select_totals(rows, *, reporter=None, periods=None, hs_codes=None, flows=None, partner=None):
    grouped = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid Comtrade row")
        if any(k in row and str(row[k]) != v for k, v in SCOPE.items()):
            continue
        if reporter is not None and "reporterCode" in row and _code(row["reporterCode"]) != _code(reporter):
            continue
        if partner is not None and "partnerCode" in row and _code(row["partnerCode"]) != _code(partner):
            continue
        if periods is not None and "period" in row and str(row["period"]) not in periods:
            continue
        if hs_codes is not None and str(row.get("cmdCode")) not in hs_codes:
            continue
        if flows is not None and "flowCode" in row and row["flowCode"] not in flows:
            continue
        for field in ("netWgt", "primaryValue"):
            value = row.get(field)
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                raise ValueError("invalid Comtrade metric")
        key = tuple(str(row.get(k, "")) for k in ("reporterCode", "period", "cmdCode", "flowCode", "partnerCode"))
        previous = grouped.get(key)
        if previous is not None and any(previous.get(k) != row.get(k) for k in ("netWgt", "primaryValue")):
            raise ValueError("conflicting Comtrade totals")
        grouped[key] = row
    return list(grouped.values())
