# Camoufox decision and reproducible spike

Decision, 2026-10-25: **reject production adoption for now**. Keep Selenium.
Camoufox produced the same parser items, but did not improve success on either
selected feed and added browser startup time and another browser stack to operate.
This is a decision about the evidence below, not proof that Camoufox cannot help
another site or network. No production imports, dependencies, parser registration,
worker configuration, or Compose services change in this experiment.

## Evidence

HLTV's [Spirit feed](https://www.hltv.org/team/7020/spirit) has explicit Cloudflare
challenge handling and a WebDriver callback that waits for an upcoming-matches
headline. [Rezka's film feed](https://hdrezka.me/films/action/64700-major-grom-game-the-2024.html)
has explicit Anubis/browser-error handling and a five-second rendering delay.
These are challenge-prone candidates identified from the existing parser code;
neither was blocked during the final runs. There is no measured detection bypass
benefit to claim.

[results.json](results.json) contains every final per-attempt measurement and Item
snapshot. Each live cell below is three fresh client processes on 2026-10-25.
Time is the median from browser/client initialization through HTML extraction,
parser validation, Item creation, hashing, and cleanup. Memory is the largest
100 ms sampled sum of process-tree RSS, in MiB.

| Execution | Feed | Successful parses | Median seconds | Peak client tree MiB |
| --- | --- | --- | --- | --- |
| Existing Selenium service, local Chromium | HLTV | 3/3 | 2.659 | 1316.4 |
| Existing Selenium service, isolated Chrome container | HLTV | 3/3 | 3.276 | 179.8 |
| AsyncCamoufox, local | HLTV | 3/3 | 3.892 | 1506.7 |
| Camoufox remote, warm loopback server | HLTV | 3/3 | 2.864 | 227.1 |
| Existing Selenium service, local Chromium | Rezka | 3/3 | 6.278 | 1443.9 |
| Existing Selenium service, isolated Chrome container | Rezka | 3/3 | 6.307 | 128.8 |
| AsyncCamoufox, local | Rezka | 3/3 | 7.800 | 1671.1 |
| Camoufox remote, warm loopback server | Rezka | 3/3 | 6.314 | 179.0 |

The Camoufox remote server separately peaked at **1854.1 MiB** across its six
live jobs. The isolated Selenium container peaked at **2023.0 MiB**, including
Grid's Java process and display services. These are different browser versions
and service stacks; the samples do not establish a memory-efficiency advantage.
Client RSS alone therefore does not show its cost. Remote timings exclude server
startup; local timings include browser startup. RSS double-counts shared pages
and is not PSS, Docker memory usage, or a recommended container limit. The host
was shared with other work and some fixture probes ran alongside live runs.
Three attempts from one IP, without proxies or authentication, establish API
compatibility here, not reliability statistics or a capacity benchmark.

The local Selenium baseline uses `SeleniumService.get_html`, the configured local
driver factory and production callback. It uses the existing Chrome fingerprint
options. Both engines use a 30-second navigation deadline and Rezka's existing
five-second delay. Selenium's existing service may continue after a bounded page
load timeout; Camoufox rejects navigation timeouts and non-success HTTP responses.
Success requires a nonempty result from the existing parser, not just HTTP 200.

All twelve live Item snapshots for each feed are identical, including hashes.
The two browsers serialize different HTML bytes, but the required HLTV rows and
Rezka film status produce the same public `items` output. Raw HTML and cookie
files stay under ignored `work/`; they are not included in the PR.

An exploratory run on 2026-10-22 failed all three Camoufox HLTV attempts because
Playwright's default `wait_for` requires visibility. Selenium's callback requires
DOM presence, and the site's matching headline was hidden. The final port uses
`state="attached"`. The local fixture deliberately hides the heading to verify
that behavior. The exploratory errors remain in `results.json` separately from
the final measurements; they are not counted as site blocking.

## Versions and artifacts

Official release metadata was checked again on 2026-10-25.

| Component | Pin used |
| --- | --- |
| Host | Arch Linux x86_64, kernel 7.2.11-zen1-1-zen, glibc 2.44 |
| Python | 3.13.11 |
| Selenium Python | 4.34.2, existing repository lock |
| Local Chromium and ChromeDriver | 156.0.8078.47 in final runs |
| Separate Chrome container | Selenium 4.48.0, Chrome 152.0.7977.82, image pinned below |
| Camoufox Python | 0.5.8 |
| Camoufox browser | 156.0.1-beta.36, BuildID 20261006020805 |
| Playwright Python and bundled driver | 1.62.0, below Camoufox's declared `<1.63` constraint |
| psutil | 7.1.3 |
| Fingerprint model | fpgen 1.3.0, model-2/2026 |

The [browser release](https://github.com/daijro/camoufox/releases/tag/v156.0.1-beta.36)
provides a Linux x86_64 ZIP of 1,294,875,941 bytes, about 1.21 GiB. Its SHA-256 is
in [browser.sha256](browser.sha256); the extracted tree is about 2.4 GiB.
[PyPI](https://pypi.org/project/camoufox/0.5.8/) identifies the wrapper as MIT.
The [browser source license](https://github.com/daijro/camoufox/blob/7a4ac0d4dca2dfdeb277f521824a26efb0b6a7b6/LICENSE)
is MPL-2.0. Packaging must retain the respective notices and source references,
including bundled third-party components.

Camoufox 0.5.8 itself pins and verifies its fingerprint model archive and members.
The model ZIP is 1,564,571 bytes, SHA-256
`6530b8322cdaa4ec042921c8d9a0369a0e6e0269ba636c01a7203e4a2f109936`.
Do not set `FPGEN_MODEL_URL`, which bypasses that default pin. Default uBlock
downloads use a `latest.xpi` URL; this spike disables default addons in both local
and remote mode so they cannot introduce an unpinned runtime dependency.

## Reproduce

Run these commands from the repository root on Linux x86_64 with Python 3.13,
`uv`, `curl`, `unzip`, and working browser system libraries. The Selenium baseline
also needs `/usr/bin/chromium` and `/usr/bin/chromedriver`, as the app requires.
The spike uses dummy DB/Redis/Twitch configuration and makes no DB, Redis or
broker calls. Use a new output directory for each run; existing results are never
overwritten. Do not run with Python optimization, which disables assertions.

```sh
uv venv work/p13/venv --python 3.13
uv pip sync --python work/p13/venv/bin/python --require-hashes experiments/camoufox/requirements.txt
mkdir -p work/p13
curl --fail --location --retry 2 \
  https://github.com/daijro/camoufox/releases/download/v156.0.1-beta.36/camoufox-156.0.1-beta.36-lin.x86_64.zip \
  --output work/p13/browser.zip
(cd work/p13 && sha256sum --check ../../experiments/camoufox/browser.sha256)
unzip -q work/p13/browser.zip -d work/p13/browser

PYTHONPATH=. work/p13/venv/bin/python experiments/camoufox/spike.py \
  --engine selenium --mode fixture --runs 1 --output work/p13/new-selenium-fixture
PYTHONPATH=. work/p13/venv/bin/python experiments/camoufox/spike.py \
  --engine camoufox --binary work/p13/browser/camoufox \
  --mode fixture --runs 2 --concurrency 2 --output work/p13/new-camoufox-fixture
```

Replace `--mode fixture` with `--mode live --runs 3` for the selected feeds.
Every browser exception, parser failure, or nonzero child exit produces an explicit
failed result and a nonzero supervisor exit. Each child has a 100-second wall
deadline and bounded process-group termination; cancellation also terminates it.
Local Camoufox dependencies load only inside the experimental process.

For remote mode, start the server in a separate terminal, then run the client:

```sh
PYTHONPATH=. work/p13/venv/bin/python experiments/camoufox/remote.py \
  --engine camoufox --binary work/p13/browser/camoufox --output work/p13/new-server

PYTHONPATH=. work/p13/venv/bin/python experiments/camoufox/spike.py \
  --engine camoufox --remote ws://127.0.0.1:19313/p13 \
  --server-pid "$(cat work/p13/new-server/server.pid)" \
  --mode fixture --runs 2 --concurrency 2 --output work/p13/new-remote-fixture
```

Stop the experimental server with Ctrl-C when finished. `--server-pid` only
samples a local server; omit it for another host and measure that host separately.

For the container baseline, use a disposable instance of the exact production
Chrome image. Wait for `/status` to report ready before running the client.
This does not use, restart or remove the production Chrome container:

```sh
docker run -d --name parser-camoufox-spike-grid \
  -p 127.0.0.1:19444:4444 --shm-size=1g -e SE_NODE_MAX_SESSIONS=1 \
  selenium/standalone-chrome:4.48.0-20260905@sha256:11faf9d193dbdce26b4d7370f2d28e299515a00dd94453f154219469eb53b1a7
curl --fail http://127.0.0.1:19444/status
PYTHONPATH=. work/p13/venv/bin/python experiments/camoufox/spike.py \
  --engine selenium --grid http://127.0.0.1:19444 \
  --server-pid "$(docker inspect --format '{{.State.Pid}}' parser-camoufox-spike-grid)" \
  --mode live --runs 3 --output work/p13/new-grid-live
docker rm -f parser-camoufox-spike-grid
```

Grid mode uses the existing app's Docker driver factory through per-process
dependency injection. It supports live feeds only, because its browser cannot
reach a fixture server bound to the client's loopback interface.

The lock includes the parser's existing production dependencies plus the optional
spike dependencies. Refresh deliberately with
`uv pip compile experiments/camoufox/requirements.in --python-version 3.13 --generate-hashes --output-file experiments/camoufox/requirements.txt`.
The production `pyproject.toml`, `uv.lock` and `requirements.txt` stay unchanged.

## Lifecycle and service choice

The fixture mode is an executable integration check using real browsers and a
local HTTP server. It checks delayed DOM rendering, the real Selenium HLTV
callback, expected Item titles/links/hashes, and rejection of malformed pages.
Camoufox additionally checks cookie loading before navigation, storage-state
save/reload, fresh-context isolation and an actual navigation timeout. Both local
and remote Camoufox passed four jobs with concurrency two. This is bounded smoke
coverage, not a heavy-worker load test.

Use `BrowserContext.add_cookies` and JSON `storage_state` for a future extension.
Do not load Selenium's pickle directly: cookie field names differ, including
`expiry` versus `expires`, and session cookies need explicit conversion. Production
state would need a per-feed/account key, mode 0600, atomic replacement and a
single writer or version check. This spike saves fixture state separately for
every job. Persistent profile directories must never be shared by concurrent jobs.

Each local job owns an `AsyncCamoufox` browser and fresh contexts. Async context
managers close them on normal completion and error. Timeout and cookie checks
also close their contexts. A future service must add admission limits, process
supervision, crash/kill recovery checks, cancellation checks and memory limits;
these are not supplied by switching the Python API. Start at one active browser
per service and measure before raising concurrency. CDP-only operations such as
RTL's user-agent override and VK request handling require a Firefox design.

The [remote server documentation](https://camoufox.com/python/remote-server/)
labels the implementation experimental and describes a shared browser fingerprint
across sessions. It uses private Playwright internals. The spike's server runs
only on loopback, and each client closes its contexts before disconnecting.
[Playwright requires matching client/server major and minor versions](https://playwright.dev/python/docs/api/class-browsertype#browser-type-connect).
The Camoufox server and client here use the exact same lock. A shared server lowers startup
cost but adds shared fate, fingerprint lifetime, queueing, health checks and
restart/drain duties. The current separate Chrome container already has session
limits, health checks and a recovery watchdog. Its occupied production instance
was not modified. The baseline clone uses the same pinned image and one session,
without the production watchdog mount. Six successful jobs do not validate Grid
or Camoufox crash recovery, nor constitute a capacity comparison.

If new evidence justifies another trial, prefer a separate Playwright extension
with a service that returns rendered HTML and runs an async page action hook.
HLTV is the first candidate because its callback is a single wait already ported
here; HTML parsing and hashes need no change. Estimate 2-4 engineering days for
the shared extension/service boundary and one day for an HLTV pilot with failure
and recovery coverage, excluding a longer live observation period.

Migrating Selenium wholesale touches 13 browser-backed parser modules, including
six custom WebDriver callback modules. Stories/Anonig form and lazy-load actions,
VK/VK Video challenge flows and RTL CDP usage make it a roughly 1-3 week migration
plus live soak time. This is a code-reading estimate, not measured delivery time.
Reject that migration now. A later adoption proposal would need to cover an
isolated glibc browser service, parser-specific action ports, per-account cookie
ownership, worker deadlines/admission control, restart recovery, deployment and
rollback, and repeated success measurements where Selenium actually fails.

## Linux, Alpine and Docker

The browser ran on the glibc Linux host. An unmodified Alpine 3.22 container
at `sha256:14358309a308569c32bdc37e2e0e9694be33a9d99e68afb0f5ff33cc1f695dce`
failed to execute `camoufox-bin` with `no such file or directory`: the ELF requests
`/lib64/ld-linux-x86-64.so.2`, absent on musl Alpine. Do not add compatibility shims
to the production worker. [Playwright also excludes Alpine/musl for Firefox](https://playwright.dev/python/docs/docker).

The research [Dockerfile](Dockerfile) installs the verified binary in
`/opt/camoufox`, the model during build, a hash-locked Python environment, a
digest-pinned Python 3.13.11 Debian base and dated Debian package snapshots.
It runs as an unprivileged user. Build using a restricted context to avoid
copying the worktree's environments or captured HTML to the Docker daemon:

```sh
tar -c app experiments/camoufox work/p13/browser.zip | \
  docker build -f experiments/camoufox/Dockerfile -t parser-camoufox-spike:0.5.8 -
docker run --rm --init --shm-size=1g parser-camoufox-spike:0.5.8
```

The Debian image built and passed both fixture feeds as its unprivileged user.
The first built research image occupied 4,913,428,678 uncompressed bytes locally.
This optional image does not join production Compose. Browser ZIPs and the large
extracted runtime increase build storage, image distribution and update cost.
The archive is a separate Docker layer even after extraction deletes its copy.
Any adoption should publish the built service by image digest and allow no
runtime `fetch` or floating browser channel. Updates must change package lock,
browser URL/checksum and base/snapshot pins together, rerun fixture and live
comparisons, retain the previous image for rollback, and review Firefox security
updates rather than holding this beta indefinitely.

The [upstream maintenance warning](https://github.com/daijro/camoufox#readme)
still says the project is under development and may be unsuitable for stable
production use. The [current initialization API](https://camoufox.com/python/usage/)
fits this isolated prototype, but the warning, remote implementation risk and
extra operating cost outweigh the unproven detection benefit in these results.
