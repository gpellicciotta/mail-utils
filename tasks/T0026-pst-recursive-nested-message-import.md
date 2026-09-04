---
id: T0026
owner: "@claude"
needs: []
branch: task/T0026-pst-recursive-nested-message-import
worktree: ./work/T0026-pst-recursive-nested-message-import
status: completed
started: 2026-09-02
ended: 2026-09-02
---

# T0026: Make `import-pst --recursive` actually extract nested messages

## Goals
Enable recursive extraction and indexing of nested embedded message attachments in Outlook PST archives.
Match recursive extraction capabilities already available for Gmail and Thunderbird import pipelines.

## Task Execution Steps

- [x] **[Read]**      Investigate MAPI embedded message attachment structures and subnode resolution in MS-PST.
- [x] **[Implement]** Implement is_embedded_message_attachment check and fetch_embedded_message in messages module.
- [x] **[Implement]** Update import-pst CLI pipeline to recursively process and upsert nested embedded messages.
- [x] **[Verify]**    Verify unit tests in test_pst_integration.py and test against real archive with embedded messages.
- [x] **[Doc]**       Update task documentation and record completion in execution logs.

## Execution Log

- [2026-09-02] **[Verify]**
  Passed 257 unit tests and verified extraction of 10 embedded messages from anubex-friends-email.pst.

- [2026-09-02] **[Complete]**
  Shipped recursive PST message extraction and integrated changes into archive import workflows.
