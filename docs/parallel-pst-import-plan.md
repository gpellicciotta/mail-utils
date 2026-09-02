# Parallel Multi-Process `import-pst` — Design & Feasibility Plan

This document is the full design for an opt-in `--parallel N` mode on `import-pst`, which would partition a
large PST archive's messages across N worker subprocesses and merge their results, to cut wall-clock time
for archives large enough that a single process is the bottleneck. It exists so the design is ready to
implement quickly if a future archive makes it worthwhile — see [Current Verdict](#current-verdict) for why
it isn't being built now.

---

## Current Verdict

Spun off from **T0020** while importing the ~26 GB `anubex-outlook-backup.pst` (186,475 messages), whose
import was originally taking 30+ hours and visibly slowing down over time. Root cause turned out to be FTS5
index fragmentation from ~127,000 uninterrupted per-message incremental delete+insert cycles into
`messages_fts`, not raw single-process throughput — fixed on T0020's branch by skipping per-message FTS
maintenance during bulk imports and doing one bulk rebuild afterward instead.

**Measured result**: the real 26 GB / 186,475-message archive now imports single-process, end to end, in
**50.8 minutes** — comfortably under the few-hours bar that made this task feel urgent in the first place.

Given that, multi-process parallelism's added complexity and new failure surface (worker isolation,
partition/merge logic, partial-merge cleanup, a new class of crash mid-slice) is very likely not worth it
for any archive size seen in practice so far. This design is kept ready rather than built, per
[When To Revisit](#when-to-revisit) below.

---

## Architecture

The parallel path is purely a new orchestration layer — partition, spawn, merge — wrapped around the
existing single-process import loop, which stays completely unchanged. No parsing or upsert code is
duplicated or forked.

```
import-pst --parallel N archive.pst --db target/
  │
  ├─ 1. Pre-scan: walk_folders() enumerates every message_nid (cheap, structural only)
  ├─ 2. Partition: split the flat nid list into N contiguous, roughly-equal chunks
  ├─ 3. Spawn: N worker subprocesses, each importing its own chunk into its own
  │            throwaway --db directory (own mails.db + attachments/)
  ├─ 4. Wait: for every worker to exit; abort the merge if any exited non-zero
  ├─ 5. Merge: worker databases + attachment stores → target --db, one worker at a time
  ├─ 6. Rebuild: messages_fts, once, from the fully-merged messages table
  └─ 7. Cleanup: delete the N worker directories once the merge is verified
```

### Worker entry point

Two options were considered:

- **`multiprocessing.Process` calling the import function in-process.** Rejected: SQLite connections,
  open file handles, and PST parser state (`ndb.py`'s B-tree page cache) would all need to survive
  pickling across the fork/spawn boundary. Windows only supports `spawn`, not `fork`, which re-imports the
  module fresh in each child anyway — so there's no real savings over a subprocess, but there is real risk
  of subtly broken shared state.
- **Subprocess re-invoking the CLI itself in a hidden worker mode.** Chosen: `import-pst --parallel N`
  spawns `N` copies of `sys.executable -m mail_utils.cli import-pst <path> --db <worker_dir>` with two new,
  undocumented (not shown in `--help`) flags: `--worker-nid-start` and `--worker-nid-end` (half-open
  range over the pre-scanned nid list). Each worker is a fully ordinary `import-pst` process — same code
  path as running it stand-alone — just scoped to a slice of the archive and a throwaway `--db` directory.
  This keeps every existing single-process code path, including its own tests, completely untouched: the
  orchestrator only ever constructs command lines and reads worker exit codes.

### Partition logic

- `walk_folders()` already produces a deterministic, structural-only listing (no per-message parsing) —
  reused unchanged as the pre-scan.
- The flat `message_nid` list is split into `N` contiguous chunks of `ceil(count / N)` (last chunk gets the
  remainder). Contiguous rather than round-robin, so each worker's chunk maps to a readable
  `--worker-nid-start`/`--worker-nid-end` range for logging and retry.
- `N` larger than the message count is clamped down to the message count (no empty workers).
- No attempt at size-weighted partitioning (e.g. by attachment bytes) — message count is a reasonable proxy
  and avoids a second, more expensive pre-scan pass.

### Merge logic

Each worker's `mails.db` is merged into the target one at a time, each as its own transaction, in this
order (parent tables before dependents):

1. `labels` — `INSERT OR IGNORE` (label ids are derived from folder paths, so identical labels are expected
   to appear in every worker's slice; the first write wins, later ones are no-ops).
2. `messages` — `INSERT OR IGNORE` keyed by message `id`. Partitions are disjoint by construction (each
   `message_nid` belongs to exactly one worker's contiguous range), so no real conflicts are expected; `OR
   IGNORE` is a safety net, not the primary correctness mechanism.
3. `message_addresses`, `attachments` — `INSERT OR IGNORE`, same reasoning.

Implementation mechanism: `ATTACH DATABASE '<worker_db_path>' AS w;` on the target connection, then
`INSERT OR IGNORE INTO messages SELECT * FROM w.messages;` (and similarly for the other three tables),
`DETACH DATABASE w;`. This keeps the merge as plain SQL rather than reading rows into Python and
re-inserting them.

`messages_fts` is **not** merged directly — FTS5's on-disk segment format isn't a stable target for
cross-database copying. Instead, after all N workers are merged, the target's FTS index is rebuilt once
from the fully-merged `messages` table (the same bulk-rebuild path T0020's FTS5 fragmentation fix
introduced for the single-process case).

Attachment stores merge by content address: for each file under a worker's `attachments/` directory (named
by `content_sha256`), copy it to the target's `attachments/` directory only if a file with that name
doesn't already exist there. Content-addressed naming makes this both safe (no risk of overwriting
different content under the same name) and idempotent (safe to re-run a partial merge).

### Cleanup

Once every worker's database and attachment store has been merged and the merge is verified (see
[Failure Handling](#failure-handling)), the N worker directories are deleted. Cleanup only happens after a
fully successful merge — a failed or partial merge leaves the worker directories in place for inspection
and manual retry.

---

## Failure Handling

- **A worker exits non-zero:** the orchestrator waits for all workers, then aborts before merging anything
  if any exited non-zero. The failing worker's `--worker-nid-start`/`--worker-nid-end` range is logged so a
  retry can target just that slice (re-running the same worker command is safe and idempotent, since the
  worker's own `--db` is a fresh throwaway directory each time).
- **A merge step fails partway (e.g. disk full mid-copy):** each worker's merge is one target-database
  transaction (per the `ATTACH`/`INSERT OR IGNORE`/`DETACH` sequence above) — so a given worker's
  contribution either lands completely or not at all; a failure never leaves the target database with half
  of one worker's messages merged and half missing. Attachment-directory copying is a separate,
  best-effort step per file (already idempotent via content-addressed skip-if-exists), so it can simply be
  re-run.
- **No cross-run resume beyond retrying a whole worker:** unlike `store-in-gmail`'s `gmail_store_state`
  table, there's no persistent bookkeeping of "which workers already merged" across separate
  `import-pst --parallel N` invocations. A crashed run should be retried in full. This is an accepted
  simplification — see [Out of Scope](#out-of-scope).

---

## CLI Design

- New `--parallel N` flag on `import-pst` (and its `import-outlook` alias). Omitted or `N=1` keeps today's
  single-process behavior byte-for-byte unchanged — this is strictly additive.
- Two new flags, `--worker-nid-start`/`--worker-nid-end`, exist only to let the orchestrator re-invoke
  itself as a worker. They're accepted by the argument parser but intentionally left out of `--help` output
  and `docs/cli-spec.md`'s public command reference, since they're not meant for direct end-user use.

---

## Testing Strategy

- **Unit tests** (fast, deterministic, part of the normal suite):
  - Partition logic: exact chunk boundaries for various `(message_count, N)` combinations, including
    `N=1`, `N > message_count`, and non-evenly-divisible counts.
  - Merge logic: small synthetic worker databases and attachment directories (a handful of rows each,
    including a deliberately duplicate label across two workers) merged into a fresh target, asserting the
    target's row counts and content match expectations, including the FTS rebuild finding every merged
    message.
- **Manual end-to-end validation** (mirrors T0020's own approach — too large/slow for the automated suite):
  run `import-pst --parallel N` against the real `anubex-outlook-backup.pst`, and compare message/attachment
  counts plus a `scripts/local-roundtrip-test.py` comparison against a plain single-process run of the same
  file, to prove the parallel path produces identical results.

---

## When To Revisit

Treat this as backlog, not urgent, unless a real archive on hand would push the current single-process time
(50.8 minutes for 26 GB / 186,475 messages, post-FTS5-fix) past roughly 3–4 hours — a rough proxy for that
is an archive around 4× today's largest, i.e. in the neighborhood of 100 GB or 750,000 messages. If such an
archive turns up, this document's design is implementation-ready; re-verify the worker-entry-point and
merge-logic decisions still hold (in particular, re-check the FTS5 rebuild's own scaling — a 4×-larger
merged `messages` table means a 4×-larger rebuild too) before starting.

---

## Out of Scope

- Parallelizing `import-thunderbird` — PST is the motivating, much larger case here; revisit separately if
  this proves valuable and Thunderbird archives of comparable size turn up.
- Cross-machine/distributed parallelism — single-machine, multi-process only.
- Making this the default for `import-pst` — stays an explicit opt-in flag given the added complexity and
  new failure modes versus the plain single-process path.
- Cross-run resume of a partially-merged parallel run (see [Failure Handling](#failure-handling)) — a
  failed run is retried in full rather than resumed worker-by-worker.
