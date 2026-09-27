# Phase 5 Operations

KiNoTch. Repository Base v0.4.0 is the current Surface Default Kit baseline. Base and
Runtime are not expanded merely because a reusable idea can be imagined.

## Operating rule

The normal loop is:

```text
active Project work
↓
observe a concrete need or failure
↓
sync Base only when that Project requires it
↓
verify the Project
↓
promote a repeated problem only when the same reason appears in independent repos
```

Do not batch-sync every repository, run periodic full audits, or create a new
Default, Surface, Runtime module, or Portable Contract for one repository's
convenience.

## Repository-local workflow

For an adopted repository, inspect `BASE_VERSION`, `CURRENT_STATE`, Git/worktree
state, and `DEFAULT` / `OVERRIDE` / `DISABLED` entries first. If synchronization
is justified, change only Base-managed files, preserve Project-owned files and
existing overrides, then run:

```text
doctor
base-check
Project test / build / verify
```

For a repository without `.kinotch/`, use a read-only shape probe first. Adopt
only when the reduction in repeated repository work is concrete; otherwise
record `N/A` or `NOT_ADOPTED` without treating it as unfinished work.

## State vocabulary

Repository operation state remains:

```text
ADOPTED / STAGED / NOT_ADOPTED / N/A
```

Default implementation state remains:

```text
DEFAULT / OVERRIDE / DISABLED
```

These are separate concepts. Existing PWA, CI, generated-data, native Windows,
API, Agent, and deployment implementations remain Project-owned `OVERRIDE`
when they fit their Project better than a generic Default.

## Current staged decisions

- `refil-viewer`: fix the Project-owned Vite failure first; Base does not fix
  the duplicate `pageIndex`.
- `standby-display`: keep PWA and generated-asset behavior as Project-owned
  overrides; classify root-hygiene differences when the Project is active.
- `SynTrail-LM`: wait for a clean user-owned worktree decision; keep Windows,
  CLI, and file I/O behavior as overrides.
- `dev_agent` and `IDS-Composit`: remain `NOT_ADOPTED` until active work gives
  a concrete adoption reason.
- Browser extensions and the listed inactive/N/A repositories do not receive a
  new Surface solely from this policy.

## Return conditions

Consider a Base change only for a clear Base bug, a security/data-loss issue,
the same failure in at least two independent repositories, repeated identical
manual setup, or a common problem that the current Defaults cannot safely
represent. Runtime remains provisional and is reconsidered only when the same
meaning, responsibility, lifecycle, and change reason recur across distinct
languages, Surfaces, and Projects.

Phase 5 has no requirement to make every repository adopted and no automatic
Phase 6 start condition. The Base succeeds when Projects can remain independent,
existing overrides are respected, and shared maintenance stays small.
