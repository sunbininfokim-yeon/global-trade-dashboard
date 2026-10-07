---
name: ui-safe-edit
description: >
  Conflict-prevention checklist for editing this repo's UI or deploy-owned files —
  "New for anti/" (app.js, style.css, index.html, data.js, shipping.js), _worker.js,
  or wrangler.jsonc. Use this BEFORE starting any edit to those files, whenever the
  user asks to change something in the UI, the map, the dashboard, the globe view,
  the worker/API proxy, or the Cloudflare deploy config — even if they don't mention
  Cursor, worktrees, or conflicts by name. This repo has a documented history of
  Cursor silently overwriting Claude Code's in-progress edits (2026-08-05 full
  app.js rollback) and of cross-session commit contamination from shared checkouts
  (three incidents on 2026-08-07). Skip this skill for read-only work (review,
  grep, explaining code) — it only applies when you're about to write to these files.
---

# UI/deploy safe-edit checklist

CLAUDE.md assigns Claude Code sole ownership of the UI and deploy files in this
repo, but ownership on paper doesn't stop a stale editor buffer from winning a
race. The failure mode isn't hypothetical — it already happened twice: on
2026-08-05, Cursor had `app.js` open, saved its (older) buffer over your commit,
and the fix vanished. On 2026-08-07 it happened three more times because two
sessions were writing into the same checkout. Both are silent failures — your
edit will look like it worked right up until someone notices the diff is gone.

Run through this before you start editing, not after something goes wrong.

## 1. Confirm you're in an isolated checkout, not the shared one

Check `docs/ops/handoff/` (most recent file) for the current worktree layout —
it's changed before and the path is authoritative there, not this skill. As of
the last recorded handoff, the shared checkout is Cursor's territory and Claude
Code work happens in a dedicated worktree under `.worktrees/`.

- If you're already in a path that looks like a dedicated worktree (e.g. contains
  `.worktrees/` or a branch-specific directory), continue.
- If you're in what looks like the main/shared checkout and this is a local
  session (not an ephemeral cloud container), create or switch to a worktree
  before editing:
  ```bash
  git worktree add ../<repo-dirname>.worktrees/claude-<topic> -b claude/<topic>
  ```
- In an ephemeral remote/cloud session with its own isolated clone, this step is
  already satisfied — no other editor shares your filesystem. Say so and move on
  rather than manufacturing a worktree that adds nothing.

## 2. Ask the user to close Cursor's grip on these files, if this is local

The collision only happens when a second program has the file open with its own
in-memory buffer. That's a local-machine problem — if you're running in a remote
container, no other editor can be looking at your working tree, so skip this
step entirely instead of asking a question that doesn't apply.

If you *are* running as local Claude Code (i.e. this session's filesystem is the
user's own machine), ask the user to confirm, before you write:
- Any Cursor tabs on `New for anti/*`, `_worker.js`, or `wrangler.jsonc` are closed
  (File › Close Folder is the reliable version — closing the tab isn't always enough)
- No Cursor Agent/Composer session is attached to this repo

You can't verify either of these programmatically from inside the edit — take
the user's word for it and proceed. Don't skip the question just because it
feels like friction; it's the one step that directly prevents the 2026-08-05
failure mode.

## 3. For large or multi-file edits, write a re-runnable patch script instead of editing freehand

A single `Edit` call against one location is fine as-is. But if you're touching
several places in `app.js`/`style.css` or restructuring a chunk of markup, prefer
writing the change as a small script (Python/Node/sed, whatever fits) that applies
the edit, rather than a long sequence of manual `Edit` calls. Reasoning: if a
Cursor save (or anything else) clobbers your work mid-edit, a re-runnable script
recovers in one command; a half-applied sequence of manual edits does not, and
you may not immediately notice which of several edits landed and which didn't.

This is a judgment call, not a hard gate — don't build script infrastructure for
a one-line CSS tweak.

## 4. Verify with grep after every apply, before considering the edit done

After writing (script or direct edit), grep for the change you just made and
confirm it's actually in the file on disk:

```bash
grep -n "<distinctive snippet you just added>" "New for anti/app.js"
```

Do this even when the tool call reported success. The whole point is that a
save can happen out-of-band, after your write returns but before you'd notice —
the tool result tells you what *you* wrote, not what's on disk a moment later.
If the grep comes back empty or shows the old content, something overwrote you;
stop and re-investigate rather than continuing to layer edits on top.

## 5. Close out per CLAUDE.md, not with an ad-hoc note

When the work is ready for review, use the repo's own handoff mechanism rather
than improvising a summary:

```bash
./tools/ops/handoff.sh claude "한 줄 요약과 남은 TODO"
```

Handoffs are single-owner files (`docs/ops/handoff/<날짜>-claude.md`) — don't
edit another agent's handoff file, and don't skip writing your own even for a
small change, since the next session (possibly you, with no memory of this one)
relies on it instead of scrollback.
