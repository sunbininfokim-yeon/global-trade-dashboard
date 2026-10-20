"""One bounded refresh of curator-approved IDN sources; no AI, mail or scheduling.

Use one persistent private state directory per manifest/stage. Completed DB/check
writes advance the cursor; an interrupted import reuses its saved source artifact.
"""
import argparse
import fcntl
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from collect import collect, official_url, ORDER

REPO = Path(__file__).resolve().parents[2]
ACTIVE_MANIFESTS = ("sources.json", "sources-coal-core-20261020.json", "sources-coal-operations-20261020.json")
# Same official identity, recovered source/coal scope reviewed in the 10/20 pack.
# All other collisions require curator review instead of last-file-wins.
ACTIVE_OVERRIDES = {("sources.json", "sources-coal-operations-20261020.json", "idn-esdm-permen-6-2026")}


def load_manifest(path=None):
    files = [Path(path)] if path else [Path(__file__).with_name(name) for name in ACTIVE_MANIFESTS]
    entries, origins = {}, {}
    identity = ("issuer_name", "jurisdiction", "document_type", "document_number", "document_year")
    for file in files:
        for e in json.loads(file.read_text()):
            key = e["document_id"]
            if key in entries:
                if (origins[key], file.name, key) not in ACTIVE_OVERRIDES or any(entries[key].get(k) != e.get(k) for k in identity):
                    raise ValueError("conflicting active manifests; curator must resolve duplicate IDs")
            entries[key], origins[key] = e, file.name
    return list(entries.values())


def atomic_json(path, value):
    tmp = path.with_name(path.name + ".tmp")
    with os.fdopen(os.open(tmp, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600), "w") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


class Gateway:
    ROUTES = {"idn_store_document", "idn_store_source_check", "idn_mail_review_queue"}

    def __init__(self, env_file=None):
        values = dict(os.environ)
        if env_file:
            for line in Path(env_file).read_text().splitlines():
                key, sep, value = line.strip().partition("=")
                if sep and key and not key.startswith("#"):
                    value = value.strip()
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                        value = value[1:-1]
                    values.setdefault(key.strip(), value)
        self.url = values.get("SUPABASE_URL", "").rstrip("/")
        self.key = values.get("SUPABASE_SERVICE_ROLE_KEY", "")
        if urlparse(self.url).scheme != "https" or not self.key:
            raise ValueError("Supabase server credentials required")

    def __call__(self, name, args):
        if name not in self.ROUTES:
            raise ValueError("not an IDN refresh RPC")
        headers = {"apikey": self.key, "Content-Type": "application/json"}
        if self.key.startswith("eyJ"):
            headers["Authorization"] = "Bearer " + self.key
        try:
            started = time.monotonic()
            with requests.post(self.url + "/rest/v1/rpc/" + name, headers=headers, json=args,
                               timeout=(10, 45), stream=True, allow_redirects=False) as r:
                if r.status_code != 200:
                    raise RuntimeError("IDN database HTTP " + str(r.status_code))
                data = bytearray()
                for chunk in r.iter_content(16384):
                    data.extend(chunk)
                    if len(data) > 256 * 1024 or time.monotonic() - started > 60:
                        raise RuntimeError("IDN database response too large")
                return json.loads(data)
        except requests.RequestException:
            raise RuntimeError("IDN database network error; checkpoint retained") from None


