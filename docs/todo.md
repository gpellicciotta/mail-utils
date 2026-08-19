# TODO

Ordered by priority.

1. Ensure CC: and BCC: headers are also captured

2. Ensure recepient statistics can be calculated too: how many times sender, in To:, in CC:, in BCC:

3. Ensure the names and sizes of attachments are also captured

4. Extend command line interface with actions:
   - help: show help
   - update: update mails, importing them into the DB
   - stats: show current stats
   While doing this, rename main.py to cli.py, folding stats.py's logic
   in as the 'stats' subcommand.

5. Stored `date` is the raw, client-supplied `Date` header — not
   normalized, and not Gmail's own reliable server-side `internalDate`.
   Capture `internalDate` (returned by `messages.get`) alongside it for
   trustworthy chronological sorting.

6. Allow dumping all emails to the file system location, where each email
   becomes a markdown document with a header section with all meta-data.
   Do this with a new CLI command 'export'

7. Extend command line interface for 'update', 'export' and 'stats' to allow filtering/importing
   only messages with a certain label, a certain word in the subject or a certain name
   in the sender or recepient fields. Stay as close as possible to GMail filter syntax.
