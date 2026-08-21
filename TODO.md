# TODO

Ordered by priority.

1. Full-Text Search (FTS5) & Search Subcommand (`mail-utils search <query>`)
   - Add SQLite `FTS5` virtual table indexing over `subject`, `body_text`, `sender`, and `recipient`.
   - Add `mail-utils search "<query>"` command to print ranked results with search snippet excerpts, highlighted matches, and metadata.
   - Support boolean queries (`OR`, `NOT`, prefix matches) and `--db` / `--limit` flags.

2. Generic Mbox & Apple Mail Import (`mail-utils import-mbox` & `import-apple-mail`)
   - Support standalone single `.mbox` files (e.g. Google Takeout / Fastmail archives).
   - Support macOS Apple Mail directories (`~/Library/Mail/V*` with `.emlx` files and `.mbox` bundles).

3. Cross-Source Conversation Threading & Deduplication (`mail-utils dedupe` / `threads`)
   - Traverse `In-Reply-To` and `References` RFC 5322 headers to reconstruct conversation threads for Outlook and Thunderbird imports.
   - Detect identical messages across multiple archives/sources, merge labels, and report duplicate storage.




