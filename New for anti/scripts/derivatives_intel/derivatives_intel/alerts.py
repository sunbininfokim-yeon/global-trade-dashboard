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
from .models import FlowAlert, TickerSnapshot

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

_ARROW = {"bullish": "\U0001f7e2", "bearish": "\U0001f534", "neutral": "⚪"}


def format_alert(alert: FlowAlert) -> str:
    return (
        f"{_ARROW.get(alert.sentiment, '')} <b>{alert.contract.underlying}</b> "
        f"{alert.contract.expiry:%Y-%m-%d} {alert.contract.strike:g}{alert.contract.right} "
        f"| {alert.kind.upper()} {alert.aggressor} "
        f"| {alert.size:,} @ {alert.vwap:.2f} "
        f"| ${alert.notional/1e6:.2f}M | DTE {alert.dte}"
        + (f" | {alert.venues} venues" if alert.venues > 1 else "")
    )


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


def compose_digest(snapshots: Sequence[TickerSnapshot], asof_label: str) -> str:
    lines = [f"<b>Derivatives Intel</b> — {asof_label}", ""]

    lines.append("<b>공매도 현황</b>")
    for snap in snapshots:
        lines.append("  " + format_short_line(snap))

    alerts = [a for s in snapshots for a in s.flow_alerts]
    alerts.sort(key=lambda a: a.notional, reverse=True)

    lines.append("")
    if alerts:
        lines.append(f"<b>옵션 이상 거래</b> (상위 {min(len(alerts), MAX_ALERTS_PER_MESSAGE)}/{len(alerts)})")
        for alert in alerts[:MAX_ALERTS_PER_MESSAGE]:
            lines.append("  " + format_alert(alert))
    else:
        lines.append("<b>옵션 이상 거래</b> — 임계값을 넘은 체결 없음")

    return "\n".join(lines)


def dispatch(sinks: Sequence[AlertSink], text: str) -> int:
    """Fan a message out; returns how many sinks accepted it."""
    return sum(1 for sink in sinks if sink.send(text))
