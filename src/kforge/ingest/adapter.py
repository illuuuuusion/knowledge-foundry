"""Metadata-only yt-dlp boundary, optional dependency and classified failures."""

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
import socket
import re
from typing import Protocol
from urllib.error import URLError

from .urls import Source


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    retryable: bool = False
    position: int | None = None


MESSAGES = {
    "unsupported": "Source is outside the supported YouTube URL forms",
    "inaccessible": "Source or entry is unavailable or requires authorization",
    "network_error": "Metadata request failed due to a network error",
    "rate_limited": "Metadata access is rate limited; retry later",
    "backend_unavailable": "Install the discovery extra to use yt-dlp",
    "invalid_metadata": "Metadata entry does not identify a valid YouTube video",
    "backend_error": "Metadata extraction failed; no access workaround was attempted",
}


class DiscoveryError(Exception):
    def __init__(self, issue: Issue):
        super().__init__(issue.message)
        self.issue = issue


class MetadataAdapter(Protocol):
    def entries(self, source: Source) -> Iterable[Mapping | None]: ...


def classify_error(error: Exception) -> Issue:
    """Conservative classification; raw backend errors are never emitted."""
    if isinstance(error, DiscoveryError):
        return error.issue
    chain, seen = [error], set()
    messages = []
    codes = []
    network = False
    while chain:
        current = chain.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        messages.append(str(current).lower())
        codes.append(getattr(current, "status", getattr(current, "code", None)))
        network |= isinstance(current, (TimeoutError, ConnectionError, socket.gaierror, URLError))
        for nested in (current.__cause__, current.__context__, getattr(current, "cause", None)):
            if isinstance(nested, Exception):
                chain.append(nested)
        info = getattr(current, "exc_info", None)
        if isinstance(info, tuple) and len(info) > 1 and isinstance(info[1], Exception):
            chain.append(info[1])
    message = " ".join(messages)
    codes.extend(int(code) for code in re.findall(r"http (?:error )?(\d{3})\b", message))
    if 429 in codes or "http error 429" in message or "too many requests" in message:
        code = "rate_limited"
    elif any(item in codes for item in (401, 403, 404, 410)) or any(
        token in message for token in ("private video", "video unavailable", "video is unavailable",
                                      "not available", "does not exist", "sign in", "login required",
                                      "members-only", "removed")
    ):
        code = "inaccessible"
    elif network or any(isinstance(item, int) and 500 <= item <= 599 for item in codes) or any(
        token in message for token in ("timed out", "unable to download", "connection reset", "connection refused",
                                      "name resolution", "network is unreachable")
    ):
        code = "network_error"
    else:
        code = "backend_error"
    return Issue(code, MESSAGES[code], code in {"network_error", "rate_limited"})


class _QuietLogger:
    # yt-dlp messages may contain URLs/source text. Only classified errors leave this boundary.
    def debug(self, message): pass
    def warning(self, message): pass
    def error(self, message): pass


class YtDlpAdapter:
    def __init__(self, factory: Callable | None = None):
        self.factory = factory

    def entries(self, source: Source) -> Iterable[Mapping | None]:
        factory = self.factory
        if factory is None:
            try:
                from yt_dlp import YoutubeDL
            except ImportError as exc:
                raise DiscoveryError(Issue("backend_unavailable", MESSAGES["backend_unavailable"])) from exc
            factory = YoutubeDL
        options = {
            "skip_download": True, "simulate": True, "extract_flat": True,
            "lazy_playlist": True, "ignoreerrors": False, "quiet": True,
            "no_warnings": True, "logger": _QuietLogger(), "cachedir": False,
            "writesubtitles": False, "writeautomaticsub": False,
            "writeinfojson": False, "writethumbnail": False, "socket_timeout": 20,
            "retries": 0, "extractor_retries": 0,
        }
        try:
            with factory(options) as backend:
                # process=False keeps extractor pagination lazy and avoids video processing.
                info = backend.extract_info(source.canonical_url, download=False, process=False)
                if not isinstance(info, Mapping):
                    raise DiscoveryError(Issue("invalid_metadata", MESSAGES["invalid_metadata"]))
                if "entries" in info:
                    entries = info["entries"]
                    if not isinstance(entries, Iterable) or isinstance(entries, (str, bytes, Mapping)):
                        raise DiscoveryError(Issue("invalid_metadata", MESSAGES["invalid_metadata"]))
                    yield from entries
                else:
                    yield info
        except Exception as exc:
            raise DiscoveryError(classify_error(exc)) from exc
