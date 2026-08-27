# TODO

An overview of all tasks and their planning.

> Tasks are listed by milestone.
> See [coordinating-work-guidelines](https://github.com/gpellicciotta/dev-guidelines/blob/main/guidelines/coordinating-work-guidelines.md) for the full coordination protocol.
>
> Status: `[ ]` available · `[~]` active · `[!]` blocked · `[?]` needs-review
> Owner: `@name` shown only when active/blocked/needs-review.
> Dependencies: `(needs Tnnnn)` shown only when unresolved.

**Next ID:** 0006

---

## Next Milestone

- [ ] A0003 Ensure all scripts comply with the guidelines

---

### Backlog

- [~] T0002 gmail-restore-import @claude
- [ ] T0004 capture-attachment-content
- [ ] A0005 Fix unhandled sqlite3.OperationalError crash in import-pst/import-thunderbird/store-in-gmail
      Root cause: init_db() calls sqlite3.connect(db_path) without ensuring db_path's parent directory
      (data/ by default) exists first, so a truly fresh checkout with no data/ dir yet crashes with a raw
      traceback instead of a friendly error. import-gmail avoids this only because it happens to check
      credentials before touching the database. Fix: create the parent directory (or give a friendly
      "directory not found" message) in init_db() or _resolve_db_path() before connecting. Found while
      building T0002 (store-in-gmail).
