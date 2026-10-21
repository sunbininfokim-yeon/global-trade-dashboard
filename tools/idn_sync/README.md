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

Private Supabase Storage bucket `idn-collector-state`, object `automatic/current.tar.gz`,
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
Archives reject traversal, links, >20k files, >1 GiB expansion and >48 MiB compression.
The collector also stops at its existing 1 GiB state capacity guard. Review capacity instead
of deleting evidence automatically. Mac must remain disabled while cloud collection is active.

The storage bucket is provisioned privately through the Storage API, without new browser/user
read policies. Mailing stays disabled; new records still require legal-effect/applicability
review before notification. Discovery coverage remains the registered sources, not all IDN laws.
