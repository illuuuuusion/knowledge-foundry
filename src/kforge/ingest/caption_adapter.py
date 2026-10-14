"""Optional yt-dlp caption-only access, with no video/audio download or bypass."""

from collections.abc import Callable, Mapping
from contextlib import closing
from urllib.parse import urlsplit

from .adapter import DiscoveryError, Issue, _QuietLogger, classify_error
from .captions import CaptionError, MAX_CAPTION_BYTES, Track
from .discovery import Video
from .urls import parse_url


def _caption_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        host = parts.hostname or ''
        return (parts.scheme == 'https' and parts.username is None and
                parts.password is None and parts.port in (None, 443) and
                any(host == domain or host.endswith('.' + domain)
                    for domain in ('youtube.com', 'googlevideo.com')))
    except ValueError:
        return False


class YtDlpCaptionAdapter:
    def __init__(self, factory: Callable | None = None):
        self.factory = factory

    def _backend(self):
        factory = self.factory
        if factory is None:
            try:
                from yt_dlp import YoutubeDL
            except ImportError:
                raise CaptionError('backend_unavailable',
                                   'Install the discovery extra to retrieve captions') from None
            factory = YoutubeDL
        return factory({
            'skip_download': True, 'simulate': True, 'noplaylist': True,
            'ignoreerrors': False, 'quiet': True, 'no_warnings': True,
            'logger': _QuietLogger(), 'cachedir': False,
            'writesubtitles': False, 'writeautomaticsub': False,
            'writeinfojson': False, 'writethumbnail': False,
            'socket_timeout': 20, 'retries': 0, 'extractor_retries': 0,
        })

    def tracks(self, video: Video) -> tuple[Track, ...]:
        try:
            source = parse_url(video.url)
            if source.kind != 'video' or source.source_id != video.id:
                raise CaptionError('unsupported', 'Video identity does not match its URL')
            with self._backend() as backend:
                info = backend.extract_info(source.canonical_url, download=False, process=False)
                if not isinstance(info, Mapping) or info.get('id') != video.video_id:
                    raise CaptionError('invalid_metadata', 'Caption metadata has a mismatched video ID')
                tracks = []
                for field, kind in (('subtitles', 'manual'), ('automatic_captions', 'auto')):
                    values = info.get(field) or {}
                    if not isinstance(values, Mapping):
                        raise CaptionError('invalid_metadata', 'Caption track metadata is invalid')
                    for language, formats in values.items():
                        if language == 'live_chat':
                            continue
                        if not isinstance(language, str) or not isinstance(formats, list):
                            raise CaptionError('invalid_metadata', 'Caption track metadata is invalid')
                        for item in formats:
                            if not isinstance(item, Mapping):
                                raise CaptionError('invalid_metadata', 'Caption track metadata is invalid')
                            url, ext = item.get('url'), item.get('ext')
                            if not isinstance(url, str) or not _caption_url(url):
                                continue  # Never request a foreign/file/credential-bearing track URL.
                            if not isinstance(ext, str):
                                continue
                            headers = item.get('http_headers', info.get('http_headers'))
                            if headers is not None and (not isinstance(headers, dict) or any(
                                    not isinstance(k, str) or not isinstance(v, str)
                                    for k, v in headers.items())):
                                raise CaptionError('invalid_metadata', 'Caption request headers are invalid')
                            tracks.append(Track(language, kind, ext, url,
                                item.get('name') if isinstance(item.get('name'), str) else None, headers))
                return tuple(tracks)
        except CaptionError:
            raise
        except Exception as exc:
            raise DiscoveryError(classify_error(exc)) from exc

    def fetch(self, track: Track) -> bytes:
        if not _caption_url(track.url):
            raise CaptionError('unsupported', 'Caption URL is outside permitted hosts')
        try:
            from yt_dlp.networking import Request
            with self._backend() as backend:
                with closing(backend.urlopen(Request(track.url, headers=track.headers))) as response:
                    # Check final URL too; do not ingest foreign redirected content.
                    if not _caption_url(response.url):
                        raise CaptionError('unsupported', 'Caption response URL is outside permitted hosts')
                    payload = response.read(MAX_CAPTION_BYTES + 1)
            if len(payload) > MAX_CAPTION_BYTES:
                raise CaptionError('invalid_captions', 'Caption response exceeds the size limit')
            return payload
        except CaptionError:
            raise
        except ImportError:
            raise CaptionError('backend_unavailable',
                               'Install the discovery extra to retrieve captions') from None
        except Exception as exc:
            raise DiscoveryError(classify_error(exc)) from exc
