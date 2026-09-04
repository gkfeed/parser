# P06: Isolate feed failures and back off on database outages

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [P05](../20260904-1005/TASK.md)

## Goal

Keep one bad feed from stopping its peers while treating a database outage as
a system-wide failure.

## Plan

- [ ] Contain fetch and parse failures inside the affected feed task.
- [ ] Let PostgreSQL connection and transaction failures stop the current
      cycle.
- [ ] Retry failed database cycles after `1, 2, 5, 10, 30, 60` seconds.
- [ ] Continue retrying once per minute after the sequence is exhausted.
- [ ] Reset database backoff after a successful database cycle.
- [ ] Do not add `pool_pre_ping`.
- [ ] Test feed isolation and the backoff sequence without real sleeps.
- [ ] Run `make lint` and `make test`.

## Definition of done

A feed error affects one feed. A database outage stops the cycle and retries
without a reconnect loop.
