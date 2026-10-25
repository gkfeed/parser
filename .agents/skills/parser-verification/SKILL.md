---
name: parser-verification
description: Use after any code change in this repository, before marking the task done.
---

# Parser verification

After each code change, review the task's staged and unstaged diff, relevant callers, and parser hooks. Follow `AGENTS.md`. Fix issues within scope and leave unrelated changes intact.

## Review

- Put readability first. Keep parsers compact. Reject refactors that make code harder to follow, even if they reduce DOM lookups, duplication, or nesting. Reuse local values only when this keeps the flow clear; avoid extra state or cleanup just to share a node.
- Prefer guard clauses and early returns. Preserve validation, selectors, fallback order, item identity, transactions, retries, cancellation, and resource cleanup. Keep deeper nesting when it is clearer or necessary for correct behavior.
- Raise on failed requests, unexpected HTTP errors, malformed pages, and invalid required fields. Distinguish failures from confirmed empty feeds, cache misses, and optional data. Status-returning APIs may leave status handling to callers.
- Catch expected failures narrowly and preserve causes. Raise when all fallbacks fail. Worker boundaries may catch errors to report explicit broker failures; cleanup must preserve the original error. Check Selenium recovery before changing `quit()` suppression.
- Reuse existing services and extensions. Keep external clients in services, shared feed-dependent behavior in parser extensions, and stateless transformations in utils. Check MRO when changing inheritance. Extract a helper or abstraction only when it makes the code clearer.

Scan changed Python files for nesting:

```sh
python .agents/skills/parser-verification/scripts/check_nesting.py <changed-python-files>
```

Review depth-3 candidates manually, including affected existing blocks. The scanner misses expressions and callbacks; its exit status is not a verification result.

## Validate and finish

Run `make lint`, then `make test`. Reuse checks if no later code changes invalidate them. `make test` excludes live integration tests; run `make test-integration` when relevant and supported by the environment.

Read existing tests to understand behavior. Do not change them or add implementation-coupled tests; avoid excessive monkeypatching.

Return a brief result with validation and unresolved blockers. Do not create audit reports or backlog files.
