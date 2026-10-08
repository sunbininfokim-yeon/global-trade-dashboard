# AISStream private reception probe

User-authorized 2026-10-08 one-off diagnostic. Isolated branch:
`codex/aisstream-probe-20261008`. No main merge, deployment, schedule, database
mutation, or changes to existing workflows/UI/shipping model.

The repository secret `AISSTREAM_API_KEY` is available only inside the new
read-only GitHub job. It is never copied to local development, committed,
returned in reports, or printed. Artifacts remain behind repository access
checks and expire after three days. Do not publish vessel-level records.

The branch push starts one sample lasting at most 900 seconds; up to eight
connection attempts are allowed. A setup/network failure can end it earlier.
The outcome must be interpreted using actual connected time, attempts,
subscription confirmations and observed data, not the nominal 15-minute target.

Five rough diagnostic rectangles are subscribed on one WebSocket connection:
Persian Gulf inner area, Hormuz, Gulf of Oman, Rotterdam and Singapore controls.
They are not geographic transit gates and can overlap/include coastal land.
Reception counts are not additive across overlapping rectangles.

Reports:

- `summary.json`: message/unique MMSI counts, repeated observations, IMO and
  broad AIS-type availability, errors, time window and limitations.
- `observed_vessels_private.json`: received identities and last sampled
  positions for private source-quality checks, not a complete trajectory archive.

No message means **not observed in this sample**, not zero vessels. No current
in-strait census, inferred transit/exit, deliberate transmitter shutdown,
cargo/DWT/TEU/barrel conversion, or historical October 4 reconstruction is made.
Reception timestamps are not automatically the time a vessel was at a location.
IMO checksum validation is not independent proof of identity. Broad AIS cargo
codes cannot reliably separate container and bulk vessels; tanker codes do not
prove a crude cargo or its volume.

Official reference: https://www.aisstream.io/documentation
No direct browser connections; keep secrets server-side. No guaranteed delivery,
replay or regional coverage. Redistributable/public product use needs a separate
rights check; this diagnostic does not establish that permission.

Run tests without credentials or network:

```sh
python3 -m unittest discover -s scripts/aisstream_probe -p 'test_*.py' -v
```
