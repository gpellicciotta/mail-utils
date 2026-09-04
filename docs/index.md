# Documentation Index

Welcome to the `mail-utils` technical documentation.

## Core Documentation
- [`requirements.md`](requirements.md) — High-level goals, functional requirements, and technical invariants.
- [`cli-spec.md`](cli-spec.md) — Complete command-line interface specification and filter grammar.
- [`devops.md`](devops.md) — Setup, testing, linting, packaging, and CI/CD guide.
- [`tutorial.md`](tutorial.md) — First-time user walkthrough for importing, searching, stats, exporting, and scheduling.
- [`emails-formats.md`](emails-formats.md) — Reference on single-message and mailbox storage formats (.eml, .msg, .mbox, .pst).
- [`database-design.md`](database-design.md) — Why the SQLite schema's tables are shaped the way they are.

## Design & Technical Plans
- [`specs/gmail-store-test-plan.md`](specs/gmail-store-test-plan.md) — Comprehensive test plan for store-in-gmail live validation.
- [`pst-support-plan.md`](pst-support-plan.md) — Architecture and specification for the pure-Python `[MS-PST]` parser.
- [`thunderbird-import-plan.md`](thunderbird-import-plan.md) — Architecture and format handling for Thunderbird PCV/Mbox archives.
- [`eml-export-support-plan.md`](eml-export-support-plan.md) — Design notes for standard RFC 5322 `.eml` message export.
- [`reverse-import-plan.md`](reverse-import-plan.md) — Feasibility study for restoring exported mail back into Gmail/Outlook/Thunderbird.
- [`parallel-pst-import-plan.md`](parallel-pst-import-plan.md) — Design for an opt-in multi-process `import-pst --parallel N` mode (backlog, not yet built).

## Root References
- [`README.md`](../README.md) — Project overview and quickstart links.
- [`LICENSE.md`](../LICENSE.md) — Project license.
- [`CHANGELOG.md`](../CHANGELOG.md) — Version history and release notes.
- [`TODO.md`](../TODO.md) — Backlog and upcoming roadmap.
- [Development Guidelines](https://github.com/gpellicciotta/dev-guidelines) — Cross-project development guidelines.
