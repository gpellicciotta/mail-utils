# TODO

Ordered by priority.

1. Extend command line interface with actions:
   - help: show help
   - update: update mails, importing them into the DB
   - stats: show current stats
   While doing this, rename main.py to cli.py, folding stats.py's logic
   in as the 'stats' subcommand.

2. Stored `date` is the raw, client-supplied `Date` header — not
   normalized, and not Gmail's own reliable server-side `internalDate`.
   Capture `internalDate` (returned by `messages.get`) alongside it for
   trustworthy chronological sorting.

3. Allow dumping all emails to the file system location, where each email
   becomes a markdown document with a header section with all meta-data.
   Do this with a new CLI command 'export'

4. Extend command line interface for 'update', 'export' and 'stats' to allow filtering/importing
   only messages with a certain label, a certain word in the subject or a certain name
   in the sender or recepient fields. Stay as close as possible to GMail filter syntax.
