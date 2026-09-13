# P13: Evaluate Camoufox browser integration

- STATUS: IDEA
- PRIORITY: 3
- DEPENDS: none

## Goal

Decide whether [Camoufox](https://github.com/daijro/camoufox) should supplement
or replace Selenium for sites that reject the current automated Chrome setup.

## Background

Camoufox is a Firefox fork controlled through Playwright. It adds browser-level
fingerprint changes intended to reduce automation detection. The current parser
path uses Selenium `WebDriver`, including parser-specific action callbacks, and
runs Chrome as a separate container. Camoufox is therefore not a drop-in driver
change. Its maintainers also describe it as under development and warn that it
may not be ready for stable production use.

## Investigation

- [ ] Pick two or three browser-backed feeds that are blocked or unreliable and
      record a Selenium baseline for success rate, response time, and memory.
- [ ] Build a small `AsyncCamoufox` spike for those feeds without changing the
      production browser path.
- [ ] Compare rendered HTML and required interactions with the current parser
      output. Include at least one parser that uses a `WebDriver` action callback.
- [ ] Decide whether to add a separate Playwright-based parser extension or
      migrate the existing Selenium extension. Estimate the parser changes for
      each choice.
- [ ] Check how cookie loading, cookie persistence, navigation timeouts, browser
      cleanup, and concurrent heavy-worker jobs would work.
- [ ] Check Linux and Alpine compatibility. Decide where to install the browser
      binary and how to pin and update it reproducibly in Docker.
- [ ] Compare local browser execution with Camoufox's remote Playwright server
      against the current separate Chrome container.
- [ ] Record the browser and Python package versions used by the spike. Do not
      follow an unpinned release channel in production.
- [ ] Review the maintenance warning, license, update process, artifact size,
      and operational cost before recommending adoption.

## Definition of done

A short decision record recommends adopting or rejecting Camoufox, backed by
the spike results. If adoption is worthwhile, it names the first parser to move,
the proposed service boundary, and the follow-up implementation tasks. This task
does not change the production browser path.
