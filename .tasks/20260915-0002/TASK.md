# P22: Reuse HTTP connections and reduce broker polling traffic

- STATUS: PENDING
- PRIORITY: 2
- DEPENDS: [P21](../20260915-0001/TASK.md), [P17](../20260912-0004/TASK.md)

## Goal

Reuse HTTP connections and reduce repeated requests while broker jobs wait.

## Finding from the 2026-09-15 performance review

Every method in `app/services/http/__init__.py` creates and closes its own
`aiohttp.ClientSession`. `app/services/broker.py` polls each pending task once
per second, creating a fresh session for every poll. Pending jobs therefore
multiply connection setup and broker request traffic.

## Plan

- [ ] Manage reusable sessions within the persistent event loop, with explicit
      startup and shutdown and bounded connection pools.
- [ ] Preserve request headers, timeout behavior, and error handling. Prevent
      cookies or authentication state from leaking between unrelated feeds.
- [ ] Check broker support for batched results or long polling. If unavailable,
      use bounded adaptive polling and record the completion-latency tradeoff.
- [ ] Preserve each job's deadline, cancellation, failure, and result semantics.
- [ ] Measure accepted connections and request counts against a local HTTP
      server for repeated requests and multiple pending jobs before and after.
- [ ] Add integration coverage for connection reuse, cleanup, and successful and
      failed broker jobs without asserting private helper calls.
- [ ] Preserve existing tests and their integration scope. Run `make lint` and
      `make test`, plus relevant integration checks.

## Definition of done

Repeated requests reuse connections, sessions close cleanly, and pending jobs
generate less polling traffic with a documented bound on detection delay.
