# TODO

An overview of all tasks and their planning.

> Tasks are listed by milestone.
> See [coordinating-work-guidelines](https://github.com/gpellicciotta/dev-guidelines/blob/main/guidelines/coordinating-work-guidelines.md) for the full coordination protocol.
>
> Status: `[ ]` available · `[~]` active · `[!]` blocked · `[?]` needs-review
> Owner: `@name` shown only when active/blocked/needs-review.
> Dependencies: `(needs Tnnnn)` shown only when unresolved.

**Next ID:** 0010

---

## Next Milestone

---

### Backlog

- [~] T0004 capture-attachment-content  @claude
- [ ] A0008 Reconcile the minimum supported Python version across pyproject.toml, docs/devops.md, and CI
      pyproject.toml's `requires-python` says `>=3.10`, docs/devops.md's "Local Environment & Dependencies"
      section says "Python 3.11+", and `.github/workflows` actually only runs CI against 3.11 - so 3.10 is
      never verified despite being formally allowed. Found while updating docs/devops.md for A0007. Pick
      one minimum (3.10 or 3.11) and make all three agree.
- [ ] A0006 Verify store-in-gmail end-to-end against a real (disposable/sandbox) Gmail account
      T0002 shipped with only mocked-service unit tests (no real Gmail account touched in CI, by design).
      Before relying on store-in-gmail against any real mailbox, run it end-to-end against a disposable or
      sandbox Gmail account: confirm the OAuth consent flow requests exactly gmail.insert + gmail.labels
      on top of the existing gmail.readonly scope, that messages land with correct dates/labels/tracking
      label, that --max-messages + rerun actually resumes cleanly, and that throttling/backoff behave
      sanely under a real (not mocked) API. Flagged as the user's own responsibility in T0002's Validation
      Record, not something the automated test suite can cover.
