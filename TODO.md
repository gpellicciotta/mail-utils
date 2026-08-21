# TODO

Ordered by priority.

1. Ensure consisting format for output messages
   When running `import`, I get lines like:
   ```
   2026-08-21 08:52:56 UTC [INFO] Starting mail_utils Thunderbird import from data\personal-email-backup.pcv
   2026-08-21 08:53:01 UTC [INFO] Thunderbird import progress: 50 messages indexed so far
   ```
   When running `stats`, the lines don't have a timestamp message prefix:
   ```
   Database:         data\thunderbird.db
   Total messages:   2595
   Distinct threads: 0
   ```
   When running `export`, the lines look like:
   ```
   Filter: 'to:jef' (84 matching messages)
   Exported 84 messages to exports\thunderbird-md
   ```
   For overall consistency, ensure:
   - on the console there are never timestamps (but there are in a log file and all messages should also end up in a mail-utils.log)
   - all main operations (stats, import, export, schedule, unschedule) should start with a message what is about to be done
   - then add the options chosen (path the DB, filter, ...) on follow-up lines
   - when showing progress messages, try to show a percentage and show how much time has been spent
   - Finish with a clear result, including how many messages were handled (if relevant) and how much time the full run has taken
   Everything sent to the console, should also end up in the log file, but with the timestamp prefix. 

2. Decide whether the src/pst folder should better (for consistency) be renamed outlook

3. Come up with 3 more ideas to extending/improving this project

