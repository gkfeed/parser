# P18: Apply yt-dlp item limits to every channel source

- STATUS: PENDING
- PRIORITY: 2
- DEPENDS: none

## Goal

Limit yt-dlp extraction work and parser output to the item count requested by
the caller.

## Plan

- [ ] Give `max_videos` one documented meaning across channel and playlist
      extraction.
- [ ] Pass the requested limit to yt-dlp instead of relying on a hard-coded mode
      value.
- [ ] Apply the same limit to YouTube channels, YouTube playlists, and TikTok
      channels.
- [ ] Define and test the behavior of zero or negative limits.
- [ ] Keep cached results separate when the URL, extraction mode, or requested
      limit differs.
- [ ] Test returned item counts and extractor options through public parser or
      extractor behavior.
- [ ] Run `make lint` and `make test`.

## Definition of done

Each parser returns no more than its requested item count, and yt-dlp does not
scan the rest of a large channel or playlist to produce that result.
