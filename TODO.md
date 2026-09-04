# TODO

An overview of all tasks and their planning.

> Tasks are listed by milestone.
> See [coordinating-work-guidelines](https://github.com/gpellicciotta/dev-guidelines/blob/main/guidelines/coordinating-work-guidelines.md) for the full coordination protocol.
>
> Status: `[ ]` available · `[~]` active · `[!]` blocked · `[?]` needs-review
> Owner: `@name` shown only when active/blocked/needs-review.
> Dependencies: `(needs Tnnnn)` shown only when unresolved.

**Next ID:** 0034

---

## Next Milestone

- [ ] T0023 Ensure to comply with the updated logging guidelines.
- [ ] T0030 Plan a full store-in-gmail test run against the disposable tester.pellicciotta@gmail.com account, covering kill/resume of a long-running import and a curated subset covering every message T0020 found problematic.
- [ ] T0031 [needs: T0030] Execute the store-in-gmail test plan against tester.pellicciotta@gmail.com and make any small fixes or improvements it surfaces.
- [ ] T0032 [needs: T0031] Plan how to detect and recover from a store-in-gmail run against the real production account going wrong.
- [ ] T0033 [needs: T0032] Execute store-in-gmail for real against the full archive, invoking the back-off/recovery procedure if needed.

### Backlog

- [?] T0024 [owner: @gio] Parallel multi-process import for very large PST archives.

