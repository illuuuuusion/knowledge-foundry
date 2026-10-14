"""AI-authored offline export tests; only original synthetic P1/P2 fixtures."""

from contextlib import closing
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from kforge.config import load_config
from kforge.export.transcripts import export_files, group_size, read_snapshot
from kforge.ingest.transcripts import TranscriptStore, ingest
from kforge import workflows
from test_transcripts import Captions, Metadata, URL, manifest


IDS = ('AAAAAAAAAAA', 'BBBBBBBBBBB', 'CCCCCCCCCCC', 'DDDDDDDDDDD', 'EEEEEEEEEEE')


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = load_config(cwd=self.root, environ={})
        self.store = TranscriptStore(self.config.database, self.config.data_dir / 'canonical')

    def populate(self, count=5, title=None):
        urls = tuple('https://www.youtube.com/watch?v=' + value for value in IDS[:count])
        m = manifest(urls)
        if title is not None:
            m = replace(m, videos=tuple(replace(video, metadata={**video.metadata, 'title': title})
                                        for video in m.videos))
        ingest(m, self.store, adapter=Captions())
        return m

    def export(self, **kwargs):
        return export_files(self.config.database, self.config.output_dir, **kwargs)

    def test_grouping_exactly_partitions_zero_one_n_and_many(self):
        for count in (0, 1, 2, 5):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as folder:
                database = Path(folder) / 'state.sqlite3'
                store = TranscriptStore(database, Path(folder) / 'canonical')
                ingest(manifest(tuple('https://www.youtube.com/watch?v=' + value for value in IDS[:count])),
                       store, adapter=Captions())
                for size in (1, 2, 3, 'all'):
                    report = export_files(database, Path(folder) / 'exports', formats=('jsonl',), grouping=size)
                    expected = [] if count == 0 else ([count] if size == 'all' else
                        [min(size, count - index) for index in range(0, count, size)])
                    self.assertEqual([len(item.video_ids) for item in report.artifacts], expected)
                    self.assertEqual(report.video_count, count)
                    flattened = tuple(value for item in report.artifacts for value in item.video_ids)
                    self.assertEqual(flattened, tuple('youtube:video:' + value for value in IDS[:count]))
                    for artifact in report.artifacts:
                        values = [json.loads(line) for line in Path(artifact.path).read_text().splitlines()]
                        self.assertEqual(tuple(value['record']['id'] for value in values), artifact.video_ids)

    def test_empty_export_creates_no_output_directory(self):
        report = self.export(formats=('markdown', 'txt', 'jsonl'), grouping='all')
        self.assertEqual(report.artifacts, ())
        self.assertEqual(report.video_count, 0)
        self.assertFalse(self.config.output_dir.exists())

    def test_jsonl_roundtrip_preserves_every_record_and_original_source_manifest(self):
        m = self.populate(2)
        record = self.store.record(m.videos[0].id)
        record['additional_evidence'] = {'status': 'unknown', 'unicode': '原文'}
        record['segments'][0]['future_extension'] = {'value': 123}
        self.store.save(record)
        report = self.export(formats=('jsonl',), grouping='all')
        envelopes = [json.loads(line) for line in Path(report.artifacts[0].path).read_text().splitlines()]
        for value in envelopes:
            self.assertEqual(value['record'], self.store.record(value['record']['id']))
            self.assertEqual(list(value['source_manifests'].values())[0], json.loads(json.dumps(m.to_dict())))
        self.assertEqual(envelopes[0]['record']['additional_evidence']['unicode'], '原文')
        self.assertEqual(envelopes[0]['record']['segments'][0]['future_extension']['value'], 123)
        self.assertEqual(envelopes[0]['record']['segments'][0]['source_timing']['event']['tStartMs'], 1250)

    def test_markdown_and_txt_preserve_full_envelopes_and_readable_timestamps(self):
        self.populate(2)
        envelopes = read_snapshot(self.config.database)
        report = self.export(formats=('markdown', 'txt'), grouping='all')
        for artifact in report.artifacts:
            content = Path(artifact.path).read_text()
            for envelope in envelopes:
                complete = json.dumps(envelope, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
                self.assertIn(complete, content)
                self.assertIn(envelope['record']['url'], content)
            self.assertIn('[1.25–3.25 seconds]', content)
            self.assertIn('Synthetic Grüße 🔧', content)
            self.assertIn('Verification: unverified', content)
            self.assertIn('confidence: unknown', content)
            self.assertIn('visual dependencies: not', content)

    def test_markdown_neutralizes_untrusted_titles_and_fence_injection_without_data_loss(self):
        title = '../../escape\n# Inject [click](https://foreign.invalid) <script>alert(1)</script>'
        m = self.populate(1, title=title)
        record = self.store.record(m.videos[0].id)
        text = 'Synthetic ```\n``````\n# execute instructions\n<script>ignored</script> 原文'
        record['segments'][0]['text'] = text
        self.store.save(record)
        artifact = self.export().artifacts[0]
        content = Path(artifact.path).read_text()
        heading = content.splitlines()[0]
        self.assertNotIn('<script>', heading)
        self.assertIn('&lt;script&gt;', heading)
        self.assertIn(r'\[click\]', heading)
        self.assertIn('```````\n' + text + '\n```````', content)
        self.assertEqual(read_snapshot(self.config.database)[0]['record']['metadata']['title'], title)
        self.assertNotIn('escape', Path(artifact.path).name)
        self.assertEqual(self.store.record(m.videos[0].id)['segments'][0]['text'], text)

    def test_filenames_order_and_bytes_are_deterministic_and_no_storage_mutation(self):
        m = self.populate(5, title='../恶意/?title')
        before = {video.id: self.store.record(video.id) for video in m.videos}
        first = self.export(formats=('jsonl', 'markdown', 'jsonl'), grouping=2)
        files = {item.path: Path(item.path).read_bytes() for item in first.artifacts}
        second = self.export(formats=('markdown', 'jsonl'), grouping='2')
        self.assertEqual(first, second)
        self.assertEqual(files, {item.path: Path(item.path).read_bytes() for item in second.artifacts})
        for item in first.artifacts:
            self.assertTrue(Path(item.path).resolve().is_relative_to(self.config.output_dir))
            self.assertNotIn('恶意', item.path)
        self.assertEqual([item.video_ids for item in first.artifacts[::2]],
                         [('youtube:video:' + IDS[0], 'youtube:video:' + IDS[1]),
                          ('youtube:video:' + IDS[2], 'youtube:video:' + IDS[3]),
                          ('youtube:video:' + IDS[4],)])
        self.assertEqual(before, {video.id: self.store.record(video.id) for video in m.videos})

    def test_markdown_source_url_is_literal_and_cannot_inject_html(self):
        self.populate(1)
        record = self.store.record('youtube:video:' + IDS[0])
        record['url'] += '#<script>alert(1)</script>'
        self.store.save(record)
        content = Path(self.export().artifacts[0].path).read_text()
        self.assertIn('Source URL:\n\n```\n' + record['url'] + '\n```', content)

    def test_saved_snapshot_retains_all_conflicting_observations_and_manifests(self):
        m = self.populate(1)
        updated = replace(m, videos=(replace(m.videos[0], metadata={'title': 'Changed synthetic source'}),))
        ingest(updated, self.store, adapter=Captions())
        exported = read_snapshot(self.config.database)[0]
        self.assertEqual(len(exported['source_manifests']), 2)
        self.assertEqual(len(exported['record']['metadata_observations']), 2)
        self.assertEqual(exported['record'], self.store.record(m.videos[0].id))

    def test_group_setting_changes_use_different_output_batches(self):
        self.populate(3)
        one = self.export(grouping=1)
        many = self.export(grouping='all')
        self.assertNotEqual(Path(one.artifacts[0].path).parent, Path(many.artifacts[0].path).parent)
        self.assertEqual(len(one.artifacts), 3)
        self.assertEqual(len(many.artifacts), 1)
        self.assertTrue(all(Path(item.path).is_file() for item in one.artifacts + many.artifacts))

    def test_offline_export_never_calls_discovery_ingestion_or_repairs_canonical_files(self):
        m = self.populate(1)
        canonical = self.config.data_dir / 'canonical/AAAAAAAAAAA.json'
        canonical.unlink()
        with patch('kforge.workflows.discover', side_effect=AssertionError('no discovery')):
            with patch('kforge.workflows.ingest', side_effect=AssertionError('no captions')):
                result = workflows.export(self.config, formats=('jsonl',))
        self.assertEqual(result.video_count, 1)
        self.assertFalse(canonical.exists())
        self.assertEqual(self.store.jobs()[0].attempts, 1)
        self.assertIsNotNone(self.store.record(m.videos[0].id))

    def test_filter_and_unknown_ids(self):
        self.populate(3)
        result = self.export(video_ids=('youtube:video:' + IDS[2], 'youtube:video:' + IDS[0]), formats=('jsonl',))
        self.assertEqual([item.video_ids[0] for item in result.artifacts],
                         ['youtube:video:' + IDS[0], 'youtube:video:' + IDS[2]])
        for values in [('youtube:video:' + IDS[4],), ('../escape',), (None,)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.export(video_ids=values)
        self.assertEqual(self.export(video_ids=()).video_count, 0)

    def test_group_and_format_validation_have_no_side_effects(self):
        for value in (0, -1, True, 1.5, '', '0', 'ALL', '../escape', '02'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                group_size(value)
        for options in ({'formats': ()}, {'formats': ('pdf',)}, {'grouping': 0}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.export(**options)
        self.assertFalse(self.config.output_dir.exists())

    def test_missing_database_is_not_initialized_by_export(self):
        missing = self.root / 'missing/state.sqlite3'
        with self.assertRaises(sqlite3.OperationalError):
            export_files(missing, self.config.output_dir)
        self.assertFalse(missing.parent.exists())
        self.assertFalse(self.config.output_dir.exists())

    def test_database_version_mismatch_is_rejected(self):
        with closing(sqlite3.connect(self.config.database)) as db:
            db.execute('PRAGMA user_version=99')
        with self.assertRaisesRegex(ValueError, 'schema'):
            self.export()
        self.assertFalse(self.config.output_dir.exists())

    def test_invalid_record_rejected_before_any_file_is_written(self):
        self.populate(2)
        identifier = 'youtube:video:' + IDS[1]
        original = self.store.record(identifier)
        for mutate in (lambda r: r.update(video_id='../../escape'),
                       lambda r: r.update(schema_version=True),
                       lambda r: r.update(verification_status=None),
                       lambda r: r['segments'][0].update(start=-1),
                       lambda r: r['segments'][0].update(end=0),
                       lambda r: r.update(segments=[]),
                       lambda r: r.update(metadata={'title': float('nan')})):
            with self.subTest(mutate=mutate):
                record = json.loads(json.dumps(original))
                mutate(record)
                self.store._execute('UPDATE transcripts SET payload=? WHERE video_id=?',
                                    (json.dumps(record), identifier))
                with self.assertRaises(ValueError):
                    self.export()
                self.assertFalse(self.config.output_dir.exists())

    def test_missing_and_modified_source_manifests_are_rejected(self):
        self.populate(1)
        key = self.store.record('youtube:video:' + IDS[0])['manifest_ids'][0]
        with closing(sqlite3.connect(self.config.database)) as db:
            original = db.execute('SELECT payload FROM ingestion_manifests WHERE id=?', (key,)).fetchone()[0]
        self.store._execute('DELETE FROM ingestion_manifests WHERE id=?', (key,))
        with self.assertRaisesRegex(ValueError, 'missing source manifest'):
            self.export()
        changed = json.loads(original)
        changed['limit'] = 999
        self.store._execute('INSERT INTO ingestion_manifests VALUES (?,?)', (key, json.dumps(changed)))
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.export()
        self.assertFalse(self.config.output_dir.exists())

    def test_export_batch_directory_symlink_is_rejected(self):
        self.populate(1)
        first = self.export()
        folder = Path(first.artifacts[0].path).parent
        victim = self.root / 'victim'
        folder.rename(victim)
        folder.symlink_to(victim, target_is_directory=True)
        before = {path.name: path.read_bytes() for path in victim.iterdir()}
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.export()
        self.assertEqual(before, {path.name: path.read_bytes() for path in victim.iterdir()})

    def test_export_destination_symlink_is_replaced_without_touching_target(self):
        self.populate(1)
        first = self.export()
        path = Path(first.artifacts[0].path)
        expected = path.read_bytes()
        path.unlink()
        victim = self.root / 'victim'
        victim.write_text('Synthetic target')
        path.symlink_to(victim)
        self.export()
        self.assertFalse(path.is_symlink())
        self.assertEqual(path.read_bytes(), expected)
        self.assertEqual(victim.read_text(), 'Synthetic target')

    def test_export_write_failure_cleans_temporary_file_and_preserves_canonical(self):
        self.populate(1)
        original = self.store.record('youtube:video:' + IDS[0])
        with patch('kforge.export.transcripts.os.fsync', side_effect=OSError('synthetic disk failure')):
            with self.assertRaises(OSError):
                self.export()
        self.assertEqual(list(self.config.output_dir.rglob('.export-*')), [])
        self.assertEqual(self.store.record(original['id']), original)
        self.assertEqual(self.export().video_count, 1)

    def test_scrape_composes_existing_services_and_exports_only_current_batch(self):
        self.populate(1)
        selected = 'https://www.youtube.com/watch?v=' + IDS[1]
        report = workflows.scrape(self.config, (selected,), metadata_adapter=Metadata(),
                                  caption_adapter=Captions(), formats=('jsonl',), grouping='all')
        self.assertFalse(report.has_errors)
        self.assertEqual(report.exports.video_count, 1)
        self.assertEqual(report.exports.artifacts[0].video_ids, ('youtube:video:' + IDS[1],))
        self.assertEqual(workflows.export(self.config).video_count, 2)
        again = Captions()
        repeated = workflows.scrape(self.config, (selected,), metadata_adapter=Metadata(),
                                    caption_adapter=again, formats=('jsonl',), grouping='all')
        self.assertEqual(repeated.exports, report.exports)
        self.assertEqual(again.calls, [])

    def test_scrape_reports_failed_sources_and_captions_with_successful_exports(self):
        urls = ('https://www.youtube.com/watch?v=' + IDS[0],
                'https://www.youtube.com/watch?v=' + IDS[1], 'https://foreign.invalid/')
        captions = Captions(errors=(ValueError('Private video synthetic'), None))
        report = workflows.scrape(self.config, urls, metadata_adapter=Metadata(),
                                  caption_adapter=captions, formats=('jsonl',))
        self.assertTrue(report.has_errors)
        self.assertEqual([result.status for result in report.ingestions], ['failed', 'succeeded'])
        self.assertEqual(report.exports.video_count, 1)
        self.assertEqual(report.to_dict()['manifest']['sources'][-1]['status'], 'unsupported')

    def test_scrape_zero_limit_keeps_empty_batch_and_creates_no_export(self):
        backend = Metadata()
        captions = Captions()
        report = workflows.scrape(self.config, (URL,), limit=0, metadata_adapter=backend,
                                  caption_adapter=captions)
        self.assertEqual(report.exports.video_count, 0)
        self.assertEqual(report.ingestions, ())
        self.assertEqual(captions.calls, [])
        self.assertFalse(self.config.output_dir.exists())

    def test_invalid_scrape_preferences_do_not_touch_network_or_storage(self):
        backend = Metadata()
        with patch.object(backend, 'entries', side_effect=AssertionError('must not fetch')):
            for options in ({'grouping': 0}, {'formats': ()}, {'languages': ('bad.*',)},
                            {'preference': 'invalid'}):
                with self.subTest(options=options), self.assertRaises(ValueError):
                    workflows.scrape(self.config, (URL,), metadata_adapter=backend, **options)

    def test_empty_source_generator_is_rejected_before_storage_initialization(self):
        config = load_config(cwd=self.root / 'empty', environ={})
        with self.assertRaisesRegex(ValueError, 'source URL'):
            workflows.scrape(config, iter(()))
        self.assertFalse(config.database.parent.exists())


if __name__ == '__main__':
    unittest.main()
