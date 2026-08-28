# TODO

An overview of all tasks and their planning.

> Tasks are listed by milestone.
> See [coordinating-work-guidelines](https://github.com/gpellicciotta/dev-guidelines/blob/main/guidelines/coordinating-work-guidelines.md) for the full coordination protocol.
>
> Status: `[ ]` available · `[~]` active · `[!]` blocked · `[?]` needs-review
> Owner: `@name` shown only when active/blocked/needs-review.
> Dependencies: `(needs Tnnnn)` shown only when unresolved.

**Next ID:** 0014

---

## Next Milestone

- [ ] T0013 gmail-e2e-safety-and-rollout

### Backlog

- [ ] A0006 (needs T0013) Verify store-in-gmail end-to-end against a real (disposable/sandbox) Gmail account
      T0002 shipped with only mocked-service unit tests (no real Gmail account touched in CI, by design).
      Before relying on store-in-gmail against any real mailbox, run it end-to-end against a disposable or
      sandbox Gmail account: confirm the OAuth consent flow requests exactly gmail.insert + gmail.labels
      on top of the existing gmail.readonly scope, that messages land with correct dates/labels/tracking
      label, that --max-messages + rerun actually resumes cleanly, and that throttling/backoff behave
      sanely under a real (not mocked) API. Flagged as the user's own responsibility in T0002's Validation
      Record, not something the automated test suite can cover.
