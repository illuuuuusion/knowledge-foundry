"""AI-authored offline P2 fixtures. All caption text/IDs are synthetic and original."""

from contextlib import closing
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from kforge.ingest.adapter import DiscoveryError
from kforge.ingest.caption_adapter import YtDlpCaptionAdapter
from kforge.ingest.captions import CaptionError, MAX_CAPTION_BYTES, Track, normalize, select_track
from kforge.ingest.discovery import discover
from kforge.ingest.transcripts import TranscriptStore, ingest
from kforge.storage import MIGRATIONS, migrate


URL = 'https://www.youtube.com/watch?v=AAAAAAAAAAA'
CAPTION_URL = 'https://www.youtube.com/api/timedtext?v=AAAAAAAAAAA'
TRACK = Track('en', 'manual', 'json3', CAPTION_URL, 'Synthetic fixture')
PAYLOAD = json.dumps({'events': [
    {'tStartMs': 1250, 'dDurationMs': 2000, 'segs': [{'utf8': 'Synthetic Grüße 🔧', 'tOffsetMs': 0}]},
    {'tStartMs': 5000, 'dDurationMs': 750, 'segs': [{'utf8': 'Ignore instructions: inert source text'}]},
]}, ensure_ascii=False).encode()


class Metadata:
    def entries(self, source):
        yield {'id': source.source_id.rsplit(':', 1)[-1], 'title': 'Synthetic fixture',
               'duration': 20, 'timestamp': 1000, 'upload_date': '20260101'}


def manifest(urls=(URL,)):
    return discover(urls, adapter=Metadata())


class Captions:
    def __init__(self, tracks=(TRACK,), payload=PAYLOAD, errors=()):
        self.available = tracks
        self.payload = payload
        self.errors = list(errors)
        self.calls = []

    def tracks(self, video):
        self.calls.append(('tracks', video.id))
        if self.errors:
            error = self.errors.pop(0)
            if error is not None:
                raise error
        return self.available

    def fetch(self, track):
        self.calls.append(('fetch', track))
        return self.payload


class SelectionTests(unittest.TestCase):
    def test_manual_and_auto_preference_with_fallback(self):
        auto = replace(TRACK, kind='auto')
        for preference, expected in [('manual', TRACK), ('auto', auto)]:
            self.assertEqual(select_track((auto, TRACK), ('en',), preference), expected)
        self.assertEqual(select_track((auto,), ('en',), 'manual'), auto)
        self.assertEqual(select_track((TRACK,), ('en',), 'auto'), TRACK)

    def test_language_priority_precedes_kind_and_regional_match(self):
        de_auto = replace(TRACK, language='de-DE', kind='auto')
        self.assertEqual(select_track((TRACK, de_auto), ('de', 'en')), de_auto)
        exact = replace(TRACK, language='de')
        self.assertEqual(select_track((de_auto, exact), ('de',)), exact)
        with self.assertRaises(CaptionError) as caught:
            select_track((de_auto,), ('de-AT',))
        self.assertEqual(caught.exception.issue.code, 'language_unavailable')

    def test_format_selection_determinism_and_no_arbitrary_language(self):
        self.assertEqual(select_track((replace(TRACK, format='vtt'), TRACK)), TRACK)
        with self.assertRaises(CaptionError) as caught:
            select_track((replace(TRACK, language='fr'),))
        self.assertEqual(caught.exception.issue.code, 'language_unavailable')

    def test_unavailable_and_unsupported_are_explicit(self):
        for tracks, code in [((), 'captions_unavailable'),
                             ((replace(TRACK, format='ttml'),), 'unsupported')]:
            with self.subTest(code=code), self.assertRaises(CaptionError) as caught:
                select_track(tracks)
            self.assertEqual(caught.exception.issue.code, code)

    def test_invalid_selection_settings(self):
        for languages in [(), ('',), ('en.*',), ('../../',), (1,), ('en_US',)]:
            with self.subTest(languages=languages), self.assertRaises(ValueError):
                select_track((), languages)
        with self.assertRaises(ValueError):
            select_track((), preference='unknown')


