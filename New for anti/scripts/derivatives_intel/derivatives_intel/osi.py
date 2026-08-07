"""OSI (OCC) option symbol parsing.

Every US listed option is identified by an OSI symbol that already encodes the
underlying, expiry, right and strike — so a contract can be fully decoded from
its identifier alone, with no separate reference-data lookup. CBOE emits the
compact form (``TSLA260807C00320000``); the padded 21-character form is the
canonical one. Both are accepted.

Layout::

    AAPL  260116C00400000
    |___| |____||_______|
    root  yymmdd C  strike * 1000
    (6, space padded)
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from .models import OptionContract

_OSI_RE = re.compile(r"^(?P<root>.{6})(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})(?P<cp>[CP])(?P<strike>\d{8})$")


def parse_osi(symbol: str) -> Optional[OptionContract]:
    """Decode an OSI symbol, or return None when it is not one.

    Accepts both the space-padded 21-char form and the compact form some
    vendors emit (``AAPL260116C00400000``).
    """
    raw = symbol.strip()
    if len(raw) < 15:
        return None

    padded = raw if len(raw) == 21 else _repad(raw)
    if padded is None:
        return None

    m = _OSI_RE.match(padded)
    if not m:
        return None

    root = m.group("root").strip()
    if not root:
        return None

    try:
        expiry = date(2000 + int(m.group("yy")), int(m.group("mm")), int(m.group("dd")))
    except ValueError:
        return None

    return OptionContract(
        osi=padded,
        underlying=root,
        expiry=expiry,
        right=m.group("cp"),  # type: ignore[arg-type]
        strike=int(m.group("strike")) / 1000.0,
    )


def _repad(raw: str) -> Optional[str]:
    """Restore the 6-char root padding on a compact OSI symbol."""
    # The tail is always fixed width: 6 date + 1 right + 8 strike = 15.
    if len(raw) <= 15:
        return None
    root, tail = raw[:-15], raw[-15:]
    if len(root) > 6:
        return None
    return f"{root:<6}{tail}"


def build_osi(underlying: str, expiry: date, right: str, strike: float) -> str:
    """Inverse of :func:`parse_osi` — handy for tests and manual queries."""
    return f"{underlying.upper():<6}{expiry:%y%m%d}{right.upper()}{int(round(strike * 1000)):08d}"
