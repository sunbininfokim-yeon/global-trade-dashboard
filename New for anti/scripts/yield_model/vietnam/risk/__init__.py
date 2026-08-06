"""Mekong hydrology / salinity early-warning risk monitor (not yield forecast)."""

from .mekong_risk import build_risk_payload, write_risk_json

__all__ = ["build_risk_payload", "write_risk_json"]
