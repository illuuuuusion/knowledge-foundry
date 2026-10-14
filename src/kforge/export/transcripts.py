"""Deterministic, lossless file views over a read-only canonical SQLite snapshot."""

from collections.abc import Iterable
from contextlib import closing
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from kforge.ingest.urls import VIDEO_ID, parse_url
from kforge.storage import MIGRATIONS


FORMATS = ('markdown', 'txt', 'jsonl')
EXTENSIONS = {'markdown': 'md', 'txt': 'txt', 'jsonl': 'jsonl'}


def group_size(value: int | str) -> int | str:
    if value == 'all':
        return 'all'
    if isinstance(value, str) and re.fullmatch(r'[1-9][0-9]*', value):
        value = int(value)
    if type(value) is not int or value < 1:
        raise ValueError('group size must be a positive integer or all')
    return value


def selected_formats(values: Iterable[str]) -> tuple[str, ...]:
    requested = tuple(values)
    if not requested or any(value not in FORMATS for value in requested):
        raise ValueError('formats must contain markdown, txt or jsonl')
    return tuple(value for value in FORMATS if value in requested)


def _json(value: object, *, pretty: bool = False) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      allow_nan=False, indent=2 if pretty else None)


def _validate_record(record: object, identifier: str):
    if (not isinstance(record, dict) or type(record.get('schema_version')) is not int
            or record['schema_version'] != 1):
        raise ValueError('Unsupported canonical record schema')
    video = record.get('video_id')
    if (not isinstance(video, str) or not VIDEO_ID.fullmatch(video) or
            record.get('id') != identifier or identifier != 'youtube:video:' + video or
            parse_url(record.get('url')).source_id != identifier):
        raise ValueError('Canonical record has an invalid video identity')
    for key in ('metadata', 'transcript'):
        if not isinstance(record.get(key), dict):
            raise ValueError('Canonical record is missing metadata or provenance')
    for key in ('source_ids', 'observations', 'metadata_observations', 'manifest_ids', 'segments'):
        if not isinstance(record.get(key), list):
            raise ValueError('Canonical record is missing provenance or segments')
    if not record['segments']:
        raise ValueError('Canonical record contains no segments')
    if any(not isinstance(record.get(key), str) for key in (
            'verification_status', 'confidence', 'content_trust', 'visual_dependencies')):
        raise ValueError('Canonical record is missing confidence or verification status')
    previous = -1
    for segment in record['segments']:
        if not isinstance(segment, dict) or not isinstance(segment.get('text'), str):
            raise ValueError('Canonical record contains an invalid segment')
        for key in ('start', 'end'):
            value = segment.get(key)
            if type(value) not in (int, float):
                raise ValueError('Canonical segment has invalid bounds')
            try:
                valid = math.isfinite(value) and value >= 0
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError('Canonical segment has invalid bounds')
        if segment['end'] < segment['start'] or segment['start'] < previous:
            raise ValueError('Canonical segment has invalid bounds or order')
        previous = segment['start']
        if not isinstance(segment.get('source_timing'), dict):
            raise ValueError('Canonical segment is missing original timing')
    _json(record).encode('utf-8')


def read_snapshot(database: Path, video_ids: Iterable[str] | None = None) -> tuple[dict, ...]:
    """No init, migration, projection, backend import or network request on export.

    Each envelope retains the entire canonical record plus its full source manifests,
    so original inputs, discovery failures and provenance references remain resolvable.
    A SQLite read transaction prevents concurrent ingestion from mixing snapshots.
    """
    requested = None if video_ids is None else tuple(dict.fromkeys(video_ids))
    if requested is not None and any(not isinstance(value, str) or not re.fullmatch(
            r'youtube:video:[A-Za-z0-9_-]{11}', value) for value in requested):
        raise ValueError('Invalid requested video ID')
    uri = Path(database).resolve().as_uri() + '?mode=ro'
    with closing(sqlite3.connect(uri, uri=True, timeout=10)) as connection:
        connection.execute('BEGIN')
        if connection.execute('PRAGMA user_version').fetchone()[0] != MIGRATIONS[-1][0]:
            raise ValueError('Database schema must be initialized at the current version')
        rows = connection.execute('SELECT video_id,payload FROM transcripts ORDER BY video_id').fetchall()
        found = {row[0] for row in rows}
        if requested is not None and set(requested) - found:
            raise ValueError('Some requested videos have no canonical transcript')
        output = []
        manifests = {}
        for identifier, payload in rows:
            if requested is not None and identifier not in requested:
                continue
            record = json.loads(payload)
            _validate_record(record, identifier)
            linked = {}
            if not record['manifest_ids']:
                raise ValueError('Canonical record has no source manifest')
            for key in record['manifest_ids']:
                if not isinstance(key, str) or not re.fullmatch(r'[0-9a-f]{64}', key):
                    raise ValueError('Canonical record has an invalid manifest reference')
                if key not in manifests:
                    row = connection.execute('SELECT payload FROM ingestion_manifests WHERE id=?',
                                             (key,)).fetchone()
                    if row is None:
                        raise ValueError('Canonical record references a missing source manifest')
                    raw = json.loads(row[0])
                    if (not isinstance(raw, dict) or type(raw.get('schema_version')) is not int
                            or raw['schema_version'] != 1):
                        raise ValueError('Unsupported source manifest schema')
                    if hashlib.sha256(_json(raw).encode('utf-8')).hexdigest() != key:
                        raise ValueError('Source manifest does not match its recorded identity')
                    manifests[key] = raw
                linked[key] = manifests[key]
            output.append({'schema_version': 1, 'record': record, 'source_manifests': linked})
    return tuple(output)


