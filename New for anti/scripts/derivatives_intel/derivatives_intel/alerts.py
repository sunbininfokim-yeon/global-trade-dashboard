"""Notification sinks: Telegram, Discord, and a no-op console sink.

Sending defaults to **dry-run**. Nothing leaves the machine unless the caller
passes ``--send`` (or ``dry_run=False``) *and* the relevant credentials are in
the environment, so a stray cron run cannot spam a channel.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Protocol, Sequence

import requests

from .httputil import make_session
from .models import TickerSnapshot, UnusualActivity

log = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
MAX_ALERTS_PER_MESSAGE = 12


class AlertSink(Protocol):
    def send(self, text: str) -> bool: ...


class ConsoleSink:
    """Default sink — prints instead of transmitting."""

    def send(self, text: str) -> bool:
        print(text)
        return True


class TelegramSink:
    def __init__(self, token: str, chat_id: str, session: Optional[requests.Session] = None) -> None:
        self.token = token
        self.chat_id = chat_id
        self.session = session or make_session()

    @classmethod
    def from_env(cls) -> Optional["TelegramSink"]:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return None
        return cls(token, chat_id)

    def send(self, text: str) -> bool:
        try:
            resp = self.session.post(
                TELEGRAM_API.format(token=self.token),
                json={
                    "chat_id": self.chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=20,
            )
        except requests.RequestException as exc:
            log.error("telegram send failed: %s", exc)
            return False
        if resp.status_code != 200:
            log.error("telegram HTTP %s: %s", resp.status_code, resp.text[:200])
            return False
        return True


class DiscordSink:
    def __init__(self, webhook_url: str, session: Optional[requests.Session] = None) -> None:
        self.webhook_url = webhook_url
        self.session = session or make_session()

    @classmethod
    def from_env(cls) -> Optional["DiscordSink"]:
        url = os.getenv("DISCORD_WEBHOOK_URL")
        return cls(url) if url else None

    def send(self, text: str) -> bool:
        try:
            resp = self.session.post(self.webhook_url, json={"content": text[:1900]}, timeout=20)
        except requests.RequestException as exc:
            log.error("discord send failed: %s", exc)
            return False
        if resp.status_code >= 300:
            log.error("discord HTTP %s: %s", resp.status_code, resp.text[:200])
            return False
        return True


def resolve_sinks(dry_run: bool = True) -> list[AlertSink]:
    """Console when dry-running; otherwise whatever credentials are present."""
    if dry_run:
        return [ConsoleSink()]
    sinks: list[AlertSink] = []
    for factory in (TelegramSink.from_env, DiscordSink.from_env):
        sink = factory()
        if sink is not None:
            sinks.append(sink)
    if not sinks:
        log.warning("--send given but no TELEGRAM_*/DISCORD_* env vars set; falling back to console")
        return [ConsoleSink()]
    return sinks


# --------------------------------------------------------------------------
# formatting
# --------------------------------------------------------------------------

_MARK = {"C": "\U0001f7e2", "P": "\U0001f534"}


def format_unusual(item: UnusualActivity) -> str:
    """One line per standout contract.

    Deliberately no BUY/SELL label: a chain snapshot cannot tell who crossed the
    spread, and inventing that call would be the most misleading thing this tool
    could do.
    """
    bits = [
        f"{_MARK.get(item.contract.right, '')} <b>{item.contract.underlying}</b>",
        f"{item.contract.expiry:%m/%d} {item.contract.strike:g}{item.contract.right}",
        f"| vol {item.volume:,} / OI {item.open_interest:,}",
    ]
    if item.vol_oi_ratio is not None:
        bits.append(f"({item.vol_oi_ratio:.1f}x)")
    bits.append(f"| ${item.notional/1e6:.2f}M | {item.dte}DTE")
    if item.iv:
        bits.append(f"| IV {item.iv*100:.0f}%")
    return " ".join(bits)


def format_short_line(snap: TickerSnapshot) -> str:
    sv = snap.short_volume
    if sv is None or sv.short_ratio is None:
        return f"<b>{snap.symbol}</b> — 공매도 데이터 없음"

    bits = [f"<b>{snap.symbol}</b> {sv.date:%m/%d} short {sv.short_ratio*100:.1f}%"]
    if snap.short_ratio_mean_20d is not None:
        bits.append(f"(20d avg {snap.short_ratio_mean_20d*100:.1f}%)")
    if snap.short_ratio_z is not None:
        bits.append(f"z={snap.short_ratio_z:+.2f}")
    if snap.short_interest is not None and snap.short_interest.days_to_cover is not None:
        bits.append(f"DTC {snap.short_interest.days_to_cover:.2f}")
    return " ".join(bits)


def format_chain_line(snap: TickerSnapshot) -> str:
    c = snap.chain
    if c is None:
        return f"<b>{snap.symbol}</b> — 체인 데이터 없음"
    bits = [f"<b>{snap.symbol}</b> ${c.spot:,.2f}"]
    pcv = c.put_call_volume_ratio
    if pcv is not None:
        bits.append(f"P/C vol {pcv:.2f}")
    pcp = c.put_call_premium_ratio
    if pcp is not None:
        bits.append(f"P/C prem {pcp:.2f}")
    if c.iv30:
        bits.append(f"IV30 {c.iv30:.1f}")
    if c.gamma_exposure:
        bits.append(f"GEX {c.gamma_exposure/1e9:+.2f}B")
    return " | ".join(bits)


def compose_digest(snapshots: Sequence[TickerSnapshot], asof_label: str) -> str:
    lines = [f"<b>Derivatives Intel</b> — {asof_label}", ""]

    lines.append("<b>공매도 현황</b>")
    for snap in snapshots:
        lines.append("  " + format_short_line(snap))

    lines.append("")
    lines.append("<b>옵션 포지셔닝</b>")
    for snap in snapshots:
        lines.append("  " + format_chain_line(snap))

    items = [u for s in snapshots for u in s.unusual]
    items.sort(key=lambda u: u.score, reverse=True)

    lines.append("")
    if items:
        shown = min(len(items), MAX_ALERTS_PER_MESSAGE)
        lines.append(f"<b>이상 거래</b> (상위 {shown}/{len(items)})")
        for item in items[:MAX_ALERTS_PER_MESSAGE]:
            lines.append("  " + format_unusual(item))
    else:
        lines.append("<b>이상 거래</b> — 임계값을 넘은 계약 없음")

    return "\n".join(lines)


def dispatch(sinks: Sequence[AlertSink], text: str) -> int:
    """Fan a message out; returns how many sinks accepted it."""
    return sum(1 for sink in sinks if sink.send(text))
