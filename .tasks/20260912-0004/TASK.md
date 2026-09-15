# P17: Enforce HTTP status and request deadlines

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: none

## Goal

Make parser and broker HTTP calls fail promptly when a server returns an error
status or stops responding.

## Reproduction from the 2026-09-14 review

[HttpService](../../app/services/http/__init__.py) catches `ClientError`, but
aiohttp's total request deadline raises `TimeoutError`. That exception bypasses
the `HttpRequestError` to `BrokerError` conversion and escapes
[Dispatcher](../../app/core/dispatcher.py), aborting its task group.

Reproduced with a local HTTP server that immediately accepts an enqueue request
but delays the result response beyond a shortened client deadline. The dispatch
call raises an `ExceptionGroup` containing `TimeoutError` instead of scheduling
the affected feed for retry.

## Plan

- [ ] Define shared connection and total request timeouts for `HttpService`.
- [ ] Reject non-success HTTP responses before reading or decoding their bodies.
- [ ] Convert status, timeout, connection, invalid URL, and JSON decoding failures
      into `HttpRequestError` while preserving the original cause.
- [ ] Keep `get_status` able to return an HTTP status for callers that need to
      inspect it.
- [ ] Ensure the broker polling deadline still applies when one request stalls.
- [ ] Test successful responses, 4xx and 5xx responses, invalid JSON, and stalled
      requests through public service behavior.
- [ ] Verify that a broker HTTP timeout schedules the affected feed for retry
      without aborting the dispatch cycle or cancelling other feed requests.
- [ ] Coordinate feed failure handling with [P06](../20260904-1006/TASK.md).
- [ ] Run `make lint` and `make test`.

## Definition of done

Parser and broker callers never treat an HTTP error page as valid data, and an
unresponsive request cannot outlive its configured deadline.
Broker HTTP timeouts follow the normal feed retry path and do not terminate the
dispatcher.
