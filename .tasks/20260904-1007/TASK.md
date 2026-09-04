# P07: Pause between dispatch cycles

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: [P04](../20260904-1004/TASK.md), [P06](../20260904-1006/TASK.md)

## Goal

Stop dispatcher from polling the database in a tight loop.

## Plan

- [ ] Wait 60 seconds after a complete successful cycle.
- [ ] Keep cycles sequential.
- [ ] Keep the existing one-second feed task stagger.
- [ ] Do not add a semaphore or derive sleep from `valid_for`.
- [ ] Use P06 database backoff instead of the normal pause after a database
      failure.
- [ ] Test cycle timing with a fake clock or patched sleep.
- [ ] Run `make lint` and `make test`.

## Definition of done

Dispatcher waits one minute after each completed cycle and never overlaps
cycles.