def run(manifest, state_dir, rpc, *, limit=5, collect_fn=collect, now=time.time, pause=time.sleep):
    if not 1 <= limit <= 20 or not manifest:
        raise ValueError("nonempty manifest and limit 1..20 required")
    ids = [e["document_id"] for e in manifest]
    if len(set(ids)) != len(ids) or any(not official_url(e["url"]) or e["primary_stage"] not in ORDER for e in manifest):
        raise ValueError("duplicate ID or invalid curated source")
    root = Path(state_dir).resolve()
    if root == REPO or REPO in root.parents:
        raise ValueError("state directory must be outside repository")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    taxonomy = json.loads(Path(__file__).with_name("taxonomy.json").read_text())
    tags = {e["document_id"]: taxonomy.get(e["document_id"], {}).get("tags", []) for e in manifest}
    digest = hashlib.sha256(json.dumps({"manifest": manifest, "curated_tags": tags}, sort_keys=True).encode()).hexdigest()
    fd = os.open(root / "sync.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("IDN refresh already running") from None
        state_path = root / "status.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {
            "version": 1, "manifest_hash": digest, "cursor": 0, "cycle": 0, "active": None, "cooldowns": {}}
        if state.get("version") != 1 or state.get("manifest_hash") != digest:
            raise ValueError("manifest changed; preserve checkpoint and use a new state directory")
        stats = dict(attempted=0, new_versions=0, source_failures=0, metadata_only=0, cooldown_skips=0, stopped=False)
        for _ in range(min(limit, len(manifest))):
            if (root / "STOP").exists():
                stats["stopped"] = True
                break
            index = state["cursor"]
            if type(index) is not int or not 0 <= index < len(manifest):
                raise ValueError("invalid cursor")
            entry = manifest[index]
            host = urlparse(entry["url"]).hostname
            if state["active"] is None and state["cooldowns"].get(host, 0) > now():
                stats["cooldown_skips"] += 1
            else:
                if state["active"] is None:
                    state["active"] = {"document_id": entry["document_id"], "artifact": f"cycle-{state['cycle']:06d}-{index:04d}.json"}
                    atomic_json(state_path, state)
                active = state["active"]
                if active["document_id"] != entry["document_id"] or Path(active["artifact"]).name != active["artifact"]:
                    raise ValueError("checkpoint identity mismatch")
                artifact = root / active["artifact"]
                if artifact.exists():
                    item = json.loads(artifact.read_text())
                else:
                    cache = root / "raw"
                    cache.mkdir(exist_ok=True, mode=0o700)
                    checked = datetime.fromtimestamp(now(), timezone.utc).isoformat()
                    blocked = {h for h, until in state["cooldowns"].items() if until > now()}
                    try:
                        doc = collect_fn(entry, cache, blocked)
                        item = {"document": doc, "checked_at": checked}
                        if doc.get("body_fetch_blocked_host"):
                            state["cooldowns"][doc["body_fetch_blocked_host"]] = now() + 86400
                    except Exception as e:
                        status = getattr(getattr(e, "response", None), "status_code", None)
                        cooldown = 86400 if status in (403, 429) or "blocked" in str(e) or "maintenance" in str(e) else 3600
                        state["cooldowns"][host] = now() + cooldown
                        item = {"document": None, "checked_at": checked, "error": str(e)[:300]}
                    # Artifact first, then DB. Reuse exactly these bytes on retry.
                    item["cooldowns"] = state["cooldowns"].copy()
                    atomic_json(artifact, item)
                state["cooldowns"].update(item.get("cooldowns", {}))
                doc = item.get("document")
                if doc:
                    if doc.get("document_id") != entry["document_id"] or doc.get("country_code") != "IDN" or doc.get("legal_status") != "unverified" or hashlib.sha256(doc["text_content"].encode()).hexdigest() != doc.get("content_hash"):
                        raise ValueError("invalid saved source artifact")
                    doc["topics"] = sorted(set(doc["topics"] + taxonomy.get(doc["document_id"], {}).get("tags", [])))
                    changed = rpc("idn_store_document", {"p_document": doc})
                    if type(changed) is not bool:
                        raise RuntimeError("invalid IDN store response")
                    stats["new_versions"] += int(changed)
                    body_failure = doc.get("body_status", "").startswith("unavailable:")
                    check = dict(document_id=doc["document_id"], checked_at=doc["observed_at"], source_url=doc["source_url"], outcome="failed" if body_failure else "collected", detail=doc.get("body_status", doc["content_kind"])[:1000])
                    stats["source_failures"] += int(body_failure)
                    stats["metadata_only"] += int(doc["content_kind"] != "official_text")
                else:
                    check = dict(document_id=entry["document_id"], checked_at=item["checked_at"], source_url=entry["url"], outcome="failed", detail=item["error"])
                    stats["source_failures"] += 1
                rpc("idn_store_source_check", {"p_check": check})
                stats["attempted"] += 1
                state["active"] = None
            # Only complete source + DB audit writes advance the cursor.
            state["cursor"] = (index + 1) % len(manifest)
            state["cycle"] += int(state["cursor"] == 0)
            state["last_completed_at"] = datetime.fromtimestamp(now(), timezone.utc).isoformat()
            atomic_json(state_path, state)
            pause(2)
        return {"country": "IDN", **stats, "cursor": state["cursor"], "cycle": state["cycle"]}
    finally:
        os.close(fd)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, help="Explicit subset; defaults to the active reviewed manifest registry")
    p.add_argument("--stage", choices=[*ORDER, "all"], default="coal")
    p.add_argument("--state-dir", required=True)
    p.add_argument("--env-file")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--write", action="store_true")
    args = p.parse_args()
    if not 1 <= args.limit <= 20:
        p.error("limit must be 1..20")
    entries = [e for e in load_manifest(args.manifest) if args.stage == "all" or e["primary_stage"] == args.stage]
    entries.sort(key=lambda e: (ORDER.index(e["primary_stage"]), e["document_id"]))
    if not args.write:
        print(json.dumps(dict(mode="preview", country="IDN", curated_sources=len(entries), limit=args.limit, network=False, database_writes=False)))
        return
    result = run(entries, args.state_dir, Gateway(args.env_file), limit=args.limit)
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError) as exc:
        raise SystemExit(str(exc))
