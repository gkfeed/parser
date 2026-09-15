# P21: Process light-worker feeds with bounded concurrency

- STATUS: PENDING
- PRIORITY: 1
- DEPENDS: none

## Goal

Allow unrelated light feeds to progress while another feed waits for I/O.

## Finding from the 2026-09-15 performance review

`app/run/worker_light.py` and `app/run/worker_heavy.py` run each task to completion
before checking the next parser type. `app/core/worker.py` also sleeps one second
before every queue check, including empty queues. A slow feed delays every parser
type handled by the same worker. `app/workers/youtube.py` calls synchronous
yt-dlp extraction directly from an async function.

## Plan

- [ ] Use one persistent event loop per worker process.
- [ ] Add a configurable, bounded number of concurrent light-feed jobs and fair
      queue polling so busy parser types cannot starve others.
- [ ] Apply idle polling backoff without adding a fixed delay before every job.
- [ ] Move blocking extraction off the event loop and define shutdown behavior
      for in-flight extraction and broker submissions.
- [ ] Keep heavy browser work serialized until browser isolation is supported.
- [ ] Add integration coverage through worker and broker behavior using a local
      broker fixture and controlled slow and fast feeds. Verify that fast feeds
      complete while a slow feed is pending and that concurrency stays bounded.
- [ ] Preserve existing tests and their integration scope. Run `make lint` and
      `make test`, plus relevant integration checks.

## Definition of done

A slow light feed does not block unrelated light feeds. Worker concurrency and
idle polling remain bounded, and shutdown closes worker resources cleanly.
