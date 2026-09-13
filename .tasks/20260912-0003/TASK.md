# P16: Normalize YouTube channel URLs without duplicating path segments

- STATUS: PENDING
- PRIORITY: 2
- DEPENDS: none

## Goal

Build the intended YouTube extraction URL without appending `/videos` to an
existing channel tab.

## Plan

- [ ] Append `/videos` only to a channel root such as `/@handle` or
      `/channel/<id>`.
- [ ] Leave existing `/videos`, `/shorts`, `/streams`, and playlist paths
      unchanged.
- [ ] Handle trailing slashes and query strings consistently.
- [ ] Test URL selection through `YoutubeFeed` behavior for handle, channel ID,
      tab, and playlist URLs.
- [ ] Run `make lint` and `make test`.

## Definition of done

Channel roots resolve to their videos tab, while URLs such as
`https://www.youtube.com/@demo/videos` never become `/videos/videos`.
