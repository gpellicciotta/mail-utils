# T0024: Parallel multi-process import for very large PST archives

- **Status:** available
- **Owner:** none
- **Started:** —
- **Branch:** —
- **Worktree:** —

## Goal

Add an opt-in parallel-import mode to `import-pst` that partitions a large archive's messages across N
worker subprocesses - each parsing its own slice into its own throwaway database and attachment store -
then merges the N partial results into the target `--db` directory, to cut wall-clock time for very large
archives beyond what a single process can achieve.

Full design (architecture, worker entry point, partition/merge logic, failure handling, testing strategy):
see [`docs/parallel-pst-import-plan.md`](../docs/parallel-pst-import-plan.md).

## Scope

- Discovered while working **T0020**: the ~26 GB `anubex-outlook-backup.pst` import was taking 30+ hours
  and visibly slowing down over time.
- **Investigated, not implemented.** The real bottleneck turned out to be FTS5 index fragmentation from
  per-message incremental delete+insert cycles, fixed on T0020's branch by doing one bulk FTS rebuild after
  import instead of per-message maintenance. With that fix, the real 26 GB / 186,475-message archive now
  imports single-process in **50.8 minutes** - well under the threshold that made this task feel urgent.
- **Decision needed, not yet made:** whether multi-process parallelism is worth building at all, given the
  single-process fix already handles every archive currently on hand. Kept in the Backlog rather than
  cancelled, since a future, substantially larger archive could still make it worthwhile - see the design
  doc's "When To Revisit" section for a concrete size threshold.
- Reuse all existing parsing/upsert code unchanged if built - this stays purely a new orchestration layer
  (partition + spawn + merge) around the existing single-process import loop, not a rewrite of the PST
  parser.

## Out of Scope

See [`docs/parallel-pst-import-plan.md`](../docs/parallel-pst-import-plan.md)'s "Out of Scope" section.

## Dependencies

Spun off from **T0020** (full-archive-import-and-eml-roundtrip), whose branch contains the FTS5 fix that
resolved the immediate need. No outstanding dependency - this task itself is now blocked only on a human
decision of whether to build it.

## Implementation Checklist

- [x] T0020's fix measured against the real big file; priority of this task reassessed - see Progress Log
- [x] Full design documented - see `docs/parallel-pst-import-plan.md`
- [ ] **Decision:** build this, or leave it backlogged/cancel it - pending
- [ ] Worker entry point implemented (if decision is to build)
- [ ] Partition logic implemented and unit-tested (if decision is to build)
- [ ] Merge logic implemented and unit-tested (if decision is to build)
- [ ] `--parallel N` wired up on `import-pst`, single-process behavior unchanged when omitted (if decision is to build)
- [ ] Validated end-to-end against a real large archive (if decision is to build)

## Test Strategy

See `docs/parallel-pst-import-plan.md`'s "Testing Strategy" section.

## Completion Criteria

- A human decision recorded on whether to build this at all.
- If built: `import-pst --parallel N` produces a database and attachment store identical (per
  `scripts/local-roundtrip-test.py`-style comparison) to what a plain single-process `import-pst` run of
  the same file produces, with a measured wall-clock improvement against a real large archive.

## Progress Log

- 2026-09-02: Claimed, worktree/branch created. Spun off from T0020 per the user's request while
  investigating why the big-file import kept slowing down.
- 2026-09-02: Investigated the real cause instead - FTS5 index fragmentation, not raw single-process
  throughput. Fixed on T0020's branch. Re-ran the real `anubex-outlook-backup.pst` (~26 GB, 186,475
  messages) end to end: 50.8 minutes total, well under the urgency threshold. No parallel-import
  implementation work done.
- 2026-09-02: Per user request, wrote the full design (`docs/parallel-pst-import-plan.md`) so it's
  implementation-ready if a future archive justifies it, and moved this task back to the Backlog pending a
  decision on whether to build it at all. Worktree/branch released - a fresh one is created via the normal
  Claim Protocol if this task is picked up again.

## Validation Record

## Completion Record
