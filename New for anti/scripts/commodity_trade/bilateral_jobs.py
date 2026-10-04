"""Bounded, resumable job engine with an injected acquisition provider.

The provider may later call a protected Worker gateway or a direct API. Neither
credentials nor transport mode belong to job identity or checkpoint contents.
No network, deployment, or scheduling side effects are built into this module.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any, Callable

from bilateral import ContractError, build_partition, validate_meta


def loses_observations(old, new):
    """Omission is not an explicit zero/retraction. Keep last good partition."""
    for flow, block in old['flows'].items():
        current = {r['partner']: r for r in new['flows'][flow]['rows']}
        for row in block['rows']:
            other = current.get(row['partner'])
            if other is None or any(v is not None and other['metrics'][k] is None for k, v in row['metrics'].items()):
                return True
        for metric, info in block['metrics'].items():
            if info['world_total'] is not None and new['flows'][flow]['metrics'][metric]['world_total'] is None:
                return True
    return False


def make_job(meta: dict[str, Any], partners: list[str]) -> dict[str, Any]:
    from bilateral import partner_code
    meta = validate_meta(meta)
    flows = meta.get("requested_flows", ["X", "M"])
    if not isinstance(flows, list) or not flows or any(f not in {"X", "M"} for f in flows):
        raise ContractError("explicit X/M flow scope required")
    meta["requested_flows"] = sorted(set(flows))
    if not isinstance(partners, list) or not partners:
        raise ContractError("explicit partner scope required")
    if partners == ["*"]:
        scope = ["*"]
    else:
        scope = sorted({partner_code(p) for p in partners}, key=int)
        if meta["all_partners_verified"]:
            raise ContractError("a partner subset cannot claim worldwide partner coverage")
    identity = {k: meta[k] for k in ("source", "reporter", "hs", "hs_version", "period", "frequency", "scope_id", "value_basis")}
    identity["partners"] = scope
    identity["requested_flows"] = meta["requested_flows"]
    digest = sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
    return {"id": digest, "meta": meta, "partners": scope}


def execute_plan(
    jobs: list[dict[str, Any]],
    state: dict[str, Any] | None,
    *,
    cycle: str,
    max_requests: int,
    provider: Callable[[dict[str, Any]], dict[str, Any]],
    checkpoint: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    """One provider call per job; checkpoint after every attempt.

    Provider response: query_id, status=ok/empty/rate_limited/auth_required/error,
    response_complete (all requested pages, not worldwide coverage), rows.
    Existing data is replaced only with a nonempty, validated complete response.
    Empty/partial/failing refreshes retain previous observations and record status.
    """
    if not cycle or not isinstance(max_requests, int) or isinstance(max_requests, bool) or max_requests < 0:
        raise ContractError("cycle and nonnegative request budget required")
    result = deepcopy(state) if state is not None else {"schema": "bilateral-checkpoint-v1", "jobs": {}, "data": {}}
    if result.get("schema") != "bilateral-checkpoint-v1":
        raise ContractError("unknown checkpoint schema")
    validated = []
    for job in jobs:
        if make_job(job["meta"], job["partners"])["id"] != job["id"]:
            raise ContractError("job identity mismatch")
        validated.append(job)
    if len({j["id"] for j in validated}) != len(validated):
        raise ContractError("duplicate job")
    # Failed early jobs cannot starve the end of a long plan after a restart.
    pending = [j for j in validated if not (
        result["jobs"].get(j["id"], {}).get("cycle") == cycle
        and result["jobs"][j["id"]].get("status") == "ok"
    )]
    pending.sort(key=lambda j: result["jobs"].get(j["id"], {}).get("attempts", 0)
                 if result["jobs"].get(j["id"], {}).get("cycle") == cycle else 0)
    attempted = 0
    stop_reason = None
    for job in pending[:max_requests]:
        jid = job["id"]
        old = result["jobs"].get(jid, {})
        attempt = (old.get("attempts", 0) if old.get("cycle") == cycle else 0) + 1
        status = "error"
        try:
            response = provider(deepcopy(job))
            if response.get("query_id") != jid:
                raise ContractError("response identity mismatch")
            status = response.get("status")
            if status not in {"ok", "empty", "rate_limited", "auth_required", "network_error", "error"}:
                raise ContractError("unknown acquisition status")
            if status == "ok":
                rows = response.get("rows")
                if not isinstance(rows, list):
                    raise ContractError("rows must be a list")
                if not rows:
                    status = "empty"
                else:
                    from bilateral import partner_code
                    for row in rows:
                        if row.get("flow") not in job["meta"]["requested_flows"]:
                            raise ContractError("response outside requested flow scope")
                        if job["partners"] != ["*"] and partner_code(row.get("partner")) not in job["partners"]:
                            raise ContractError("response outside requested partner scope")
                    partition = build_partition(job["meta"], rows)
                    if response.get("response_complete") is not True:
                        status = "partial"
                    elif job["partners"] != ["0"] and not any(b["rows"] for b in partition["flows"].values()):
                        status = "world_only"
                    elif jid in result["data"] and loses_observations(result["data"][jid], partition):
                        # Even a transport-complete response cannot turn an absent
                        # direction into zero or erase its last good observations.
                        status = "partial"
                    else:
                        partition["meta"]["retrieved_at"] = response.get("retrieved_at")
                        result["data"][jid] = partition
        except ContractError:
            status = "contract_error"
        except Exception:
            # Never serialize exception messages, request URLs or provider bodies:
            # Korea's upstream credential is a URL parameter.
            status = "provider_error"
        entry = {"cycle": cycle, "attempts": attempt, "status": status,
                 "query_meta": deepcopy(job['meta']), "partners": deepcopy(job['partners']),
                 "last_success_cycle": cycle if status == "ok" else old.get("last_success_cycle"),
                 "has_retained_data": jid in result["data"]}
        result["jobs"][jid] = entry
        attempted += 1
        checkpoint(deepcopy(result))  # Persistence failure stops further acquisition.
        if status in {"auth_required", "rate_limited", "network_error"}:
            stop_reason = status
            break
    return {"state": result, "attempted": attempted, "stop_reason": stop_reason,
            "unfinished": [j["id"] for j in validated if not (
                result["jobs"].get(j["id"], {}).get("cycle") == cycle
                and result["jobs"][j["id"]].get("status") == "ok") ]}
