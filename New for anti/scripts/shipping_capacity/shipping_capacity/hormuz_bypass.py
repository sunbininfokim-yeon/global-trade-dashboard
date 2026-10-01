"""Hormuz bypass through the Red Sea, and the threat to it.

Saudi crude that avoids Hormuz goes by the East-West pipeline to Yanbu and
leaves the Red Sea north (Suez/SUMED) or south (Bab el-Mandeb). The Houthi
blockade targets Yanbu loadings and that southern exit. This block puts the
free evidence for that route side by side:

- Yanbu tanker activity from IMF PortWatch daily port data (AIS estimates).
- EIA quarterly crude+condensate for Hormuz, Bab el-Mandeb and Suez+SUMED,
  read from official_cargo_monitor (same publisher, frequency, commodity).
- A manual, source-cited log of threat events (config/hormuz_bypass.json),
  with a status that expires if the log is not re-reviewed.

No diverted volume is computed. A Bab el-Mandeb rise is not "Hormuz flow
rerouted", and a Yanbu AIS collapse is not proof that loadings stopped:
tankers in a threatened area switch AIS off.
"""

from __future__ import annotations

import calendar
import copy
import json
import re
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from shipping_capacity.portwatch import PORTWATCH_PORTS_QUERY_URL, _iso_date


CONTRACT_VERSION = "hormuz-bypass-v1"
USER_AGENT = "Chokemonitor/1.0 public-reference-collector"
HISTORY_DAYS = 300
COMPARED_POINTS = (
    ("hormuz", "호르무즈 해협"),
    ("bab_el_mandeb", "바브엘만데브 해협"),
    ("suez", "수에즈+SUMED"),
)
EVIDENCE_LABELS_KO = {"press_report": "보도", "official_statement": "공식 성명"}

Fetcher = Callable[[str], bytes]


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=45) as response:
        if urllib.parse.urlparse(response.geturl()).hostname != urllib.parse.urlparse(url).hostname:
            raise ValueError("PortWatch redirected outside its host")
        body = response.read(8_000_001)
        if len(body) > 8_000_000:
            raise ValueError("PortWatch response exceeds size limit")
        return body


def yanbu_query_url(port_ids: list[str], start: date) -> str:
    if not port_ids or not all(re.fullmatch(r"port\d+", port_id) for port_id in port_ids):
        raise ValueError("PortWatch port ids must look like port123")
    fields = ("portcalls_tanker", "export_tanker", "import_tanker")
    return PORTWATCH_PORTS_QUERY_URL + "?" + urllib.parse.urlencode({
        # Values come from the checked id list above, never from input text.
        "where": "portid IN (" + ",".join(f"'{port_id}'" for port_id in port_ids) + f") AND date >= DATE '{start.isoformat()}'",
        "outStatistics": json.dumps([
            {"statisticType": "sum", "onStatisticField": field, "outStatisticFieldName": field} for field in fields
        ]),
        "groupByFieldsForStatistics": "date",
        "orderByFields": "date DESC",
        "returnGeometry": "false",
        "resultRecordCount": str(HISTORY_DAYS + 10),
        "f": "json",
    })


def parse_yanbu_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if "error" in payload or not isinstance(payload.get("features"), list):
        raise ValueError("PortWatch ports payload error or shape change")
    rows: dict[str, dict[str, Any]] = {}
    for feature in payload["features"]:
        attributes = feature.get("attributes") or {}
        day = _iso_date(attributes.get("date"))
        if not day:
            continue
        values = {field: attributes.get(field) for field in ("portcalls_tanker", "export_tanker", "import_tanker")}
        if any(value is not None and (not isinstance(value, (int, float)) or value < 0) for value in values.values()):
            raise ValueError("invalid PortWatch port value")
        rows[day] = {"date": day, **values}
    if not rows:
        raise ValueError("PortWatch returned no Yanbu rows")
    return [rows[day] for day in sorted(rows)]


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def summarize_yanbu(rows: list[dict[str, Any]], today: date) -> dict[str, Any]:
    by_month: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_month.setdefault(row["date"][:7], []).append(row)
    monthly = [{
        "month": month,
        "days_observed": len(items),
        # PortWatch lags several days, so a past month can still be partial.
        "partial_month": len(items) < calendar.monthrange(int(month[:4]), int(month[5:]))[1],
        "tanker_export_tonnes_per_day": _mean([item["export_tanker"] for item in items if item["export_tanker"] is not None]),
        "tanker_port_calls": sum(item["portcalls_tanker"] or 0 for item in items),
    } for month, items in sorted(by_month.items())]
    exports = [(row["date"], row["export_tanker"]) for row in rows if row["export_tanker"] is not None]
    recent = [value for _, value in exports[-7:]]
    prior = [value for _, value in exports[-35:-7]]
    recent_mean, prior_mean = _mean(recent), _mean(prior)
    change = None
    if recent_mean is not None and prior_mean:
        change = round((recent_mean / prior_mean - 1) * 100, 1)
    return {
        "monthly": monthly,
        "latest_date": rows[-1]["date"] if rows else None,
        "recent_7d_mean_tonnes_per_day": recent_mean if len(recent) == 7 else None,
        "prior_28d_mean_tonnes_per_day": prior_mean if len(prior) == 28 else None,
        "change_pct": change if len(recent) == 7 and len(prior) == 28 else None,
    }


