# P07: Pause between dispatch cycles

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [P04](../20260904-1004/TASK.md), [P06](../20260904-1006/TASK.md)

## Goal

Stop dispatcher from polling the database in a tight loop.

## Reproduction from the 2026-09-14 review

[The dispatch loop](../../app/run/dispatcher.py) immediately starts another cycle
when no feeds are due. The one-second pause in
[Dispatcher](../../app/core/dispatcher.py) only runs when a feed is scheduled.

With one feed whose `valid_for` was an hour in the future, the dispatcher ran
178 cycles and executed 354 SQL queries in 0.2 seconds against an in-memory
database. It also printed a log line for every cycle.

## Plan

- [ ] Wait 60 seconds after a complete successful cycle.
- [ ] Keep cycles sequential.
- [ ] Keep the existing one-second feed task stagger.
- [ ] Do not add a semaphore or derive sleep from `valid_for`.
- [ ] Use P06 database backoff instead of the normal pause after a database
      failure.
- [ ] Test cycle timing with a fake clock or patched sleep.
- [ ] Cover an empty feed list and a list containing only feeds with future
      `valid_for` values; neither case should repeatedly poll during the pause.
- [ ] Run `make lint` and `make test`.

## Definition of done

Dispatcher waits one minute after each completed cycle and never overlaps
cycles.
