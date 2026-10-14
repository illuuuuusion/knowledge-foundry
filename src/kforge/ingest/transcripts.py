"""Serial, resumable ingestion with SQLite authority and repairable JSON views."""

from collections.abc import Callable
from contextlib import closing, contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

from kforge.storage import migrate
from .adapter import Issue, classify_error
from .caption_adapter import YtDlpCaptionAdapter
from .captions import CaptionAdapter, CaptionError, normalize, select_track
from .discovery import Manifest, Video
from .urls import VIDEO_ID, parse_url


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


@dataclass(frozen=True)
class Result:
    video_id: str
    status: str
    attempts: int
    issue: Issue | None = None


class TranscriptStore:
    """One SQLite row and one generated JSON file per video; files are projections.

    All workers for a database share a crash-safe SQLite advisory lock in a sidecar
    database. A simultaneous worker fails before resetting another worker's jobs.
    Use one canonical directory per database; SQLite can repair any missing files.
    """
    def __init__(self, database: Path, canonical_dir: Path):
        self.database = Path(database).resolve()
        self.canonical_dir = Path(canonical_dir).resolve()
        migrate(self.database)

    @contextmanager
    def session(self):
        lock = self.database.with_name(self.database.name + '.lock.sqlite3')
        with closing(sqlite3.connect(lock, timeout=0)) as owner:
            try:
                owner.execute('BEGIN EXCLUSIVE')
            except sqlite3.OperationalError:
                raise RuntimeError('Another ingestion worker owns this database') from None
            try:
                yield
            finally:
                owner.rollback()

    def _execute(self, sql: str, params: tuple = ()):
        with closing(sqlite3.connect(self.database, timeout=10)) as connection:
            with connection:
                cursor = connection.execute(sql, params)
                return cursor.fetchall()

    def register(self, manifest: Manifest) -> str:
        payload = _json(manifest.to_dict())
        identifier = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        self._execute('INSERT OR IGNORE INTO ingestion_manifests VALUES (?, ?)',
                      (identifier, payload))
        for video in manifest.videos:
            self._execute("INSERT OR IGNORE INTO ingestion_jobs (video_id,status) VALUES (?, 'pending')",
                          (video.id,))
        return identifier

    def jobs(self) -> tuple[Result, ...]:
        return tuple(Result(row[0], row[1], row[2], Issue(**json.loads(row[3])) if row[3] else None)
                     for row in self._execute('SELECT video_id,status,attempts,issue '
                                              'FROM ingestion_jobs ORDER BY video_id'))

    def record(self, video_id: str) -> dict | None:
        rows = self._execute('SELECT payload FROM transcripts WHERE video_id=?', (video_id,))
        return json.loads(rows[0][0]) if rows else None

    def begin(self, video_id: str):
        self._execute("UPDATE ingestion_jobs SET status='running', attempts=attempts+1, "
                      'issue=NULL, updated_at=CURRENT_TIMESTAMP WHERE video_id=?', (video_id,))

    def fail(self, video_id: str, issue: Issue):
        self._execute('UPDATE ingestion_jobs SET status=?, issue=?, updated_at=CURRENT_TIMESTAMP '
                      'WHERE video_id=?', ('unsupported' if issue.code == 'unsupported' else 'failed',
                                          _json(asdict(issue)), video_id))

    def save(self, record: dict):
        payload = _json(record)
        with closing(sqlite3.connect(self.database, timeout=10)) as connection:
            with connection:
                connection.execute('INSERT INTO transcripts VALUES (?,?) ON CONFLICT(video_id) '
                                   'DO UPDATE SET payload=excluded.payload', (record['id'], payload))
                connection.execute("UPDATE ingestion_jobs SET status='succeeded', issue=NULL, "
                                   'updated_at=CURRENT_TIMESTAMP WHERE video_id=?', (record['id'],))
        try:
            self.project(record)
        except OSError:
            self.fail(record['id'], Issue('storage_error',
                'Canonical JSON could not be written; rerun to repair', True))
            raise

    def project(self, record: dict):
        identifier = record['video_id']
        if not isinstance(identifier, str) or not VIDEO_ID.fullmatch(identifier):
            raise ValueError('Invalid canonical video ID')
        self.canonical_dir.mkdir(parents=True, exist_ok=True)
        # replace writes a new inode, so a preexisting destination symlink is not followed.
        payload = (_json(record) + '\n').encode('utf-8')
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.canonical_dir, prefix='.transcript-',
                                             delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.canonical_dir / (identifier + '.json'))
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def _merge_provenance(record: dict, video: Video, manifest_id: str) -> dict:
    # Successful captions remain immutable on reruns, but new discovery evidence survives.
    current = asdict(video)
    record['source_ids'] = list(dict.fromkeys((*record['source_ids'], *current['source_ids'])))
    for observation in current['observations']:
        if observation not in record['observations']:
            record['observations'].append(observation)
    if current['metadata'] not in record['metadata_observations']:
        record['metadata_observations'].append(current['metadata'])
    if manifest_id not in record['manifest_ids']:
        record['manifest_ids'].append(manifest_id)
    return record


