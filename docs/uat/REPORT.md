# P8 user acceptance — accepted

Date: 2026-10-15 (Europe/Berlin).

## User-observed issue

The user attempted to scrape the supplied video PIt_02rTgx0 and reported
`kforge: error: unrecognized arguments`. The pasted shell text contained
backslash-space sequences on one line and, later, a Markdown-formatted URL.
The user then explicitly asked the AI to run the real command, test it and
produce a small knowledge graph from its result.

## AI support and actual outcomes

A correctly separated command with a plain URL parsed successfully. Authorized
live discovery worked, while the German auto-caption download was rate-limited.
The offered English original track exposed a genuine parser defect: newline-only
JSON3 append controls without durations caused invalid_captions. The focused fix
preserves their raw provenance without inventing durations. It has two new
synthetic regressions, 179 passing automated tests and a separate AI review.

The subsequent actual English-original CLI run succeeded. The AI processed two
real extraction jobs and imported nine selected statements via the validating
importer, then generated a 19-node/33-edge graph and a portable knowledge library.
Every statement remains unverified; hypotheses, temporary success, later relapse
and ambiguity in the repair narrative remain visible. This is a selected sample,
not exhaustive extraction or external corroboration. Four actual-artifact tests
and the separate review of all nine statements passed.

Evidence: docs/test-reports/P8.md and docs/reviews/P8.md. Outputs remain local in
`output/live-PIt_02rTgx0/`; begin with DEMO.md or library/INDEX.md. An identical
external temporary workspace is at `/private/tmp/kforge-knowledge-PIt_02rTgx0`.

## User acceptance

The user accepted the reported implementation and test results and authorized
committing them with the exact message **"Gut committe"** on 2026-10-15. This
records acceptance of the presented scope and limitations: 432/448 channel
transcripts accessible, selected graph extraction and 460 remaining extraction
jobs. It does not invent additional hands-on user testing, image verification,
external client sessions or exhaustive knowledge extraction. The live runs were
performed by AI at the user's explicit request; the sign-off is the user's.

## Additional playlist and whole-channel trial requested by user

The user supplied a four-video playlist and the channel's /playlists navigation
URL and asked the AI to test both with bug fixes. No aggregate user acceptance
was inferred from this request.

Playlist: all four videos succeeded; grouped exports contain two videos each.
The repeat preserved attempt=1 and identical exports. Five AI-authored selected
job results imported, producing ten unverified statements and a 24-node/25-edge
graph. Channel navigation support and missing-tab classification were repaired
with three additional offline regressions; full suite is now 182 passing tests.

Channel: all 448 discovered unique videos were attempted without a video cap
(393 normal videos, 55 shorts). Both initial run and resume exported 432
transcripts. Twelve videos have no caption tracks and four remained rate-limited.
The unavailable streams tab and these 16 video failures remain visible. Resume
preserved all 432 successful payload hashes/counters; root/navigation aliases
were deduplicated. No anti-bot workaround or media download was used.

All 468 extraction jobs were generated. Eight results imported, 460 remain
pending; the selected graph has 21 unverified statements from six videos,
46 nodes and 65 edges. Seven byte-identical input/schema results were safely
reused and a further video was newly extracted. This does not claim exhaustive
semantic extraction across the channel. Four real-artifact checks passed per
corpus, alongside separate review and external-workspace file-parity checks.

Open the runtime DEMO.md files in output/live-playlist-PLAcPAREfsYHV6WRV0C6ZPYdFN6UKutLru
and output/live-channel-northwestrepair to inspect actual results and failures.
The subsequent user message "Gut committe" grants acceptance of these reported
results and limitations and authorizes the phase commit. P8 is now complete.
