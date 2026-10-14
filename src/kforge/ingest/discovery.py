"""Bounded discovery manifests over an injectable, streaming metadata adapter."""

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, replace
import math

from .adapter import Issue, MESSAGES, MetadataAdapter, YtDlpAdapter, classify_error
from .urls import Source, UnsupportedURL, VIDEO_ID, parse_url


@dataclass(frozen=True)
class Observation:
    source_id: str
    position: int
    metadata: dict


@dataclass(frozen=True)
class Video:
    id: str
    video_id: str
    url: str
    metadata: dict
    source_ids: tuple[str, ...]
    observations: tuple[Observation, ...]
    verification_status: str = "unverified"


@dataclass(frozen=True)
class SourceResult:
    input_url: str
    source: Source | None
    status: str
    video_ids: tuple[str, ...] = ()
    issues: tuple[Issue, ...] = ()


@dataclass(frozen=True)
class Manifest:
    sources: tuple[SourceResult, ...]
    videos: tuple[Video, ...]
    limit: int | None
    order: str
    schema_version: int = 1

    def to_dict(self) -> dict:
        return asdict(self)


def _finite_number(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _metadata(entry: Mapping) -> dict:
    values = {}
    for key in ("title", "channel", "channel_id", "uploader", "uploader_id",
                "upload_date", "release_date", "modified_date", "availability",
                "webpage_url", "url", "description"):
        if isinstance(entry.get(key), str):
            values[key] = entry[key]
    duration = entry.get("duration")
    if _finite_number(duration) and duration >= 0:
        values["duration"] = duration
    for key in ("timestamp", "release_timestamp", "modified_timestamp", "epoch"):
        if _finite_number(entry.get(key)):
            values[key] = entry[key]
    return values


def discover(
    urls: str | Iterable[str], *, adapter: MetadataAdapter | None = None,
    limit: int | None = None, order: str = "source",
) -> Manifest:
    """Select a source-order prefix of unique videos, then optionally sort by ID.

    A reached limit conservatively reports truncation without fetching another page.
    Individual source failures preserve earlier discoveries and do not abort the batch.
    """
    if limit is not None and (type(limit) is not int or limit < 0):
        raise ValueError("limit must be a nonnegative integer or None")
    if order not in {"source", "id"}:
        raise ValueError("order must be source or id")
    inputs = [urls] if isinstance(urls, str) else list(urls)
    if any(not isinstance(value, str) for value in inputs):
        raise ValueError("URL list must contain strings")
    backend = adapter if adapter is not None else YtDlpAdapter()
    results = []
    videos: dict[str, Video] = {}
    cached: dict[str, SourceResult] = {}
    for value in inputs:
        try:
            source = parse_url(value)
        except UnsupportedURL:
            results.append(SourceResult(value, None, "unsupported", issues=(
                Issue("unsupported", MESSAGES["unsupported"]),)))
            continue
        if source.source_id in cached:
            results.append(replace(cached[source.source_id], input_url=value, source=source))
            continue
        if limit is not None and len(videos) >= limit:
            results.append(SourceResult(value, source, "not_processed"))
            continue
        found, issues = [], []
        status = "empty"
        entries = None
        try:
            entries = iter(backend.entries(source))
            for position, entry in enumerate(entries, start=1):
                if entry is None:
                    issues.append(Issue("inaccessible", MESSAGES["inaccessible"], position=position))
                    continue
                if (not isinstance(entry, Mapping) or not isinstance(entry.get("id"), str)
                        or not VIDEO_ID.fullmatch(entry["id"])
                        or entry.get("ie_key") not in (None, "Youtube")
                        or "entries" in entry):
                    issues.append(Issue("invalid_metadata", MESSAGES["invalid_metadata"], position=position))
                    continue
                identifier = entry["id"]
                if source.kind == "video" and identifier != source.source_id.rsplit(":", 1)[1]:
                    issues.append(Issue("invalid_metadata", MESSAGES["invalid_metadata"], position=position))
                    continue
                key = f"youtube:video:{identifier}"
                metadata = _metadata(entry)
                observation = Observation(source.source_id, position, metadata)
                if key in videos:
                    previous = videos[key]
                    videos[key] = replace(previous,
                        source_ids=tuple(dict.fromkeys((*previous.source_ids, source.source_id))),
                        observations=(*previous.observations, observation))
                else:
                    videos[key] = Video(key, identifier,
                        f"https://www.youtube.com/watch?v={identifier}", metadata,
                        (source.source_id,), (observation,))
                if key not in found:
                    found.append(key)
                status = "ok"
                if metadata.get("availability") in {"private", "needs_auth", "subscriber_only", "premium_only"}:
                    issues.append(Issue("inaccessible", MESSAGES["inaccessible"], position=position))
                if limit is not None and len(videos) >= limit:
                    status = "ok" if source.kind == "video" else "truncated"
                    break
        except Exception as exc:
            issue = classify_error(exc)
            issues.append(issue)
            status = "partial" if found else issue.code
        finally:
            close = getattr(entries, "close", None)
            if close is not None:
                try:
                    close()
                except Exception as exc:
                    issue = classify_error(exc)
                    issues.append(issue)
                    status = "partial" if found else issue.code
        if issues and status not in {"truncated", "partial"}:
            status = "partial" if found else issues[0].code
        result = SourceResult(value, source, status, tuple(found), tuple(issues))
        cached[source.source_id] = result
        results.append(result)
    selected = tuple(videos.values())
    if order == "id":
        selected = tuple(sorted(selected, key=lambda video: video.video_id))
    return Manifest(tuple(results), selected, limit, order)