def ingest(manifest: Manifest, store: TranscriptStore, *, adapter: CaptionAdapter | None = None,
           languages: tuple[str, ...] = ('en',), preference: str = 'manual',
           max_attempts: int = 3, retry_delay: float = 1,
           retry_failed: bool = False, sleep: Callable[[float], None] = time.sleep) -> tuple[Result, ...]:
    """Reruns skip successful downloads; permanent failures need retry_failed=True.

    max_attempts limits retrieval attempts per video per invocation (not lifetime attempts).
    Only classified transient failures retry automatically, with bounded backoff.
    Interruptions remain running and are retried on the next serial invocation.
    """
    if type(max_attempts) is not int or not 1 <= max_attempts <= 10:
        raise ValueError('max_attempts must be between 1 and 10')
    if type(retry_delay) not in (int, float) or not 0 <= retry_delay <= 60:
        raise ValueError('retry_delay must be between 0 and 60 seconds')
    # Validate selection arguments before any persistence/backend calls.
    try:
        select_track((), languages, preference)
    except CaptionError:
        pass
    seen = set()
    for video in manifest.videos:
        if (not VIDEO_ID.fullmatch(video.video_id) or video.id != 'youtube:video:' + video.video_id
                or parse_url(video.url).source_id != video.id or video.id in seen):
            raise ValueError('Manifest contains invalid or duplicate video identities')
        seen.add(video.id)
    backend = adapter if adapter is not None else YtDlpCaptionAdapter()
    results = []
    with store.session():
        manifest_id = store.register(manifest)
        previous = {result.video_id: result for result in store.jobs()}
        for video in manifest.videos:
            job = previous[video.id]
            record = store.record(video.id)
            if record is not None:
                try:
                    store.save(_merge_provenance(record, video, manifest_id))
                    results.append(Result(video.id, 'succeeded', job.attempts))
                except OSError:
                    results.append(Result(video.id, 'projection_failed', job.attempts,
                        Issue('storage_error', 'Canonical JSON could not be written; rerun to repair', True)))
                continue
            if job.status in {'failed', 'unsupported'} and job.issue and not (
                    job.issue.retryable or retry_failed):
                results.append(job)
                continue
            for attempt in range(max_attempts):
                store.begin(video.id)
                try:
                    track = select_track(backend.tracks(video), languages, preference)
                    payload = backend.fetch(track)
                    segments = normalize(payload, track.format)
                    record = asdict(video)
                    record.update(schema_version=1, metadata_observations=[record['metadata']],
                        manifest_ids=[manifest_id], segments=segments,
                        transcript={'track': track.provenance(),
                            'adapter': type(backend).__name__,
                            'payload_sha256': hashlib.sha256(payload).hexdigest(),
                            'retrieved_at': datetime.now(timezone.utc).isoformat(),
                            'selection': {'languages': languages, 'preference': preference}},
                        verification_status='unverified',
                        content_trust='untrusted_source_text', confidence='unknown',
                        visual_dependencies='not_assessed')
                except Exception as exc:
                    issue = exc.issue if isinstance(exc, CaptionError) else classify_error(exc)
                    store.fail(video.id, issue)
                    if issue.retryable and attempt + 1 < max_attempts:
                        sleep(min(retry_delay * (2 ** attempt), 60))
                        continue
                    results.append(Result(video.id, 'unsupported' if issue.code == 'unsupported' else
                                          'failed', job.attempts + attempt + 1, issue))
                    break
                # Storage failures must not be misclassified as caption/network errors.
                try:
                    store.save(record)
                    results.append(Result(video.id, 'succeeded', job.attempts + attempt + 1))
                except OSError:
                    results.append(Result(video.id, 'projection_failed', job.attempts + attempt + 1,
                        Issue('storage_error', 'Canonical JSON could not be written; rerun to repair', True)))
                break
    return tuple(results)
