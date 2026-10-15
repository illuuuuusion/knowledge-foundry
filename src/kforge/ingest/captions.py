"""Caption selection and strict timestamp-preserving offline normalization."""

from dataclasses import asdict, dataclass
import html
import json
import math
import re
from typing import Protocol

from .adapter import Issue
from .discovery import Video


FORMATS = ('json3', 'vtt', 'srt')
MAX_CAPTION_BYTES = 10 * 1024 * 1024


class CaptionError(Exception):
    def __init__(self, code: str, message: str):
        self.issue = Issue(code, message)
        super().__init__(message)


@dataclass(frozen=True)
class Track:
    language: str
    kind: str  # manual or auto; this is a source label, not a quality assessment
    format: str
    url: str
    name: str | None = None
    headers: dict | None = None

    def provenance(self) -> dict:
        # Request headers may contain credentials; never persist them.
        return {key: value for key, value in asdict(self).items() if key != 'headers'}


class CaptionAdapter(Protocol):
    def tracks(self, video: Video) -> tuple[Track, ...]: ...
    def fetch(self, track: Track) -> bytes: ...


def select_track(tracks: tuple[Track, ...], languages: tuple[str, ...] = ('en',),
                 preference: str = 'manual') -> Track:
    """Language priority precedes kind, then exact locale, format and source order.

    A base language accepts regional variants. An explicit locale does not silently
    select another locale. No arbitrary-language fallback or automatic translation.
    """
    if preference not in {'manual', 'auto'}:
        raise ValueError('preference must be manual or auto')
    if not languages or any(not isinstance(lang, str) or not re.fullmatch(
            r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]+)*', lang) for lang in languages):
        raise ValueError('languages must contain explicit language codes')
    supported = [(index, track) for index, track in enumerate(tracks)
                 if track.kind in {'manual', 'auto'} and track.format in FORMATS]
    if not tracks:
        raise CaptionError('captions_unavailable', 'No caption tracks are available')
    for language in languages:
        lang = language.lower()
        candidates = [(index, track) for index, track in supported
                      if track.language.lower() == lang or
                      ('-' not in lang and track.language.lower().startswith(lang + '-'))]
        if candidates:
            return min(candidates, key=lambda item: (
                item[1].kind != preference, item[1].language.lower() != lang,
                FORMATS.index(item[1].format), item[1].language.lower(), item[0]))[1]
    if not supported:
        raise CaptionError('unsupported', 'Available caption formats are unsupported')
    raise CaptionError('language_unavailable', 'No captions match the requested languages')


def _invalid() -> CaptionError:
    return CaptionError('invalid_captions', 'Caption data has invalid text or timestamps')


def _number(value: object) -> float:
    if type(value) not in (int, float):
        raise _invalid()
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise _invalid() from None
    if not math.isfinite(result) or result < 0:
        raise _invalid()
    return result


def _segment(index: int, start: float, end: float, text: str, timing: dict) -> dict:
    if not math.isfinite(end) or end < start or not isinstance(text, str):
        raise _invalid()
    # Preserve text (including Unicode and inert instruction text) and overlaps.
    return {'source_index': index, 'start': start, 'end': end, 'text': text,
            'source_timing': timing}


def _json3(text: str) -> list[dict]:
    doc = json.loads(text)
    if not isinstance(doc, dict) or not isinstance(doc.get('events'), list):
        raise _invalid()
    segments = []
    leading_controls = []
    for index, event in enumerate(doc['events']):
        if not isinstance(event, dict):
            raise _invalid()
        if 'segs' not in event:  # Window/control event, no transcript content.
            continue
        pieces = event['segs']
        if not isinstance(pieces, list) or any(not isinstance(piece, dict) or
                not isinstance(piece.get('utf8'), str) for piece in pieces):
            raise _invalid()
        start = _number(event.get('tStartMs')) / 1000
        for piece in pieces:
            if 'tOffsetMs' in piece:
                _number(piece['tOffsetMs'])
        content = ''.join(piece['utf8'] for piece in pieces)
        # Live JSON3 can append a line break without a duration. It is formatting,
        # not a timed utterance: retain its raw event/index with adjacent provenance
        # rather than inventing an end time or rejecting the entire transcript.
        if ('dDurationMs' not in event and event.get('aAppend') == 1
                and content in ('\n', '\r\n')):
            control = {'source_index': index, 'event': event}
            if segments:
                segments[-1]['source_timing'].setdefault('formatting_events', []).append(control)
            else:
                leading_controls.append(control)
            continue
        duration = _number(event.get('dDurationMs')) / 1000
        timing = {'unit': 'milliseconds', 'start': event['tStartMs'],
                  'duration': event['dDurationMs'],
                  'event': event}  # Preserve word offsets and other source fields.
        if leading_controls:
            timing['formatting_events'] = leading_controls
            leading_controls = []
        segments.append(_segment(index, start, start + duration, content, timing))
    return segments


def _timestamp(value: str) -> float:
    match = re.fullmatch(r'(?:(\d{2,}):)?([0-5]\d):([0-5]\d)[.,](\d{3})', value)
    if not match:
        raise _invalid()
    hours, minutes, seconds, milliseconds = match.groups()
    return _number(int(hours or 0) * 3600 + int(minutes) * 60 +
                   int(seconds) + int(milliseconds) / 1000)


def _cues(text: str, format: str) -> list[dict]:
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    if format == 'vtt':
        if not lines or not re.fullmatch(r'WEBVTT(?:[ \t].*)?', lines[0]):
            raise _invalid()
        # Header metadata ends at the first blank line.
        try:
            lines = lines[lines.index('') + 1:]
        except ValueError:
            raise _invalid() from None
    blocks = re.split(r'\n[ \t]*\n', '\n'.join(lines).strip())
    result = []
    for block in blocks:
        if not block.strip():
            continue
        rows = block.split('\n')
        if format == 'vtt' and re.match(r'^(NOTE(?:[ \t]|$)|STYLE$|REGION$)', rows[0]):
            continue
        position = 0 if '-->' in rows[0] else 1
        if len(rows) <= position or '-->' not in rows[position]:
            raise _invalid()
        match = re.fullmatch(r'(\S+)\s+-->\s+(\S+)(?:[ \t]+(.*))?', rows[position])
        if not match or len(rows) <= position + 1:
            raise _invalid()
        start, end, settings = match.groups()
        cue_text = '\n'.join(rows[position + 1:])
        # Keep inline timing/markup in provenance; normalized text is readable.
        cleaned = html.unescape(re.sub(r'<[^>]*>', '', cue_text))
        result.append(_segment(len(result), _timestamp(start), _timestamp(end), cleaned,
            {'start': start, 'end': end, 'cue_id': rows[0] if position else None,
             'settings': settings, 'raw_text': cue_text}))
    return result


def normalize(payload: bytes, format: str) -> tuple[dict, ...]:
    if format not in FORMATS:
        raise CaptionError('unsupported', 'Caption format is unsupported')
    if not isinstance(payload, bytes) or len(payload) > MAX_CAPTION_BYTES:
        raise _invalid()
    try:
        text = payload.decode('utf-8-sig')
        segments = _json3(text) if format == 'json3' else _cues(text, format)
        # Validate retained source fields too: JSON must never contain NaN/Infinity.
        json.dumps(segments, ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise _invalid() from None
    if not segments:
        raise CaptionError('captions_unavailable', 'Caption track contains no segments')
    return tuple(sorted(segments, key=lambda segment: (segment['start'], segment['source_index'])))
