"""Public KR extras (deposit/credit/flows/LETF categories).

FreeSIS funding/credit: see fetch_freesis_credit.py
  fetch_freesis_funding_credit() → 예탁·신용융자·담보·미수·반대매매

Naver remains fallback for simple deposit/credit when FreeSIS fails.
Full local module may include additional helpers; this file on PR
re-exports FreeSIS entrypoint for Claude/engine consumers.
"""
from __future__ import annotations

from fetch_freesis_credit import fetch_freesis_funding_credit

__all__ = ["fetch_freesis_funding_credit"]
