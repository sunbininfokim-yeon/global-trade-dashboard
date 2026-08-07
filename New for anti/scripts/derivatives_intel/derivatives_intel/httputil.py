"""Shared HTTP session with retries and a polite user agent."""

from __future__ import annotations

import logging
from typing import Any, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger(__name__)

USER_AGENT = "new-for-anti-derivatives-intel/1.0 (+dashboard pipeline)"
DEFAULT_TIMEOUT = 30


def make_session(total_retries: int = 3) -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=total_retries,
        backoff_factor=1.0,
        # 403 is deliberately absent: FINRA's CDN returns it for "file not
        # published yet", which is a normal condition we walk back from rather
        # than something to retry.
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=8)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def get_text(session: requests.Session, url: str, timeout: int = DEFAULT_TIMEOUT) -> Optional[str]:
    """GET returning body text, or None on any non-200 / transport failure."""
    try:
        resp = session.get(url, timeout=timeout)
    except requests.RequestException as exc:
        log.warning("GET %s failed: %s", url, exc)
        return None
    if resp.status_code != 200:
        log.info("GET %s -> HTTP %s", url, resp.status_code)
        return None
    return resp.text


def post_json(
    session: requests.Session,
    url: str,
    payload: dict,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[Any]:
    """POST a JSON body and decode a JSON response, or None on failure."""
    try:
        resp = session.post(
            url,
            json=payload,
            timeout=timeout,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
    except requests.RequestException as exc:
        log.warning("POST %s failed: %s", url, exc)
        return None
    if resp.status_code != 200:
        log.info("POST %s -> HTTP %s: %s", url, resp.status_code, resp.text[:200])
        return None
    try:
        return resp.json()
    except ValueError as exc:
        log.warning("POST %s returned non-JSON: %s", url, exc)
        return None
