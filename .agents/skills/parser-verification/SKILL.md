---
name: parser-verification
description: Use after any code change in this repository, before marking the task done.
---

# Parser verification

Run this check automatically after any code change, including features, fixes, and refactoring. Review your changes, correct problems within the task's scope, and validate the result before handing the work back. Follow `AGENTS.md` and `GEMINI.md`. Do not create audit reports or backlog files.

## Check the changed code

Review the diff for the current task, including staged and unstaged changes. Read affected functions, callers, and inherited parser hooks. Keep unrelated existing changes intact. Expand the review only where needed to understand the fix's behavior.

### Keep parsers readable

Readability takes priority over DOM reuse, deduplication, and lower nesting counts. Keep parsers compact and reject refactors that make the parsing path harder to follow. Preserve validation, selectors, fallback order, item identity, and failure behavior.

Reuse an already extracted DOM node through a local variable when it makes the code clearer. A small repeated lookup can be preferable to extra state, cleanup, parameter plumbing, or a parallel parsing path. Byte caching does not cache DOM trees, and calling a helper twice does not reuse its result; neither fact alone justifies a refactor.

### Keep control flow flat

Avoid three nested control-flow blocks. Prefer guard clauses, early returns, and `continue`. Extract a complete operation into a named method when that makes the caller easier to understand. Preserve transaction boundaries, resource lifetimes, retries, cancellation, and cleanup.

Run the bundled scanner on changed Python files from the repository root:

```sh
python <skill-dir>/scripts/check_nesting.py <changed-python-files>
```

Replace the placeholders with this skill's directory and actual file paths. The scanner counts `if`, loops, `try`, `with`, `match`, and their async variants. It treats `elif` as the same level and starts a new count inside each function. It lists the first point reaching depth 3 in each branch. Review those candidates manually, including pre-existing nesting affected by the change. Also inspect comprehensions, conditional expressions, and callbacks, which the scanner does not measure. A successful scanner exit does not mean the code passed verification.

Flatten nesting introduced or made harder to follow by the change. If a third level is clearer or must remain to preserve behavior, keep the reason explicit. Do not replace readable blocks with dense expressions to reduce indentation.

### Raise on failure

Trace error paths to the public result, especially `except`, `suppress`, `pass`, empty returns, `continue`, `.get()`, `or`, and `gather(return_exceptions=True)`.

- Network failures, unexpected HTTP error responses, malformed pages, and invalid required fields must raise an appropriate exception. Reuse `HttpRequestError`, `FeedUnavailable`, `ValueError`, or `BrokerError` where suitable. Preserve causes with `raise ... from exc`.
- Missing expected selectors do not prove a feed is empty. Validate the page and required data before returning items or caching a response. Keep confirmed empty feeds distinguishable from failed parsing.
- A fallback must raise after all sources fail. Catch expected failures narrowly so programming errors do not become empty results or retries. Logging an error does not make the operation successful.
- Check HTTP status handling as well as connection failures. Status-returning methods may delegate status handling to callers; methods returning successful data must reject unexpected error responses.
- Respect deliberate absence contracts, such as no queued task, cache miss, or an optional field. For optional enrichment, verify that fallback data is sufficient and degradation is observable.
- Worker and dispatcher boundaries may catch exceptions when they submit an explicit failure to the broker. Cleanup must preserve the original error. Inspect Selenium recovery before changing suppression around `quit()`.

### Reuse the right abstraction

Look for existing code before adding a service or extension.

- `app/parsers/` coordinates source-specific extraction and creates `Item` objects.
- `app/services/` owns external clients, HTTP, Selenium, uploads, caching, and persistence. Keep clients independent of concrete feed classes. Reuse services such as `ImageService` instead of copying their behavior into a parser.
- `app/extensions/parsers/` owns shared parser behavior that needs `feed`, `data`, or parser hooks. Reuse HTTP, Selenium, post-to-item, cache, and hash extensions. Check MRO and `super()` when changing inheritance.
- `app/utils/` holds small stateless transformations without I/O. An operation private to one parser usually belongs in a local method.

Extract code when it removes actual duplication or separates a clear responsibility. Keep inputs, outputs, and failure behavior explicit. Avoid a generic service or new mixin merely to move a few lines. Keep any refactoring proportional to the change.

## Finish the change

Correct issues introduced or exposed by your changes when necessary for the intended behavior to work. Do not turn verification into an unrelated repository cleanup.

Run `make lint`, then `make test` after the final code changes. Reuse completed checks when no subsequent code changes invalidate them. `make test` excludes the `integration` marker and does not verify live external services; use `make test-integration` only when relevant and the environment supports it.

Read existing tests to understand behavior. Do not change them or add implementation-coupled unit tests. Preserve the repository's integration testing approach and avoid excessive monkeypatching.

Return the completed change with a brief validation result. Mention any unresolved blocker honestly. Do not generate a separate verification report.
