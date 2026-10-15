# P1 source discovery

## Interface and data contract

`ingest.urls.parse_url` validates explicit HTTP(S) YouTube hosts and supported paths
offline. It strips navigation/tracking from canonical URLs but retains each original
input. Video IDs are 11 ASCII token characters; channel IDs use UC plus 22; playlist
IDs are nonempty bounded tokens. Credentials, ports, repeated identity parameters,
foreign hosts, unsupported paths and tabs are rejected. Bare channels default to
videos; `/playlists` channel navigation also normalizes to that video feed while
retaining the original URL. Explicit shorts and streams are separate source
identities. Watch URLs with
both v/list denote a video; playlist discovery requires an explicit playlist URL.
URL lists are line-based data, not executable instructions or shell commands.

`MetadataAdapter.entries(Source)` streams video mappings. `YtDlpAdapter` lazily
imports the optional discovery extra. It holds the backend context while iterating
raw extractor results, disables downloads/subtitle writes/cache/info/thumbnail
writes, and uses extract_info(download=False, process=False). Lazy raw playlist
entries preserve pagination and allow early close without fetching the next page.
The API was checked against official [embedding documentation](https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp)
and [YoutubeDL source](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py),
plus an offline constructor/signature contract against locally installed yt-dlp.
No third-party source code or real source collection is copied into fixtures.

`discover` returns a schema-versioned Manifest with source results and one Video
per stable YouTube ID. Each video retains whitelisted available metadata, the first
observation as its summary, source IDs and every observation (including conflicting
duplicate metadata and entry position). Metadata is unverified. Missing metadata
is not invented, and video canonical URLs are normalization, not verified citations.
Foreign extractor entries, nested collection entries and mismatching single-video
IDs are rejected. This is discovery, not P2 canonical transcript storage; SQLite
schema remains unchanged.

Source timestamp, release_timestamp, modified_timestamp and epoch values, plus
upload/release/modified dates, are retained exactly when present and well typed,
including in conflicting observations. Invalid optional numeric values (boolean,
nonfinite or beyond finite conversion range) are omitted without aborting remaining
entries. These fields were added after the independent review found timestamp loss.

## Ordering, limits and errors

Default order is input-source then adapter-entry order. Dedup uses video IDs and
canonical source identities. Equivalent inputs are fetched once, while each input
still has a source result. Global limit counts unique videos; 0 avoids backend calls.
ID ordering sorts the bounded source-order selection, never implies full-channel
scanning for lowest IDs. Hitting a collection limit conservatively means truncated
even if it happened to be the final entry. Later sources remain not_processed.
Determinism is relative to identical returned metadata, not mutable remote sources.

Unsupported sources never reach yt-dlp. Unavailable/invalid entries are explicit
issues; lazy failures preserve prior videos and processing continues for other
sources. Errors are conservative classifications with generic messages and retry
flags; raw backend logs/exceptions are not output. Rate limits and network errors
are retryable; auth/private/removed/HTTP 401/403/404/410 are inaccessible. Unknown
failures are backend_error. No automatic retries, credentials, bot bypasses or
claims of exhaustive access are added in P1. Collection-level diagnostics are
limited to what the backend actually emits; no unknown video IDs are fabricated.

## Verification and next phase

Fixtures are synthetic and offline, including paginated channel/playlist responses,
dedup/provenance, limits, sorting, empty results, errors and inert instruction text.
See P1 test/review reports for actual results. Local native API checks used yt-dlp
2026.08.19, but no live YouTube request or real UAT occurred. P2 must preserve this
manifest contract while adding transcript track selection and canonical storage;
do not treat metadata availability or claims as independently verified facts.

## P8 collection live tests and maintenance

The supplied four-video playlist completed normal original-English caption
retrieval for all four entries. The channel URL pointed at /@northwestrepair/playlists,
which P1 had rejected. P8 now recognizes this navigation URL as the same channel
video feed as its root or /videos; it does not recursively ingest channel-owned
playlists. Source input is preserved and duplicate root/navigation discovery
uses a single backend request. Synthetic tests cover all supported channel forms,
Unicode handles and rejected nested tabs. Explicit playlist URLs are unchanged.

The real channel yielded 393 normal videos and 55 shorts. Its streams tab is
not available. yt-dlp's explicit 'This channel does not have a streams tab'
message previously became generic backend_error; it now classifies as
nonretryable tab_unavailable, also for missing videos/shorts tabs. This reports
accessibility, not a fabricated zero-count complete feed. A synthetic failure
case checks that prior sources remain intact. The bounded classifier matches
known explicit backend messages and never publishes raw error text.
