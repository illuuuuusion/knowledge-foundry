# P8 live collection tests

Date: 2026-10-15. User requested a complete four-video playlist trial followed
by an unbounded channel trial, with discovered defects fixed. These are AI
execution results supporting UAT. The later user message "Gut committe"
accepts the reported scope and limitations and authorizes committing them.

## Sources and outcomes

- Playlist PLAcPAREfsYHV6WRV0C6ZPYdFN6UKutLru: four videos, four successful
  transcripts, grouping 2, two groups per format. Repeat preserved attempt=1
  for every video and identical export paths. Five extraction jobs, ten
  selected unverified statements, 24 nodes/25 edges. All five results imported.
- Channel @northwestrepair: no --limit, 393 video-feed entries plus 55 shorts,
  448 unique videos attempted. Streams tab is unavailable. First run and resume
  both exported 432 transcripts; twelve videos have no caption tracks and four
  remained rate-limited after bounded retries. They are explicit failures,
  not successful transcripts. Source/video issues make CLI exit 1 correctly.
- Resume included both channel root and /playlists alias. They identify the
  same feed without duplicate videos. All 432 prior successes preserve caption
  attempt counts and payload hashes; only retryable failed retrievals retry.
- Whole successful channel store yields 468 file jobs. Eight results imported,
  460 pending. The selected graph has 21 unverified statements from six videos,
  46 nodes/65 edges. Seven earlier results were reused only after byte-equal
  input.jsonl and schema.json checks; one further channel video was freshly
  read and extracted. No exhaustive analysis of all 448 videos is claimed.

## Repairs and evidence

Channel /playlists navigation now selects the same normal video feed as the
root/videos while retaining original inputs. Explicit playlist URLs remain
separate; the navigation alias does not crawl channel-owned playlists.
Explicit missing-tab errors classify as nonretryable tab_unavailable instead
of generic backend_error. Three new synthetic tests cover aliases, provenance,
dedup, unsafe nested tabs and unavailable-tab partial-source preservation.
Full offline suite: 182 pass; separate reviewer independently reran it.

Four actual-artifact checks per corpus validate unbounded attempted coverage,
lossless grouped JSONL/canonical equality, source/timing consistency, graph
integrity and library links/budgets. Playlist and channel libraries also match
external temporary workspaces (28 and 38 files respectively). All paths/counts,
limits and independent review evidence are in the P8 reports.

## Runtime and next steps

Ignored runtime folders:
`output/live-playlist-PLAcPAREfsYHV6WRV0C6ZPYdFN6UKutLru/` and
`output/live-channel-northwestrepair/`. Begin with each DEMO.md or library/INDEX.md.
They retain first/final scrape reports, resume checks, file jobs, selected graph,
exports and failures.json. External copies are temporary under /private/tmp.
Do not commit raw transcripts or copy real data into deterministic fixtures.

P8 is complete following the user's explicit "Gut committe" acceptance. Remaining
caption access failures and the 460 pending extraction jobs are accepted residual
limits of this reported trial, not completed extraction or bypass targets. More
extraction can process the pending jobs; no model API is required by the application.
No extra hands-on user workflow or external client session is asserted.
