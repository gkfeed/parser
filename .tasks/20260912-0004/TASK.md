# P17: Enforce HTTP status and request deadlines

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: none

## Goal

Make parser and broker HTTP calls fail promptly when a server returns an error
status or stops responding.

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
- [ ] Run `make lint` and `make test`.

## Definition of done

Parser and broker callers never treat an HTTP error page as valid data, and an
unresponsive request cannot outlive its configured deadline.
