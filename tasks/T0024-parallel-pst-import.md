# T0024: Parallel multi-process import for very large PST archives

- **Status:** active
- **Owner:** @claude
- **Started:** 2026-09-02
- **Branch:** task/T0024-parallel-pst-import
- **Worktree:** ./work/T0024-parallel-pst-import

## Goal

Add an opt-in parallel-import mode to `import-pst` that partitions a large archive's messages across N
worker subprocesses - each parsing its own slice into its own throwaway database and attachment store -
then merges the N partial results into the target `--db` directory, to cut wall-clock time for very large
archives beyond what a single process can achieve.

## Scope

- Discovered while working **T0020**: the ~26 GB `anubex-outlook-backup.pst` import was taking 30+ hours
  and visibly slowing down over time. Root-caused directly in T0020's own branch (not this task) to a
  real, separate bug - `db.py`'s `upsert_message`/`upsert_addresses`/`upsert_attachments` committing on
  every single call (3 fsync-backed commits per message) with no WAL mode, against a database that grew
  to several GB. That fix (batched commits + `journal_mode=WAL`) already landed in T0020's branch.
- **This task is for further speedup on top of that fix**, via true multi-process parallelism - see
  Dependencies for how its priority should be judged once the batching fix's real-world speedup is known.
- New `--parallel N` flag on `import-pst`:
  - Pre-scan via the existing `walk_folders()` (already cheap - structural only, no per-message parsing)
    to enumerate every `message_nid` across all folders.
  - Partition that flat list into N contiguous, roughly-equal chunks.
  - Spawn N worker subprocesses, each running the existing per-message import loop (unchanged) against
    its own slice, its own throwaway SQLite database, and its own throwaway attachment store directory -
    SQLite does not support safe concurrent writers to one file from multiple OS processes, so each
    worker needs full isolation, not shared state.
  - Once every worker exits successfully, merge the N partial databases into the target `--db`:
    `messages`/`message_addresses`/`attachments`/`labels` via `ATTACH DATABASE` + `INSERT OR IGNORE`
    (partitions are disjoint by message id, so no real conflicts are expected in practice), then rebuild
    the target's FTS5 index from the merged `messages` table rather than attempting to merge FTS5
    segments directly.
  - Merge each worker's attachment directory into the target's: content-addressed by `content_sha256`,
    so copying any file that doesn't already exist at the target path is safe and idempotent.
  - Clean up (delete) the N worker directories once the merge is verified.
- Reuse all existing parsing/upsert code unchanged - this is purely a new orchestration layer (partition +
  spawn + merge) around the existing single-process import loop, not a rewrite of the PST parser.

## Out of Scope

- Parallelizing `import-thunderbird` - PST is the motivating, much larger case here; revisit separately if
  this proves valuable and Thunderbird archives of comparable size turn up.
- Cross-machine/distributed parallelism - single-machine, multi-process only.
- Making this the default for `import-pst` - stays an explicit opt-in flag given the added complexity and
  new failure modes (a worker crashing mid-slice, partial-merge cleanup, etc.) versus the plain single-
  process path.

## Dependencies

Spun off from **T0020** (full-archive-import-and-eml-roundtrip), whose own branch already contains the
batching/WAL fix. **Before investing further in this task**, measure that fix's real-world speedup against
the actual `anubex-outlook-backup.pst` file (in progress as of this task's creation) - if it alone gets the
big file's import down to a few hours, the added complexity and new failure surface of multi-process
parallelism may not be worth it for the archives on hand today, and this task should stay backlog-priority
(still worth having for future, larger archives) rather than urgent.

## Approach

1. Wait for T0020's batching/WAL fix to be measured against the real 26 GB file; record the result here.
2. Design the worker entry point: either a new hidden CLI action (`import-pst` gains internal
   `--nid-range`/`--worker-index`/`--worker-count`-style plumbing) invoked as a subprocess per worker, or a
   pure-Python `multiprocessing`/`subprocess` orchestration function that calls the existing import
   machinery directly with a pre-filtered `message_nids` list - prefer whichever keeps the existing
   single-process code path completely unchanged and the new orchestration layer isolated and testable on
   its own.
3. Implement the merge step as its own testable function (`merge_partial_databases` or similar) - unit
   test it against small synthetic partial databases (attachments included) before trusting it against
   real multi-GB output.
4. Wire up `--parallel N` on `import-pst`, defaulting to today's single-process behavior when omitted.
5. Validate end-to-end against the real `anubex-outlook-backup.pst`, comparing message/attachment counts
   and a local round-trip comparison (`scripts/local-roundtrip-test.py`, from T0020) against a plain
   single-process run of the same file, to prove the parallel path produces identical results.

## Implementation Checklist

- [ ] T0020's batching/WAL fix measured against the real big file; priority of this task reassessed
- [ ] Worker entry point designed and implemented
- [ ] Partition logic (`walk_folders()` pre-scan + N-way chunking) implemented and unit-tested
- [ ] Merge logic (databases + attachment directories + FTS5 rebuild) implemented and unit-tested
- [ ] `--parallel N` wired up on `import-pst`, single-process behavior unchanged when omitted
- [ ] Validated end-to-end against the real big file (counts + local round-trip comparison match a
      single-process run)

## Test Strategy

Unit tests for partitioning and merge logic against small synthetic databases/attachment directories
(fast, deterministic). The real end-to-end validation against `anubex-outlook-backup.pst` is manual,
mirroring T0020's own approach - too large/slow for the automated suite.

## Completion Criteria

- `import-pst --parallel N` produces a database and attachment store identical (per
  `scripts/local-roundtrip-test.py`-style comparison) to what a plain single-process `import-pst` run of
  the same file produces.
- Measured wall-clock improvement recorded against the real `anubex-outlook-backup.pst` file.

## Progress Log

- 2026-09-02: Claimed, worktree/branch created. Spun off from T0020 per the user's request while
  investigating why the big-file import kept slowing down. T0020's own branch already fixed the actual
  root cause found (commit-per-row, no WAL mode); this task covers the separate, larger idea (multi-
  process parallelism) the user asked to pursue in parallel regardless of that fix's outcome.

## Validation Record

## Completion Record