def _event_day(event: dict[str, Any]) -> date:
    if event.get("date_precision") == "month":
        return date.fromisoformat(f"{event['date']}-01")
    return date.fromisoformat(event["date"])


def threat_status(config: dict[str, Any], today: date) -> dict[str, Any]:
    reviewed = date.fromisoformat(config["reviewed_at"])
    days_since_review = (today - reviewed).days
    events = config.get("threat_events", [])
    latest = max((_event_day(event) for event in events), default=None)
    if days_since_review > int(config["review_max_age_days"]):
        # A manual log must not keep asserting a live threat nobody re-checked.
        status = "log_review_stale"
    elif latest and (today - latest).days <= int(config["recent_event_window_days"]):
        status = "recent_events_reported"
    else:
        status = "no_recent_events_in_log"
    return {
        "status": status,
        "reviewed_at": config["reviewed_at"],
        "days_since_review": days_since_review,
        "review_max_age_days": config["review_max_age_days"],
        "recent_event_window_days": config["recent_event_window_days"],
        "latest_event_date": max((event["date"] for event in events), default=None),
        "event_count": len(events),
    }


def official_crude_comparison(official_cargo: dict[str, Any] | None) -> dict[str, Any]:
    points = (official_cargo or {}).get("chokepoints") or {}
    series = []
    for point_id, label in COMPARED_POINTS:
        rows = [row for row in (points.get(point_id) or {}).get("reported_series", [])
                if row.get("publisher") == "EIA" and row.get("frequency") == "quarterly"
                and row.get("cargo_category") == "crude_condensate" and row.get("unit") == "barrels_per_day"]
        series.append({
            "chokepoint_id": point_id,
            "label_ko": label,
            "geography_scope": rows[0]["geography_scope"] if rows else None,
            "points": [{"period": row["period"], "period_start": row["period_start"], "value": row["value"]}
                       for row in sorted(rows, key=lambda row: row["period_start"])],
        })
    return {
        "publisher": "EIA",
        "frequency": "quarterly",
        "cargo_category": "crude_condensate",
        "unit": "barrels_per_day",
        "series": series,
        "diverted_volume": None,
        "warning_ko": "같은 기관·분기·품목이라 나란히 놓았다. 바브엘만데브 증가분을 호르무즈에서 옮겨 온 물량으로 계산하지 않는다(다른 산지·목적지 화물이 섞인다).",
    }


def collect_hormuz_bypass(
    config_dir: Path, *, fetch: bool = False, previous: dict[str, Any] | None = None,
    now: datetime | None = None, fetcher: Fetcher = fetch_bytes,
    official_cargo: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    timestamp = now.isoformat()
    config = json.loads((config_dir / "hormuz_bypass.json").read_text(encoding="utf-8"))
    port_ids = [port["portid"] for port in config["yanbu_ports"]]
    source = copy.deepcopy(((previous or {}).get("sources") or {}).get("portwatch_ports", {}))
    source.update({
        "source_url": PORTWATCH_PORTS_QUERY_URL, "publisher": "IMF PortWatch (Daily Ports Data)",
        "api_key_required": False, "last_attempt_at": timestamp if fetch else source.get("last_attempt_at"),
    })
    if fetch:
        try:
            url = yanbu_query_url(port_ids, now.date() - timedelta(days=HISTORY_DAYS))
            rows = parse_yanbu_rows(json.loads(fetcher(url).decode("utf-8")))
            source.update({"rows": rows, "status": "fetched", "retrieved_at": timestamp, "error_code": None})
        except Exception as exc:  # noqa: BLE001 -- keep the last good copy
            source.update({"status": "cached_fallback" if source.get("rows") else "unavailable", "error_code": type(exc).__name__})
    else:
        source["status"] = "cached_offline" if source.get("retrieved_at") else "not_fetched"
    source.setdefault("rows", [])
    yanbu = summarize_yanbu(source["rows"], now.date()) if source["rows"] else {
        "monthly": [], "latest_date": None, "recent_7d_mean_tonnes_per_day": None,
        "prior_28d_mean_tonnes_per_day": None, "change_pct": None,
    }
    events = sorted(copy.deepcopy(config["threat_events"]), key=_event_day)
    for event in events:
        event["evidence_label_ko"] = EVIDENCE_LABELS_KO[event["evidence_class"]]
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": timestamp,
        "status": "available" if source["status"] == "fetched" else "cached" if source.get("retrieved_at") else "unavailable",
        "api_keys_required": [],
        "route": copy.deepcopy(config["route"]),
        "threat": {**threat_status(config, now.date()), "events": events},
        "yanbu_port_activity": {
            "status": "available" if yanbu["monthly"] else "unavailable",
            "ports": copy.deepcopy(config["yanbu_ports"]),
            "unit": "estimated_tanker_export_tonnes_per_day",
            **yanbu,
            "warning_ko": "PortWatch AIS 기반 탱커 화물 추정(톤)이며 원유 배럴이 아니다. 위협 해역에서는 탱커가 AIS를 끄는 경우가 많아, 0에 가까운 값이 실제 선적 중단을 뜻한다고 단정할 수 없다.",
        },
        "official_crude_comparison": official_crude_comparison(official_cargo),
        "sources": {"portwatch_ports": source},
    }