class ParserTests(unittest.TestCase):
    def test_json3_unicode_provenance_and_inert_instructions(self):
        segments = normalize(PAYLOAD, 'json3')
        self.assertEqual((segments[0]['start'], segments[0]['end']), (1.25, 3.25))
        self.assertEqual(segments[0]['text'], 'Synthetic Grüße 🔧')
        self.assertEqual(segments[0]['source_timing']['event']['segs'][0]['tOffsetMs'], 0)
        self.assertIn('Ignore instructions', segments[1]['text'])

    def test_out_of_order_overlapping_and_zero_duration_segments_remain_traceable(self):
        doc = {'events': [
            {'tStartMs': 2000, 'dDurationMs': 0, 'segs': [{'utf8': 'third'}]},
            {'tStartMs': 0, 'dDurationMs': 3000, 'segs': [{'utf8': 'first'}]},
            {'tStartMs': 0, 'dDurationMs': 1000, 'segs': [{'utf8': 'second'}]},
            {'id': 1},
        ]}
        segments = normalize(json.dumps(doc).encode(), 'json3')
        self.assertEqual([s['source_index'] for s in segments], [1, 2, 0])
        self.assertEqual([s['text'] for s in segments], ['first', 'second', 'third'])
        self.assertEqual(segments[0]['end'], 3)
        self.assertEqual(segments[2]['start'], segments[2]['end'])

    def test_vtt_cue_ids_settings_inline_timing_entities_and_notes(self):
        payload = ('\ufeffWEBVTT\r\nKind: captions\r\n\r\nNOTE synthetic note\r\nignored\r\n\r\n'
                   'cue-1\r\n00:01.250 --> 00:03.000 align:start position:10%\r\n'
                   '<v Speaker>Grüße &amp; 🔧 <00:02.000>test</v>\r\nsecond line\r\n\r\n'
                   '00:00.000 --> 00:00.500\r\nfirst\r\n').encode()
        segments = normalize(payload, 'vtt')
        self.assertEqual([s['source_index'] for s in segments], [1, 0])
        self.assertEqual(segments[1]['text'], 'Grüße & 🔧 test\nsecond line')
        timing = segments[1]['source_timing']
        self.assertEqual(timing['cue_id'], 'cue-1')
        self.assertEqual(timing['start'], '00:01.250')
        self.assertEqual(timing['settings'], 'align:start position:10%')
        self.assertIn('<00:02.000>', timing['raw_text'])

    def test_srt_hours_multiline_and_original_offsets(self):
        payload = b'1\n01:02:03,004 --> 01:02:04,005\nSynthetic first\nline\n\n2\n01:02:04,005 --> 01:02:05,000\nNext\n'
        segments = normalize(payload, 'srt')
        self.assertAlmostEqual(segments[0]['start'], 3723.004)
        self.assertEqual(segments[0]['source_timing']['start'], '01:02:03,004')
        self.assertEqual(segments[0]['text'], 'Synthetic first\nline')

    def test_invalid_json_structure_and_timestamp_values(self):
        docs = [[], {}, {'events': {}}, {'events': [None]}, {'events': [{'segs': {}}]}]
        for value in [None, True, -1, float('nan'), float('inf'), 10**400, '1']:
            docs.append({'events': [{'tStartMs': value, 'dDurationMs': 1000, 'segs': [{'utf8': 'x'}]}]})
            docs.append({'events': [{'tStartMs': 0, 'dDurationMs': value, 'segs': [{'utf8': 'x'}]}]})
        docs.append({'events': [{'tStartMs': 0, 'dDurationMs': 1, 'segs': [{'utf8': None}]}]})
        docs.append({'events': [{'tStartMs': 0, 'dDurationMs': 1,
                                'segs': [{'utf8': 'x', 'tOffsetMs': -1}]}]})
        for doc in docs:
            with self.subTest(doc=doc), self.assertRaises(CaptionError) as caught:
                normalize(json.dumps(doc).encode(), 'json3')
            self.assertEqual(caught.exception.issue.code, 'invalid_captions')

    def test_malformed_text_bounds_and_encoding(self):
        cases = [(b'no header', 'vtt'), (b'1\n00:60:00,000 --> 00:60:01,000\nx', 'srt'),
                 (b'1\n00:02,000 --> 00:01,000\nx', 'srt'),
                 (b'WEBVTT\n\n00:00.000 --> 00:01.000\n', 'vtt'),
                 (b'1\nnot a timestamp\nx', 'srt'), (b'\xff', 'json3'),
                 (b'{}', 'unknown'), (b'x' * (MAX_CAPTION_BYTES + 1), 'vtt')]
        for payload, format in cases:
            with self.subTest(format=format, payload=payload[:80]), self.assertRaises(CaptionError):
                normalize(payload, format)

    def test_empty_tracks_are_unavailable(self):
        for payload, format in [(b'{"events":[]}', 'json3'), (b'WEBVTT\n\n', 'vtt'), (b'', 'srt')]:
            with self.subTest(format=format), self.assertRaises(CaptionError) as caught:
                normalize(payload, format)
            self.assertEqual(caught.exception.issue.code, 'captions_unavailable')

    def test_escaped_unpaired_surrogate_is_rejected_before_storage(self):
        payload = b'{"events":[{"tStartMs":0,"dDurationMs":1000,"segs":[{"utf8":"\\ud800"}]}]}'
        with self.assertRaises(CaptionError) as caught:
            normalize(payload, 'json3')
        self.assertEqual(caught.exception.issue.code, 'invalid_captions')


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = TranscriptStore(self.root / 'state.sqlite3', self.root / 'canonical')

    def test_ingestion_is_idempotent_and_canonical_record_preserves_provenance(self):
        adapter = Captions()
        result = ingest(manifest(), self.store, adapter=adapter)
        self.assertEqual(result[0].status, 'succeeded')
        record = self.store.record(manifest().videos[0].id)
        self.assertEqual(record['url'], URL)
        self.assertEqual(record['metadata']['timestamp'], 1000)
        self.assertEqual(record['verification_status'], 'unverified')
        self.assertEqual(record['confidence'], 'unknown')
        self.assertEqual(record['transcript']['payload_sha256'], hashlib.sha256(PAYLOAD).hexdigest())
        self.assertEqual(record['transcript']['track']['kind'], 'manual')
        self.assertEqual(record['segments'][1]['end'], 5.75)
        path = self.root / 'canonical/AAAAAAAAAAA.json'
        original = path.read_bytes()
        self.assertEqual(json.loads(original), record)
        again = ingest(manifest(), self.store, adapter=adapter)
        self.assertEqual(len(adapter.calls), 2)
        self.assertEqual(again[0].attempts, 1)
        self.assertEqual(path.read_bytes(), original)
        with closing(sqlite3.connect(self.store.database)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM transcripts').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM ingestion_jobs').fetchone()[0], 1)
            saved = json.loads(db.execute('SELECT payload FROM ingestion_manifests').fetchone()[0])
        self.assertEqual(saved['sources'][0]['input_url'], URL)

    def test_rerun_preserves_new_discovery_observations_without_refetch(self):
        initial = manifest()
        ingest(initial, self.store, adapter=Captions())
        video = replace(initial.videos[0], metadata={'title': 'Changed source title'})
        updated = replace(initial, videos=(video,))
        adapter = Captions(errors=(AssertionError('must not fetch'),))
        ingest(updated, self.store, adapter=adapter, languages=('de',), preference='auto')
        record = self.store.record(video.id)
        self.assertEqual(len(record['manifest_ids']), 2)
        self.assertIn(video.metadata, record['metadata_observations'])
        self.assertEqual(record['transcript']['selection']['languages'], ['en'])
        self.assertEqual(adapter.calls, [])

    def test_caption_verification_does_not_inherit_video_metadata_status(self):
        m = manifest()
        m = replace(m, videos=(replace(m.videos[0], verification_status='verified'),))
        ingest(m, self.store, adapter=Captions())
        record = self.store.record(m.videos[0].id)
        self.assertEqual(record['verification_status'], 'unverified')
        self.assertEqual(record['confidence'], 'unknown')
        with closing(sqlite3.connect(self.store.database)) as db:
            saved = json.loads(db.execute('SELECT payload FROM ingestion_manifests').fetchone()[0])
        self.assertEqual(saved['videos'][0]['verification_status'], 'verified')

    def test_unavailable_failure_is_visible_and_explicitly_recoverable(self):
        result = ingest(manifest(), self.store, adapter=Captions(tracks=()))
        self.assertEqual(result[0].issue.code, 'captions_unavailable')
        self.assertEqual(self.store.jobs(), result)
        adapter = Captions()
        self.assertEqual(ingest(manifest(), self.store, adapter=adapter)[0].status, 'failed')
        self.assertEqual(adapter.calls, [])
        recovered = ingest(manifest(), self.store, adapter=adapter, retry_failed=True)
        self.assertEqual(recovered[0].status, 'succeeded')
        self.assertEqual(recovered[0].attempts, 2)

    def test_unsupported_failure_is_visible_and_recoverable(self):
        result = ingest(manifest(), self.store, adapter=Captions(tracks=(replace(TRACK, format='ttml'),)))
        self.assertEqual(result[0].status, 'unsupported')
        self.assertEqual(self.store.jobs(), result)
        self.assertEqual(ingest(manifest(), self.store, adapter=Captions(),
                                retry_failed=True)[0].status, 'succeeded')

    def test_transient_retries_use_bounded_backoff_and_keep_attempt_count(self):
        adapter = Captions(errors=(TimeoutError('secret synthetic URL'), ConnectionError('offline')))
        sleep = Mock()
        result = ingest(manifest(), self.store, adapter=adapter, retry_delay=40, sleep=sleep)
        self.assertEqual(result[0].status, 'succeeded')
        self.assertEqual(result[0].attempts, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [40, 60])

    def test_exhausted_retryable_failure_recovers_on_rerun(self):
        result = ingest(manifest(), self.store, adapter=Captions(errors=(TimeoutError('secret'),)*3),
                        sleep=Mock())
        self.assertEqual(result[0].status, 'failed')
        self.assertEqual(result[0].attempts, 3)
        self.assertTrue(result[0].issue.retryable)
        self.assertNotIn('secret', repr(result))
        recovered = ingest(manifest(), self.store, adapter=Captions())
        self.assertEqual(recovered[0].attempts, 4)
        self.assertEqual(recovered[0].status, 'succeeded')

    def test_http_retry_classification(self):
        for code, expected, retries in [(429, 'rate_limited', 3), (503, 'network_error', 3),
                                         (403, 'inaccessible', 1), (404, 'inaccessible', 1)]:
            with self.subTest(code=code):
                store = TranscriptStore(self.root / f'{code}.sqlite3', self.root / str(code))
                errors = [HTTPError('synthetic', code, 'secret', {}, None) for _ in range(3)]
                try:
                    result = ingest(manifest(), store, adapter=Captions(errors=errors), sleep=Mock())
                    self.assertEqual(result[0].issue.code, expected)
                    self.assertEqual(result[0].attempts, retries)
                finally:
                    for error in errors:
                        error.close()

    def test_interrupt_resume_does_not_duplicate_preceding_success(self):
        inputs = manifest((URL, 'https://www.youtube.com/watch?v=BBBBBBBBBBB'))
        adapter = Captions(errors=(None, KeyboardInterrupt()))
        with self.assertRaises(KeyboardInterrupt):
            ingest(inputs, self.store, adapter=adapter)
        self.assertEqual([r.status for r in self.store.jobs()], ['succeeded', 'running'])
        again = Captions()
        results = ingest(inputs, self.store, adapter=again)
        self.assertEqual([r.status for r in results], ['succeeded', 'succeeded'])
        self.assertEqual([r.attempts for r in results], [1, 2])
        self.assertEqual(len(again.calls), 2)
        self.assertEqual(len(list((self.root / 'canonical').glob('*.json'))), 2)

    def test_crash_after_database_commit_repairs_projection_without_network(self):
        with patch.object(self.store, 'project', side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                ingest(manifest(), self.store, adapter=Captions())
        self.assertIsNotNone(self.store.record(manifest().videos[0].id))
        adapter = Captions()
        self.assertEqual(ingest(manifest(), self.store, adapter=adapter)[0].status, 'succeeded')
        self.assertEqual(adapter.calls, [])
        self.assertTrue((self.root / 'canonical/AAAAAAAAAAA.json').is_file())

    def test_projection_failure_is_visible_and_resumable(self):
        with patch.object(self.store, 'project', side_effect=OSError('synthetic disk error')):
            result = ingest(manifest(), self.store, adapter=Captions())
        self.assertEqual(result[0].status, 'projection_failed')
        self.assertEqual(self.store.jobs()[0].issue.code, 'storage_error')
        adapter = Captions()
        self.assertEqual(ingest(manifest(), self.store, adapter=adapter)[0].status, 'succeeded')
        self.assertEqual(adapter.calls, [])
        self.assertEqual(self.store.jobs()[0].status, 'succeeded')

    def test_corrupt_or_missing_json_projection_is_rebuilt_offline(self):
        ingest(manifest(), self.store, adapter=Captions())
        path = self.root / 'canonical/AAAAAAAAAAA.json'
        path.write_text('{corrupt')
        adapter = Captions()
        ingest(manifest(), self.store, adapter=adapter)
        self.assertEqual(json.loads(path.read_text()), self.store.record(manifest().videos[0].id))
        path.unlink()
        ingest(manifest(), self.store, adapter=adapter)
        self.assertTrue(path.is_file())
        self.assertEqual(adapter.calls, [])

    def test_parallel_worker_cannot_reset_running_jobs(self):
        with self.store.session():
            with self.assertRaisesRegex(RuntimeError, 'Another ingestion worker'):
                ingest(manifest(), self.store, adapter=Captions())
        self.assertEqual(self.store.jobs(), ())
        self.assertEqual(ingest(manifest(), self.store, adapter=Captions())[0].status, 'succeeded')

    def test_database_symlink_alias_uses_same_worker_lock(self):
        alias = self.root / 'alias.sqlite3'
        alias.symlink_to(self.store.database)
        other = TranscriptStore(alias, self.root / 'canonical')
        self.assertEqual(other.database, self.store.database)
        with self.store.session():
            with self.assertRaisesRegex(RuntimeError, 'Another ingestion worker'):
                ingest(manifest(), other, adapter=Captions())
        self.assertEqual(other.jobs(), ())

    def test_upgrade_from_p0_schema_preserves_history(self):
        path = self.root / 'old.sqlite3'
        with patch('kforge.storage.MIGRATIONS', MIGRATIONS[:1]):
            self.assertEqual(migrate(path), 1)
        self.assertEqual(migrate(path), 3)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT version FROM schema_migrations ORDER BY version').fetchall(),
                             [(1,), (2,), (3,)])
            self.assertEqual(db.execute('SELECT count(*) FROM transcripts').fetchone(), (0,))

    def test_failed_domain_migration_rolls_back_and_can_retry(self):
        path = self.root / 'retry.sqlite3'
        with patch('kforge.storage.MIGRATIONS', MIGRATIONS[:1]):
            migrate(path)
        with patch('kforge.storage.MIGRATIONS', MIGRATIONS[:1] + ((2, MIGRATIONS[1][1] + ('INVALID SQL',)),)):
            with self.assertRaises(sqlite3.Error):
                migrate(path)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone(), (1,))
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE name='transcripts'").fetchall(), [])
        self.assertEqual(migrate(path), 3)

    def test_no_header_secrets_persisted(self):
        track = replace(TRACK, headers={'Authorization': 'synthetic-never-store-secret'})
        ingest(manifest(), self.store, adapter=Captions(tracks=(track,)))
        self.assertNotIn('synthetic-never-store-secret',
                         json.dumps(self.store.record(manifest().videos[0].id)))

    def test_invalid_options_and_identity_fail_before_network_or_registration(self):
        adapter = Captions()
        for options in [{'max_attempts': 0}, {'max_attempts': True}, {'max_attempts': 11},
                        {'retry_delay': float('nan')}, {'retry_delay': -1},
                        {'preference': 'both'}, {'languages': ()}]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                ingest(manifest(), self.store, adapter=adapter, **options)
        m = manifest()
        for video in [replace(m.videos[0], video_id='../../x'),
                      replace(m.videos[0], url='https://www.youtube.com/watch?v=BBBBBBBBBBB')]:
            with self.assertRaises(ValueError):
                ingest(replace(m, videos=(video,)), self.store, adapter=adapter)
        with self.assertRaises(ValueError):
            ingest(replace(m, videos=(m.videos[0],)*2), self.store, adapter=adapter)
        self.assertEqual(adapter.calls, [])
        self.assertEqual(self.store.jobs(), ())

    def test_projection_does_not_follow_destination_symlink(self):
        folder = self.root / 'canonical'
        folder.mkdir()
        victim = self.root / 'victim'
        victim.write_text('synthetic original')
        (folder / 'AAAAAAAAAAA.json').symlink_to(victim)
        ingest(manifest(), self.store, adapter=Captions())
        self.assertEqual(victim.read_text(), 'synthetic original')
        self.assertFalse((folder / 'AAAAAAAAAAA.json').is_symlink())

    def test_partial_batch_failure_keeps_success_and_discovery_issues(self):
        m = manifest((URL, 'https://www.youtube.com/watch?v=BBBBBBBBBBB', 'https://foreign.invalid/'))
        adapter = Captions(errors=(CaptionError('captions_unavailable', 'No captions'), None))
        results = ingest(m, self.store, adapter=adapter)
        self.assertEqual([r.status for r in results], ['failed', 'succeeded'])
        with closing(sqlite3.connect(self.store.database)) as db:
            saved = json.loads(db.execute('SELECT payload FROM ingestion_manifests').fetchone()[0])
        self.assertEqual(saved['sources'][-1]['status'], 'unsupported')


