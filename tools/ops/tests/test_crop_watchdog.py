"""Offline tests for tools/ops/crop_watchdog.py against synthetic payloads."""

import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import crop_watchdog as W  # noqa: E402


def _setup(tmp_path, monkeypatch, payload, country="testland", mode="forecast"):
    models, data = tmp_path / "models", tmp_path / "data"
    (models / country).mkdir(parents=True)
    data.mkdir()
    (models / country / "model.yaml").write_text(
        f"country: {country}\npanel_mode: {mode}\ndata_file: {country}.json\n")
    (data / f"{country}.json").write_text(json.dumps(payload))
    monkeypatch.setattr(W, "MODELS", str(models))
    monkeypatch.setattr(W, "DATA", str(data))


def test_fresh_payload_passes(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, {"generated_at": "2026-10-30T20:00:00+00:00",
                                   "regions": {"a": {"weather_through": "2026-10-24"}}})
    assert W.check(date(2026, 11, 1)) == ([], [])


def test_stale_run_and_stale_weather_are_errors(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, {"generated_at": "2026-10-30T20:00:00+00:00",
                                   "regions": {"a": {"x": {"weather_through": "2026-09-01"}}}})
    errors, _ = W.check(date(2026, 11, 20))
    assert any("days old" in e for e in errors)
    assert any("feed has stopped" in e for e in errors)


def test_skipped_and_future_weather_are_warnings(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, {"generated_at": "2026-10-30T20:00:00+00:00",
                                   "regions": {"a": {"weather_through": "2026-11-14"}},
                                   "skipped": {"b": "no trained model"}})
    errors, warnings = W.check(date(2026, 11, 1))
    assert errors == []
    assert len(warnings) == 2


def test_reference_panels_are_ignored(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, {"generated_at": "2020-01-01T00:00:00+00:00"},
           mode="reference")
    assert W.check(date(2026, 11, 1)) == ([], [])
