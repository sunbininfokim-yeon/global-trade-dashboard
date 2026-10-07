"""English (and Korean) headlines for non-English sources, via Gemini.

Why English first: the commodity and country taggers are built on English
aliases and market terms. A Chinese export-control notice that names 镓 or 锑
-- or names no metal at all, only "两用物项" -- is invisible to them until it
reads "gallium", "antimony", "dual-use items". So a source that opts in with
"translate": true has its headlines translated *before* tagging, and the
tagger reads original and English together.

Export-control items (a source with a "board") also get a small structured
reading of the headline for the export-controls window: what kind of measure
it is, which goods or technologies it names, and which countries it targets.
That is an LLM's reading of one headline -- the item says so
(control.extracted_by) -- and the original is always one click away.

Optional by design: no GEMINI_API_KEY, a quota error, a model that no longer
exists -- the build carries on with the originals, exactly as before this
module existed. Translations are carried between builds by URL + title, so a
headline is sent once, not every four hours.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# First one that answers wins. Aliases first, so a model retirement does not
# break the build; GEMINI_TRANSLATE_MODEL pins one when that matters.
DEFAULT_MODELS = ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.5-flash"]
BATCH = 40

MEASURES = [
    "entity_list",        # parties added to / removed from a control or unreliable-entity list
    "export_restriction",  # licence requirement or control placed on goods/technology
    "export_ban",         # outright prohibition
    "sanctions",          # blocking / asset freeze / SDN-type designation
    "countermeasure",     # retaliation against another country's measures
    "list_adjustment",    # control list / catalogue amended
    "suspension",         # a control paused, lifted or exempted
    "enforcement",        # penalties, investigations, reporting channels
    "dialogue",           # bilateral talks, working groups, meetings
    "guidance",           # how-to, FAQ, compliance guidance
    "other",
]

_PROMPT = """You translate official trade-regulation headlines for an analyst dashboard.

For each item return:
- "en": a faithful English translation of the headline (keep names of laws, lists and agencies; do not summarise or add facts).
- "ko": a faithful Korean translation of the headline.
For items with "control": true, also return:
- "measure": one of {measures} -- what the headline says was done. Use "other" if unclear.
  A government restricting its own exports counts too: a ban (or its extension) on exporting a good is "export_ban"; a quota, licence, minimum export price, export duty or amended export policy is "export_restriction"; lifting or relaxing one is "suspension".
- "items": the goods, materials or technologies the headline names, in lowercase English (e.g. "gallium", "rare earths", "drones", "lithium battery technology"). Empty if none are named. Do not infer items that are not in the headline.
- "targets": ISO 3166 alpha-3 codes of the countries the measure is aimed at, or "EU" for the European Union. Empty if none are named.

Return a JSON array with one object per input item, each carrying its "key".

Items:
{items}"""


def _schema(control: bool) -> Dict[str, Any]:
    props: Dict[str, Any] = {
        "key": {"type": "STRING"},
        "en": {"type": "STRING"},
        "ko": {"type": "STRING"},
    }
    if control:
        props.update({
            "measure": {"type": "STRING", "enum": MEASURES},
            "items": {"type": "ARRAY", "items": {"type": "STRING"}},
            "targets": {"type": "ARRAY", "items": {"type": "STRING"}},
        })
    return {"type": "ARRAY", "items": {"type": "OBJECT", "properties": props, "required": ["key", "en", "ko"]}}


def _post(url: str, body: Dict[str, Any], api_key: str, timeout: float) -> Dict[str, Any]:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


class GeminiAnnotator:
    """Batch headline annotation. `post` is injectable for tests."""

    def __init__(self, api_key: Optional[str] = None, *, models: Optional[List[str]] = None,
                 timeout: float = 60.0, post: Optional[Callable[..., Dict[str, Any]]] = None):
        self.api_key = api_key if api_key is not None else os.environ.get("GEMINI_API_KEY", "")
        pinned = os.environ.get("GEMINI_TRANSLATE_MODEL", "").strip()
        self.models = models or ([pinned] if pinned else []) + DEFAULT_MODELS
        self.timeout = timeout
        self.post = post or _post
        self.model_used: Optional[str] = None
        self.error: Optional[str] = None
        self.calls = 0

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def annotate(self, items: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """items: [{"key", "title", "lang", "control": bool}] -> key -> result.

        Missing keys in the result mean "no translation"; the caller keeps
        the original. Never raises.
        """
        out: Dict[str, Dict[str, Any]] = {}
        if not self.enabled or not items:
            return out
        for control in (False, True):
            group = [it for it in items if bool(it.get("control")) == control]
            for i in range(0, len(group), BATCH):
                if self.error:
                    return out  # a dead key or exhausted quota: stop asking
                out.update(self._batch(group[i:i + BATCH], control))
        return out

    def _batch(self, batch: List[Dict[str, Any]], control: bool) -> Dict[str, Dict[str, Any]]:
        listing = json.dumps(
            [{"key": it["key"], "lang": it.get("lang") or "", "control": control, "title": it["title"]}
             for it in batch],
            ensure_ascii=False,
        )
        body = {
            "contents": [{"role": "user", "parts": [{"text": _PROMPT.format(measures=", ".join(MEASURES), items=listing)}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": _schema(control),
            },
        }
        models = [self.model_used] if self.model_used else self.models
        for model in models:
            try:
                payload = self.post(ENDPOINT.format(model=model), body, self.api_key, self.timeout)
                self.calls += 1
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    continue  # retired or unknown model: try the next name
                self.error = f"HTTP {exc.code} on {model}"
                return {}
            except Exception as exc:  # noqa: BLE001 -- translation is optional
                self.error = f"{type(exc).__name__} on {model}"
                return {}
            self.model_used = model
            return self._parse(payload, batch, control)
        self.error = "no model answered (all 404)"
        return {}

    @staticmethod
    def _parse(payload: Dict[str, Any], batch: List[Dict[str, Any]], control: bool) -> Dict[str, Dict[str, Any]]:
        try:
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            rows = json.loads(text)
        except (KeyError, IndexError, TypeError, ValueError):
            return {}
        wanted = {it["key"] for it in batch}
        out: Dict[str, Dict[str, Any]] = {}
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or row.get("key") not in wanted:
                continue
            en = str(row.get("en") or "").strip()
            ko = str(row.get("ko") or "").strip()
            if not en:
                continue
            res: Dict[str, Any] = {"en": en, "ko": ko or None}
            if control:
                measure = row.get("measure") if row.get("measure") in MEASURES else "other"
                res["control"] = {
                    "measure": measure,
                    "items": sorted({str(x).strip().lower() for x in row.get("items") or [] if str(x).strip()}),
                    "targets": sorted({str(x).strip().upper() for x in row.get("targets") or [] if str(x).strip()}),
                }
            out[row["key"]] = res
        return out