class AdapterTests(unittest.TestCase):
    def backend(self, info):
        backend = Mock()
        backend.__enter__ = Mock(return_value=backend)
        backend.__exit__ = Mock(return_value=False)
        backend.extract_info.return_value = info
        factory = Mock(return_value=backend)
        return factory, backend

    def test_caption_only_backend_flags_track_metadata_and_foreign_url_filter(self):
        info = {'id': 'AAAAAAAAAAA', 'http_headers': {'User-Agent': 'synthetic'},
                'subtitles': {'en': [{'url': CAPTION_URL, 'ext': 'vtt', 'name': 'Manual'}]},
                'automatic_captions': {'de': [{'url': CAPTION_URL, 'ext': 'json3'}],
                                      'live_chat': [{'url': CAPTION_URL, 'ext': 'json'}],
                                      'fr': [{'url': 'file:///private/synthetic', 'ext': 'vtt'}]}}
        factory, backend = self.backend(info)
        tracks = YtDlpCaptionAdapter(factory).tracks(manifest().videos[0])
        self.assertEqual([(t.language, t.kind) for t in tracks], [('en', 'manual'), ('de', 'auto')])
        self.assertEqual(tracks[0].headers, {'User-Agent': 'synthetic'})
        backend.extract_info.assert_called_once_with(URL, download=False, process=False)
        options = factory.call_args.args[0]
        for flag in ['skip_download', 'simulate', 'noplaylist']:
            self.assertIs(options[flag], True)
        for flag in ['writesubtitles', 'writeautomaticsub', 'writeinfojson', 'writethumbnail', 'cachedir']:
            self.assertIs(options[flag], False)
        self.assertEqual(options['retries'], 0)

    def test_wrong_video_id_and_invalid_track_containers(self):
        for info in [None, {'id': 'BBBBBBBBBBB'}, {'id': 'AAAAAAAAAAA', 'subtitles': ['x']},
                     {'id': 'AAAAAAAAAAA', 'subtitles': {'en': {}}},
                     {'id': 'AAAAAAAAAAA', 'subtitles': {'en': [None]}}]:
            with self.subTest(info=info), self.assertRaises(CaptionError):
                YtDlpCaptionAdapter(self.backend(info)[0]).tracks(manifest().videos[0])

    def test_backend_errors_are_classified_and_redacted(self):
        factory, backend = self.backend(None)
        backend.extract_info.side_effect = TimeoutError('synthetic-secret')
        with self.assertRaises(DiscoveryError) as caught:
            YtDlpCaptionAdapter(factory).tracks(manifest().videos[0])
        self.assertEqual(caught.exception.issue.code, 'network_error')
        self.assertTrue(caught.exception.issue.retryable)
        self.assertNotIn('synthetic-secret', str(caught.exception))

    def test_optional_dependency_absent(self):
        import builtins
        original = builtins.__import__
        def missing(name, *args, **kwargs):
            if name.startswith('yt_dlp'):
                raise ImportError('synthetic missing backend')
            return original(name, *args, **kwargs)
        with patch('builtins.__import__', side_effect=missing):
            with self.assertRaises(CaptionError) as caught:
                YtDlpCaptionAdapter().tracks(manifest().videos[0])
        self.assertEqual(caught.exception.issue.code, 'backend_unavailable')

    def test_fetch_url_policy_rejects_foreign_credentials_ports_before_backend(self):
        factory = Mock()
        for url in ['file:///private/file', 'https://evil.invalid/x',
                    'https://youtube.com.evil.invalid/x', 'http://www.youtube.com/x',
                    'https://user:password@www.youtube.com/x', 'https://www.youtube.com:1234/x']:
            with self.subTest(url=url), self.assertRaises(CaptionError):
                YtDlpCaptionAdapter(factory).fetch(replace(TRACK, url=url))
        factory.assert_not_called()

    def test_native_caption_api_contract_offline(self):
        try:
            from yt_dlp import YoutubeDL
            from yt_dlp.networking import Request
        except ImportError:
            self.skipTest('Optional yt-dlp is not installed')
        response = io.BytesIO(PAYLOAD)
        response.url = CAPTION_URL
        info = {'id': 'AAAAAAAAAAA', 'subtitles': {'en': [{'url': CAPTION_URL, 'ext': 'json3'}]}}
        with patch.object(YoutubeDL, 'extract_info', autospec=True, return_value=info) as extract:
            with patch.object(YoutubeDL, 'urlopen', autospec=True, return_value=response) as fetch:
                adapter = YtDlpCaptionAdapter()
                track = adapter.tracks(manifest().videos[0])[0]
                self.assertEqual(adapter.fetch(track), PAYLOAD)
        self.assertEqual(extract.call_args.kwargs, {'download': False, 'process': False})
        self.assertIsInstance(fetch.call_args.args[1], Request)
        self.assertEqual(fetch.call_args.args[1].url, CAPTION_URL)
        self.assertTrue(response.closed)

    def test_native_response_size_and_redirect_policy(self):
        try:
            from yt_dlp import YoutubeDL
        except ImportError:
            self.skipTest('Optional yt-dlp is not installed')
        for url, data, code in [(CAPTION_URL, b'x'*(MAX_CAPTION_BYTES+1), 'invalid_captions'),
                                ('https://foreign.invalid/caption', PAYLOAD, 'unsupported')]:
            with self.subTest(url=url):
                response = io.BytesIO(data)
                response.url = url
                with patch.object(YoutubeDL, 'urlopen', autospec=True, return_value=response):
                    with self.assertRaises(CaptionError) as caught:
                        YtDlpCaptionAdapter().fetch(TRACK)
                self.assertEqual(caught.exception.issue.code, code)
                self.assertTrue(response.closed)


if __name__ == '__main__':
    unittest.main()
