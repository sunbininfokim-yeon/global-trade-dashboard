"""Bounded AISStream reception diagnostic; never a vessel census or cargo model."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import time

ENDPOINT = "wss://stream.aisstream.io/v0/stream"
# Rough diagnostic rectangles, not navigation boundaries or transit gates.
REGIONS = {
    "persian_gulf_inner": (24.0, 48.0, 30.7, 56.0),
    "hormuz": (25.5, 55.8, 27.3, 57.3),
    "gulf_of_oman_outer": (22.5, 57.3, 26.5, 60.5),
    "rotterdam_control": (51.7, 3.8, 52.2, 4.7),
    "singapore_control": (1.0, 103.5, 1.5, 104.3),
}
POSITION_TYPES = {
    "PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport"
}
MESSAGE_TYPES = sorted(POSITION_TYPES | {"ShipStaticData", "StaticDataReport"})


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def valid_mmsi(value):
    if isinstance(value, bool):
        return None
    text = str(value)
    return text if len(text) == 9 and text.isdigit() else None


def valid_imo(value):
    text = str(value)
    if len(text) != 7 or not text.isdigit():
        return None
    checksum = sum(int(digit) * weight for digit, weight in zip(text[:6], range(7, 1, -1)))
    return text if checksum % 10 == int(text[-1]) else None


def position_of(body):
    try:
        if isinstance(body.get("Latitude"), bool) or isinstance(body.get("Longitude"), bool):
            return None
        lat, lon = float(body["Latitude"]), float(body["Longitude"])
        if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
            return lat, lon
    except (KeyError, TypeError, ValueError):
        pass
    return None


def regions_at(lat, lon):
    return [name for name, (south, west, north, east) in REGIONS.items()
            if south <= lat <= north and west <= lon <= east]


def type_group(code):
    # AIS cargo codes do not distinguish container from dry-bulk cargo vessels.
    if isinstance(code, int) and not isinstance(code, bool):
        if 80 <= code <= 89:
            return "tanker_ais_code_not_crude_cargo_confirmed"
        if 70 <= code <= 79:
            return "cargo_ais_code_container_bulk_not_distinguished"
        if 60 <= code <= 69:
            return "passenger"
        if 1 <= code <= 99:
            return "other"
    return "unknown"


class Probe:
    def __init__(self):
        self.started_at = utc_now()
        self.ended_at = None
        self.messages = Counter()
        self.region_positions = Counter()
        self.region_vessels = {name: set() for name in REGIONS}
        self.vessels = {}
        self.errors = Counter()
        self.connection_attempts = 0
        self.connected_seconds = 0.0
        self.confirmations = 0
        self.server_rejected = False
        self.invalid_messages = 0

    def ingest(self, event, received_at=None):
        if not isinstance(event, dict):
            self.invalid_messages += 1
            return
        kind = event.get("MessageType")
        if not kind and (event.get("error") or event.get("Error")):
            # Do not retain or print upstream error text: it might echo a secret.
            self.server_rejected = True
            self.errors["server_rejected_subscription"] += 1
            return
        if kind == "SubscriptionConfirmation":
            self.confirmations += 1
            return
        if kind not in MESSAGE_TYPES:
            self.messages["other_message"] += 1
            return
        self.messages[kind] += 1
        metadata = event.get("MetaData", {})
        body = event.get("Message", {}).get(kind, {})
        if not isinstance(metadata, dict) or not isinstance(body, dict):
            self.invalid_messages += 1
            return
        if body.get("Valid") is False:
            self.invalid_messages += 1
            return
        mmsi = valid_mmsi(body.get("UserID", metadata.get("MMSI")))
        meta_mmsi = valid_mmsi(metadata.get("MMSI"))
        if not mmsi or (meta_mmsi and meta_mmsi != mmsi):
            self.invalid_messages += 1
            return
        if mmsi not in self.vessels and len(self.vessels) >= 20000:
            self.errors["vessel_memory_cap"] += 1
            return
        ship = self.vessels.setdefault(mmsi, {
            "mmsi": mmsi, "imo": None, "ship_type_code": None,
            "name": None, "first_received_at": received_at or utc_now(),
            "last_received_at": None, "last_position": None,
            "position_messages": 0, "regions_seen": [],
        })
        ship["last_received_at"] = received_at or utc_now()
        if kind == "ShipStaticData":
            ship["imo"] = valid_imo(body.get("ImoNumber")) or ship["imo"]
            ship["ship_type_code"] = body.get("Type", ship["ship_type_code"])
            ship["name"] = body.get("Name") or ship["name"]
        elif kind == "StaticDataReport":
            part_a, part_b = body.get("ReportA") or {}, body.get("ReportB") or {}
            ship["name"] = part_a.get("Name") or ship["name"]
            ship["ship_type_code"] = part_b.get("ShipType", part_b.get("Type", ship["ship_type_code"]))
        else:
            location = position_of(body)
            if location is None:
                self.invalid_messages += 1
                return
            lat, lon = location
            names = regions_at(lat, lon)
            ship["name"] = metadata.get("ShipName") or ship["name"]
            ship["position_messages"] += 1
            ship["last_position"] = {
                "latitude": lat, "longitude": lon,
                "received_at": received_at or utc_now(),
                "source_time_utc": metadata.get("time_utc"),
                "speed_knots_reported": body.get("Sog"),
            }
            for name in names:
                self.region_positions[name] += 1
                self.region_vessels[name].add(mmsi)
                if name not in ship["regions_seen"]:
                    ship["regions_seen"].append(name)

    def report(self):
        focal = sum(self.region_positions[name] for name in list(REGIONS)[:3])
        control = sum(self.region_positions[name] for name in list(REGIONS)[3:])
        accepted = self.confirmations > 0 or any(self.region_positions.values())
        if focal:
            status = "focal_positions_observed_not_full_census"
        elif control:
            status = "controls_observed_focal_not_observed_in_sample"
        elif self.server_rejected:
            status = "server_rejected_subscription"
        elif accepted:
            status = "subscription_confirmed_no_positions_observed_in_sample"
        else:
            status = "subscription_unconfirmed_no_positions_observed_in_sample"
        regions = {}
        for name, bounds in REGIONS.items():
            records = [self.vessels[mmsi] for mmsi in sorted(self.region_vessels[name])]
            regions[name] = {
                "diagnostic_rectangle_south_west_north_east": list(bounds),
                "position_messages_received": self.region_positions[name],
                "unique_mmsi_observed_during_window": len(records),
                "valid_imo_available": sum(ship["imo"] is not None for ship in records),
                "repeated_position_mmsi": sum(ship["position_messages"] > 1 for ship in records),
                "ais_type_groups": dict(Counter(type_group(ship["ship_type_code"]) for ship in records)),
                "sample_mmsi": [ship["mmsi"] for ship in records[:5]],
                "status": "positions_observed" if records else "not_observed_in_sample_not_zero_vessels",
            }
        return {
            "source": "AISStream", "endpoint": ENDPOINT, "status": status,
            "started_at": self.started_at, "ended_at": self.ended_at,
            "snapshot_at": utc_now(), "connection_attempts": self.connection_attempts,
            "connected_seconds": round(self.connected_seconds, 1),
            "subscription_confirmations": self.confirmations,
            "message_counts": dict(self.messages), "invalid_messages": self.invalid_messages,
            "errors": dict(self.errors), "regions": regions,
            "full_population_coverage_known": False,
            "inside_vessel_total": None, "transit_count": None,
            "cargo_tonnes": None, "crude_barrels": None,
            "limitations": [
                "Counts are received messages and unique identifiers during this sample, not current vessel stock.",
                "No messages does not mean no vessels. Rough rectangles may overlap and include land.",
                "No exit, intentional AIS shutdown, loaded cargo, or tanker crude classification is inferred.",
                "No historical replay or completeness guarantee. This is a private diagnostic, not publishable traffic data.",
            ],
        }

    def save(self, output, key):
        output.mkdir(parents=True, exist_ok=True)
        for filename, value in (("summary.json", self.report()),
                                ("observed_vessels_private.json", list(self.vessels.values()))):
            serialized = json.dumps(value, ensure_ascii=False, indent=2)
            if key:
                serialized = serialized.replace(key, "[REDACTED]")
            (output / filename).write_text(serialized + "\n", encoding="utf-8")


async def collect(probe, key, seconds, output):
    from websockets.asyncio.client import connect

    deadline = time.monotonic() + seconds
    next_progress = time.monotonic() + 60
    subscription = {
        "APIKey": key,
        "BoundingBoxes": [[[south, west], [north, east]]
                          for south, west, north, east in REGIONS.values()],
        "FilterMessageTypes": MESSAGE_TYPES,
    }
    while time.monotonic() < deadline and probe.connection_attempts < 8:
        probe.connection_attempts += 1
        connected_at = None
        try:
            async with connect(ENDPOINT, compression="deflate", open_timeout=15,
                               ping_interval=20, ping_timeout=20, close_timeout=5,
                               max_size=2 * 1024 * 1024) as socket:
                connected_at = time.monotonic()
                await socket.send(json.dumps(subscription))
                while time.monotonic() < deadline:
                    remaining = deadline - time.monotonic()
                    try:
                        frame = await asyncio.wait_for(socket.recv(), timeout=min(10, remaining))
                    except asyncio.TimeoutError:
                        frame = None
                    if frame is not None:
                        try:
                            probe.ingest(json.loads(frame))
                        except (ValueError, TypeError, AttributeError):
                            probe.invalid_messages += 1
                    if probe.server_rejected:
                        break
                    if time.monotonic() >= next_progress:
                        probe.save(output, key)
                        print(json.dumps({"elapsed_seconds": round(seconds - (deadline - time.monotonic())),
                                          "region_position_messages": dict(probe.region_positions),
                                          "subscription_confirmations": probe.confirmations}), flush=True)
                        next_progress = time.monotonic() + 60
                if probe.server_rejected:
                    break
        except Exception as error:
            # Retain exception class only, never repr/str(error) or request payloads.
            probe.errors[type(error).__name__] += 1
        finally:
            if connected_at is not None:
                probe.connected_seconds += time.monotonic() - connected_at
            probe.save(output, key)
        remaining = deadline - time.monotonic()
        if remaining > 0 and not probe.server_rejected:
            await asyncio.sleep(min(remaining, 2 ** min(probe.connection_attempts, 5)))
    probe.ended_at = utc_now()
    probe.save(output, key)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=900)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 900:
        parser.error("sampling time must be between 1 and 900 seconds")
    key = os.environ.get("AISSTREAM_API_KEY", "").strip()
    probe = Probe()
    if not key:
        probe.errors["missing_server_secret"] += 1
        probe.ended_at = utc_now()
        probe.save(args.output, key)
        print("Missing server-side secret; no subscription sent.", flush=True)
        return 2
    asyncio.run(collect(probe, key, args.seconds, args.output))
    print(json.dumps(probe.report(), ensure_ascii=False), flush=True)
    return 2 if probe.server_rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
