# Indonesia collection on GitHub Actions

User requested moving the IDN collector from Mac to Actions on 2026-10-21.
Only `.github/workflows/sync-indonesia-policy.yml` has a branch ownership exception.
No UI/mail Worker, US collector, deployment workflow, or paid AI activation is included.

The dedicated workflow runs every four hours at minute 43 UTC (GitHub may delay scheduled runs).
It reuses existing `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` repository Secrets.
Only trusted schedule/manual contexts run it; no pull-request execution receives credentials.
`contents: read`, a single concurrency group, and the existing database lease limit overlapping writes.

The collector is pinned to reviewed commit `7cdbb19868426bcd82e0f5a263d260fadf181e8b` from PR #652.
This permits collection without merging or deploying that PR's UI/mail changes.
Update this explicit pin only after reviewing collector changes.

Private Supabase Storage bucket `idn-collector-state`, manifest `automatic/current.json` and content-hashed `automatic/chunks/*`,
contains official-source cache, processing artifacts, cursors and host cooldowns.
No credentials are written into it. It is not an Actions public artifact or repository file.
A missing/corrupt snapshot fails closed rather than restarting at zero.
Mac state is copied after its collector has stopped. Its transfer STOP is omitted from the
cloud copy only; the original Mac STOP and disabled LaunchAgent remain as rollback evidence.

The wrapper restores state, runs at most 20 curated refreshes plus 6 catalogue heads and
5 admission candidates, and uploads state in `finally` on ordinary failures.
A hard runner kill can precede upload. The next run replays the prior checkpoint; DB document
hashes and fenced transactions prevent duplicate versions. A just-discovered cooldown may
be lost on hard kill. No exactly-once remote checkpoint claim is made.
An upload failure fails the workflow and preserves the previous remote checkpoint.
The first run #39593520141 failed at the old 48 MiB archive cap after committing DB work.
Its ephemeral final cursor could not be recovered. One replay from the last saved Mac
checkpoint is necessary; document hashes and DB admission retry state preserve idempotency.
Archives reject traversal, links, >20k files and >1 GiB expansion/compression.
Each uploaded chunk is at most 16 MiB, below the unchanged 48 MiB bucket object limit.
Only after all chunks upload does a small manifest atomically replace the latest pointer.
Restoration checks individual sizes/digests and whole-archive digest before extraction.
A genuinely missing manifest restores the original Mac `automatic/current.tar.gz`;
a corrupt manifest, missing chunk, or network/auth error never falls back to old progress.
Prior chunks and the legacy archive are preserved. Stored historical chunks can grow;
no automatic evidence deletion or unlimited storage claim is made.
The collector also stops at its existing 1 GiB state capacity guard. Review capacity instead
of deleting evidence automatically. Mac must remain disabled while cloud collection is active.

The storage bucket is provisioned privately through the Storage API, without new browser/user
read policies. Mailing stays disabled; new records still require legal-effect/applicability
review before notification. Discovery coverage remains the registered sources, not all IDN laws.
