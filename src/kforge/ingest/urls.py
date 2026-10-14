"""Parse an explicit allowlist of YouTube source URLs without network access."""

from dataclasses import dataclass
import re
from urllib.parse import parse_qs, quote, unquote, urlsplit


VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")
TOKEN = re.compile(r"[A-Za-z0-9_-]{1,128}")
NAME = re.compile(r"[\w.-]{1,100}")


class UnsupportedURL(ValueError):
    """The URL is outside the supported source forms."""


@dataclass(frozen=True)
class Source:
    input_url: str
    source_id: str
    kind: str
    canonical_url: str


def parse_url(value: str) -> Source:
    if not isinstance(value, str) or not value.strip():
        raise UnsupportedURL("Expected a nonempty YouTube URL")
    original = value.strip()
    try:
        url = urlsplit(original)
        if (url.scheme not in {"https", "http"} or url.username is not None
                or url.password is not None or url.port is not None
                or any(char.isspace() or ord(char) < 32 for char in original)):
            raise UnsupportedURL("Unsupported URL scheme or authority")
        host = url.hostname
        parts = unquote(url.path).strip("/").split("/")
        query = parse_qs(url.query, keep_blank_values=True)
    except ValueError as exc:
        raise UnsupportedURL("Malformed URL") from exc

    def video(identifier: str) -> Source:
        if not VIDEO_ID.fullmatch(identifier):
            raise UnsupportedURL("Invalid YouTube video ID")
        return Source(original, f"youtube:video:{identifier}", "video",
                      f"https://www.youtube.com/watch?v={identifier}")

    def parameter(name: str) -> str:
        values = query.get(name, [])
        if len(values) != 1 or not values[0]:
            raise UnsupportedURL(f"Expected one {name} parameter")
        return values[0]

    if host in {"youtu.be", "www.youtu.be"}:
        if len(parts) == 1:
            return video(parts[0])
        raise UnsupportedURL("Unsupported short URL path")
    if host in {"youtube-nocookie.com", "www.youtube-nocookie.com"}:
        if len(parts) == 2 and parts[0] == "embed":
            return video(parts[1])
        raise UnsupportedURL("Only embed URLs are supported on this host")
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
        raise UnsupportedURL("Unsupported host")
    if parts == ["watch"]:
        # A watch URL with v and list identifies the video, not its surrounding playlist.
        return video(parameter("v"))
    if len(parts) == 2 and parts[0] in {"shorts", "live", "embed"}:
        return video(parts[1])
    if parts == ["playlist"]:
        identifier = parameter("list")
        if not TOKEN.fullmatch(identifier):
            raise UnsupportedURL("Invalid playlist ID")
        return Source(original, f"youtube:playlist:{identifier}", "playlist",
                      f"https://www.youtube.com/playlist?list={identifier}")
    if parts[0].startswith("@") and NAME.fullmatch(parts[0][1:]):
        channel, remainder = parts[0], parts[1:]
    elif len(parts) >= 2 and parts[0] in {"channel", "c", "user"}:
        identifier = parts[1]
        valid = (re.fullmatch(r"UC[A-Za-z0-9_-]{22}", identifier)
                 if parts[0] == "channel" else NAME.fullmatch(identifier))
        if not valid:
            raise UnsupportedURL("Invalid channel identifier")
        channel, remainder = "/".join(parts[:2]), parts[2:]
    else:
        raise UnsupportedURL("Unsupported YouTube path")
    if remainder not in ([], ["videos"], ["shorts"], ["streams"]):
        raise UnsupportedURL("Unsupported channel tab")
    tab = remainder[0] if remainder else "videos"
    return Source(original, f"youtube:channel:{channel}:{tab}", "channel",
                  f"https://www.youtube.com/{quote(channel, safe='/@')}/{tab}")


def parse_url_list(text: str) -> list[str]:
    """One URL per line; blank lines and full-line # comments are ignored."""
    return [line.strip() for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]
