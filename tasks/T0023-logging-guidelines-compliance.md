---
id: T0023
owner: "@antigravity"
needs: []
branch: task/T0023-logging-guidelines-compliance
worktree: ./work/T0023-logging-guidelines-compliance
status: completed
started: 2026-09-04
ended: 2026-09-04
---

# T0023: Ensure compliance with the updated logging guidelines

## Goals
Update mail-utils logging configuration to comply with general guidelines.
Provide standard timestamping, 5-character padded severity tags, multi-line indentation, --log-file option, and startup/completion summaries.

## Task Execution Steps

- [x] **[Read]**      Review general guidelines for logging requirements and existing CLI logging implementations.
- [x] **[Implement]** Update _UTCFormatter and logger setup to produce padded severity indicators and multi-line alignment.
- [x] **[Implement]** Add --log-file option across CLI commands and support dynamic log target configuration.
- [x] **[Implement]** Add startup and completion duration logging adhering to the guidelines.
- [x] **[Verify]**    Verify unit tests and inspect log file and console outputs for format compliance.
- [x] **[Doc]**       Update documentation and CLI specifications to document --log-file and logging format.

## Execution Log

- [2026-09-04] **[Read]**
  Audited current logging setup in cli.py against general guidelines.

- [2026-09-04] **[Implement]**
  Implemented format_severity_indicator, _FileFormatter, and _ConsoleFormatter with multi-line indentation.
  Added --log-file and --debug CLI flags across all subcommands.

- [2026-09-04] **[Verify]**
  Verified full test suite passes with 271 unit tests covering logging formatters and CLI flags.

- [2026-09-04] **[Doc]**
  Updated CLI specification and CHANGELOG.md with new flags and logging details.

- [2026-09-04] **[Complete]**
  Aligned mail-utils logging formatting and CLI options with general guidelines.
