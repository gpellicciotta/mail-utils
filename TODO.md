# TODO

An overview of all tasks and their planning.

> Tasks are listed by milestone.
> See [coordinating-work-guidelines](https://github.com/gpellicciotta/dev-guidelines/blob/main/guidelines/coordinating-work-guidelines.md) for the full coordination protocol.
>
> Status: `[ ]` available · `[~]` active · `[!]` blocked · `[?]` needs-review
> Owner: `@name` shown only when active/blocked/needs-review.
> Dependencies: `(needs Tnnnn)` shown only when unresolved.

**Next ID:** 0042

---

## Next Milestone

- [ ] T0041 Finalize the work done as part of T0020 and T0033: further condense the summary of the work in docs/specs/gmail-full-archive-migration-report.md, then ensure all code changes made as part of these 2 tasks were merged into the main branch. If yes: drop the task branches and worktrees entirely. 
  As to "condense the summary", I mean the following:
  - Remove all information from gmail-full-archive-migration-report.md that is no longer usable in the future (e.g. references to the worktrees that will no longer exist)
  - Also further **condense** the text to the essential info:
    - Source database provenance (T0020): just name this "Inputs" and list the 4 original files used
    - Add a new "Verification" section mentioning the types of verification that were done, very briefly
    - Performance: just give the final performance: full elapsed, throughput and number of messages. Only explain the stored+skipped in a small side-note
    - Error catalogue and Attachment-stripped retry: bundle in "Issues" section and just list all distinct issue types and how they have been handled:, e.g. "Issue: attachments got blocked by Google. Affected messages: 417 messages. Approach taken: all were succesfully imported without attachment. See xxx for the full list of messages as the attachments are still available locally" OR "Issue: some sender email addresses didn't comply with RFC and were not accepted by Gmail; Affected messages: ~2003'Approach taken: x were fixed by improving our parsing and making them RFC complient but y needed to be replaced by unknown@invalid.com and z were dropped entirely."
  Once done: commit.  

- [ ] T0040 Update mail-utils to comply with latest sets of guidelines and be as close as possible to the existing python-project-template.

### Backlog

*(Currently no tasks)*