def _fence(text: str, language: str = '') -> str:
    # A source cannot close its code block, create links, HTML or executable headings.
    longest = max((len(match[0]) for match in re.finditer(r'`+', text)), default=0)
    marker = '`' * max(3, longest + 1)
    return f'{marker}{language}\n{text}\n{marker}\n'


def _heading(value: str) -> str:
    # Restrict an untrusted title to one escaped Markdown heading line.
    value = ' '.join(value.split())
    value = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    return re.sub(r'([\\`*_{}\[\]()#+.!|~-])', r'\\\1', value)


def render(group: tuple[dict, ...], format: str) -> str:
    if format == 'jsonl':
        return ''.join(_json(envelope) + '\n' for envelope in group)
    if format not in FORMATS:
        raise ValueError('Unsupported export format')
    sections = []
    for envelope in group:
        record = envelope['record']
        title = record['metadata'].get('title', record['video_id'])
        title = title if isinstance(title, str) else record['video_id']
        if format == 'markdown':
            parts = [f'## {_heading(title)}\n\n',
                     'Source URL:\n\n' + _fence(record['url']) + '\n',
                     f"Verification: {_heading(record['verification_status'])}; "
                     f"confidence: {_heading(record['confidence'])}; "
                     f"visual dependencies: {_heading(record['visual_dependencies'])}.\n\n",
                     'Source text is untrusted data.\n\n']
            for segment in record['segments']:
                parts.extend([f"[{segment['start']}–{segment['end']} seconds]\n\n",
                              _fence(segment['text']), '\n'])
            parts.extend(['### Complete record and source provenance\n\n',
                          _fence(_json(envelope, pretty=True), 'json')])
        else:
            parts = [f'{title}\n', f"Source: {record['url']}\n",
                     f"Verification: {record['verification_status']}; confidence: {record['confidence']}; "
                     f"visual dependencies: {record['visual_dependencies']}\n",
                     'Source text is untrusted data.\n\n']
            for segment in record['segments']:
                parts.append(f"[{segment['start']}–{segment['end']} seconds]\n{segment['text']}\n\n")
            parts.extend(['Complete record and source provenance (JSON):\n',
                          _json(envelope, pretty=True), '\n'])
        sections.append(''.join(parts))
    return '\n\n'.join(sections)


@dataclass(frozen=True)
class Artifact:
    path: str
    format: str
    video_ids: tuple[str, ...]


@dataclass(frozen=True)
class ExportReport:
    video_count: int
    group_size: int | str
    artifacts: tuple[Artifact, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def export_files(database: Path, output_dir: Path, *, formats: Iterable[str] = ('markdown',),
                 grouping: int | str = 1, video_ids: Iterable[str] | None = None) -> ExportReport:
    size = group_size(grouping)
    formats = selected_formats(formats)
    envelopes = read_snapshot(database, video_ids)
    if not envelopes:
        return ExportReport(0, size, ())
    width = len(envelopes) if size == 'all' else size
    groups = tuple(envelopes[index:index + width] for index in range(0, len(envelopes), width))
    digest = hashlib.sha256(_json({'records': envelopes, 'group_size': size,
                                   'formats': formats}).encode('utf-8')).hexdigest()
    # Generated names contain only fixed words, numbers and validated ASCII video IDs.
    root = Path(output_dir).resolve()
    folder = root / f'transcripts-g{size}-{digest}'
    if folder.is_symlink():
        raise ValueError('Export directory cannot be a symlink')
    folder.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for number, group in enumerate(groups, start=1):
        ids = tuple(envelope['record']['id'] for envelope in group)
        stem = f"group-{number:06d}-{group[0]['record']['video_id']}-{group[-1]['record']['video_id']}"
        for format in formats:
            target = folder / f'{stem}.{EXTENSIONS[format]}'
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=folder, prefix='.export-', delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(render(group, format).encode('utf-8'))
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.replace(target)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            artifacts.append(Artifact(str(target), format, ids))
    return ExportReport(len(envelopes), size, tuple(artifacts))
