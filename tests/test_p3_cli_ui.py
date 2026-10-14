"""AI-authored CLI and native Streamlit contracts, with synthetic offline services."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from kforge.cli import main
from kforge.config import load_config
from kforge.export.transcripts import ExportReport
from kforge.ingest.discovery import Manifest
from kforge.ingest.transcripts import TranscriptStore, ingest
from kforge import ui, workflows
from test_discovery import FixtureAdapter, PLAYLIST, VIDEO, A, B, C, entry
from test_transcripts import Captions, manifest


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.environment = patch.dict(os.environ, {'KFORGE_DATA_DIR': str(self.root / 'data'),
                'KFORGE_OUTPUT_DIR': str(self.root / 'output')}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.config = load_config()

    def call(self, args):
        with redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()) as errors:
            result = main(args)
        return result, output.getvalue(), errors.getvalue()

    def test_scrape_cli_full_offline_pipeline_limit_languages_groups_and_reexport(self):
        metadata = FixtureAdapter({PLAYLIST: [entry(B), entry(A), entry(C)]})
        captions = Captions()
        with patch('kforge.ingest.discovery.YtDlpAdapter', return_value=metadata):
            with patch('kforge.ingest.transcripts.YtDlpCaptionAdapter', return_value=captions):
                result, output, error = self.call(['scrape', PLAYLIST, '--limit', '2',
                    '--language', 'de', '--language', 'en', '--preference', 'auto',
                    '--group-size', '2', '--format', 'jsonl', '--format', 'txt'])
        self.assertEqual(result, 0, error)
        report = json.loads(output)
        self.assertEqual([video['video_id'] for video in report['manifest']['videos']], [B, A])
        self.assertEqual(report['manifest']['sources'][0]['status'], 'truncated')
        self.assertEqual(report['exports']['video_count'], 2)
        self.assertEqual(len(report['exports']['artifacts']), 2)
        store = TranscriptStore(self.config.database, self.config.data_dir / 'canonical')
        record = store.record('youtube:video:' + A)
        self.assertEqual(record['transcript']['selection'], {'languages': ['de', 'en'], 'preference': 'auto'})
        with patch('kforge.workflows.scrape', side_effect=AssertionError('must be offline')):
            with patch('kforge.workflows.discover', side_effect=AssertionError('must be offline')):
                result, output, error = self.call(['export', '--group-size', 'all', '--format', 'markdown'])
        self.assertEqual(result, 0, error)
        self.assertEqual(json.loads(output)['video_count'], 2)
        self.assertEqual(len(captions.calls), 4)

    def test_scrape_url_file_and_shared_workflow_arguments(self):
        file = self.root / 'urls.txt'
        file.write_text('# Synthetic list\n' + PLAYLIST + '\n')
        report = workflows.ScrapeReport(Manifest((), (), None, 'source'), (), ExportReport(0, 1, ()))
        with patch('kforge.workflows.scrape', return_value=report) as scrape:
            result, _, error = self.call(['scrape', VIDEO, '--url-file', str(file), '--retry-failed'])
        self.assertEqual(result, 0, error)
        self.assertEqual(scrape.call_args.args[1], [VIDEO, PLAYLIST])
        self.assertEqual(scrape.call_args.kwargs['languages'], ('en',))
        self.assertTrue(scrape.call_args.kwargs['retry_failed'])

    def test_failed_source_and_unavailable_captions_return_nonzero_with_structured_status(self):
        metadata = FixtureAdapter({VIDEO: [entry(A)]})
        with patch('kforge.ingest.discovery.YtDlpAdapter', return_value=metadata):
            with patch('kforge.ingest.transcripts.YtDlpCaptionAdapter', return_value=Captions(tracks=())):
                result, output, _ = self.call(['scrape', VIDEO, 'https://foreign.invalid/'])
        self.assertEqual(result, 1)
        report = json.loads(output)
        self.assertEqual(report['ingestions'][0]['issue']['code'], 'captions_unavailable')
        self.assertTrue(report['has_errors'])
        self.assertEqual(report['exports']['artifacts'], [])

    def test_invalid_commands_return_errors_without_tracebacks_or_writes(self):
        for args in (['scrape'], ['scrape', VIDEO, '--language', 'bad.*'],
                     ['scrape', VIDEO, '--limit', '-1'], ['export'], ['ui', '--port', '0']):
            with self.subTest(args=args):
                result, _, errors = self.call(args)
                self.assertEqual(result, 1)
                self.assertNotIn('Traceback', errors)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_bad_group_size_is_an_argparse_usage_error(self):
        for value in ('0', '-1', 'x', '../escape'):
            with self.subTest(value=value), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
                main(['export', '--group-size', value])
            self.assertEqual(raised.exception.code, 2)

    def test_export_specific_id_calls_shared_service(self):
        store = TranscriptStore(self.config.database, self.config.data_dir / 'canonical')
        ingest(manifest((VIDEO, 'https://www.youtube.com/watch?v=' + B)), store, adapter=Captions())
        with patch('kforge.workflows.export', wraps=workflows.export) as export:
            result, output, error = self.call(['export', '--video-id', 'youtube:video:' + B, '--format', 'jsonl'])
        self.assertEqual(result, 0, error)
        self.assertEqual(json.loads(output)['video_count'], 1)
        self.assertEqual(export.call_args.kwargs['video_ids'], ['youtube:video:' + B])

    def test_worker_lock_error_is_reported_without_traceback(self):
        with patch('kforge.workflows.scrape', side_effect=RuntimeError('Another ingestion worker owns this database')):
            result, _, error = self.call(['scrape', VIDEO])
        self.assertEqual(result, 1)
        self.assertIn('Another ingestion worker', error)
        self.assertNotIn('Traceback', error)

    def test_missing_ui_dependency_is_actionable(self):
        with patch('kforge.cli.importlib.util.find_spec', return_value=None):
            result, _, error = self.call(['ui'])
        self.assertEqual(result, 1)
        self.assertIn('Install the ui extra', error)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_ui_launch_forwards_config_and_uses_local_host(self):
        file = self.root / 'config.toml'
        file.write_text('[logging]\nlevel="WARNING"\n')
        with patch('kforge.cli.importlib.util.find_spec', return_value=object()):
            with patch('kforge.cli.subprocess.run', return_value=Mock(returncode=0)) as run:
                result, _, error = self.call(['--config', str(file), 'ui', '--port', '9876'])
        self.assertEqual(result, 0, error)
        args = run.call_args.args[0]
        self.assertEqual(args[:4], [sys.executable, '-m', 'streamlit', 'run'])
        self.assertTrue(args[4].endswith('ui.py'))
        self.assertIn('--server.address=127.0.0.1', args)
        self.assertIn('--server.port=9876', args)
        self.assertEqual(run.call_args.kwargs['env']['KFORGE_CONFIG'], str(file))

    def test_installed_cli_help_for_all_new_commands_creates_no_storage(self):
        for command in ('scrape', 'export', 'ui'):
            with self.subTest(command=command):
                result = subprocess.run([str(Path(sys.executable).parent / 'kforge'), command, '--help'],
                                        cwd=self.root, capture_output=True, text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(command, result.stdout)
        self.assertEqual(list(self.root.iterdir()), [])


@unittest.skipUnless(importlib.util.find_spec('streamlit'), 'Optional Streamlit is not installed')
class StreamlitTests(unittest.TestCase):
    def setUp(self):
        from streamlit.testing.v1 import AppTest
        self.AppTest = AppTest
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        env = patch.dict(os.environ, {'KFORGE_DATA_DIR': str(self.root / 'data'),
                'KFORGE_OUTPUT_DIR': str(self.root / 'output')}, clear=True)
        env.start()
        self.addCleanup(env.stop)
        self.config = load_config()
        self.app = AppTest.from_file(Path(ui.__file__), default_timeout=10)

    def test_initial_native_ui_has_required_controls_and_no_side_effects(self):
        with patch('kforge.workflows.scrape', side_effect=AssertionError('no auto scrape')):
            self.app.run()
            self.assertEqual(len(self.app.exception), 0)
            self.assertEqual(self.app.text_area(key='sources').label, 'Sources')
            self.assertEqual(self.app.number_input(key='limit').value, 10)
            self.assertEqual(self.app.text_input(key='languages').value, 'en')
            self.assertEqual(self.app.selectbox(key='preference').value, 'manual')
            self.assertEqual(self.app.text_input(key='scrape_group').value, '1')
            self.app.text_input(key='languages').set_value('de,en').run()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_native_ui_submits_to_same_workflow_with_all_choices_and_persists_status(self):
        report = workflows.ScrapeReport(Manifest((), (), 2, 'source'), (), ExportReport(0, 'all', ()))
        self.app.run()
        self.app.text_area(key='sources').set_value(VIDEO + '\n' + PLAYLIST)
        self.app.number_input(key='limit').set_value(2)
        self.app.text_input(key='languages').set_value('de, en')
        self.app.selectbox(key='preference').select('auto')
        self.app.text_input(key='scrape_group').set_value('all')
        self.app.multiselect(key='scrape_formats').set_value(['txt', 'jsonl'])
        self.app.checkbox(key='retry_failed').check()
        with patch('kforge.workflows.scrape', return_value=report) as scrape:
            self.app.button[0].click().run()
            self.assertEqual(len(self.app.exception), 0)
            self.assertEqual(scrape.call_args.args[1], [VIDEO, PLAYLIST])
            self.assertEqual(scrape.call_args.kwargs, {'limit': 2, 'languages': ('de', 'en'),
                'preference': 'auto', 'grouping': 'all', 'formats': ['txt', 'jsonl'], 'retry_failed': True})
            self.app.run()
            self.assertEqual(scrape.call_count, 1)
        self.assertEqual(self.app.session_state['last_scrape']['exports']['group_size'], 'all')
        self.assertEqual(len(self.app.success), 1)
        self.assertEqual(len(self.app.info), 1)

    def test_native_ui_real_workflow_with_mock_adapters_and_offline_reexport(self):
        metadata = FixtureAdapter({VIDEO: [entry(A)]})
        captions = Captions()
        self.app.run()
        self.app.text_area(key='sources').set_value(VIDEO)
        with patch('kforge.ingest.discovery.YtDlpAdapter', return_value=metadata):
            with patch('kforge.ingest.transcripts.YtDlpCaptionAdapter', return_value=captions):
                self.app.button[0].click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(self.app.session_state['last_export']['video_count'], 1)
        first = self.app.session_state['last_export']['artifacts'][0]['path']
        self.assertTrue(Path(first).is_file())
        self.app.text_input(key='offline_group').set_value('all')
        self.app.multiselect(key='offline_formats').set_value(['jsonl'])
        with patch('kforge.workflows.scrape', side_effect=AssertionError('offline only')):
            with patch('kforge.workflows.export', wraps=workflows.export) as export:
                self.app.button[1].click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(export.call_count, 1)
        self.assertEqual(self.app.session_state['last_export']['artifacts'][0]['format'], 'jsonl')
        self.assertEqual(len(captions.calls), 2)

    def test_native_ui_error_clears_old_success_and_is_not_a_traceback(self):
        good = workflows.ScrapeReport(Manifest((), (), None, 'source'), (), ExportReport(0, 1, ()))
        self.app.run()
        self.app.text_area(key='sources').set_value(VIDEO)
        with patch('kforge.workflows.scrape', return_value=good):
            self.app.button[0].click().run()
        with patch('kforge.workflows.scrape', side_effect=ValueError('Synthetic validation error')):
            self.app.button[0].click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(len(self.app.success), 0)
        self.assertEqual(self.app.error[0].value, 'Synthetic validation error')

    def test_native_ui_partial_failure_shows_source_and_video_status(self):
        report = workflows.scrape(self.config, (VIDEO, 'https://foreign.invalid/'),
                                 metadata_adapter=FixtureAdapter({VIDEO: [entry(A)]}),
                                 caption_adapter=Captions(tracks=()))
        self.app.run()
        self.app.text_area(key='sources').set_value(VIDEO)
        with patch('kforge.workflows.scrape', return_value=report):
            self.app.button[0].click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(len(self.app.warning), 1)
        sources = self.app.dataframe[0].value
        jobs = self.app.dataframe[1].value
        self.assertEqual(sources['status'].tolist(), ['ok', 'unsupported'])
        self.assertEqual(jobs['issue'].tolist(), ['captions_unavailable'])

    def test_native_offline_missing_storage_reports_error_and_creates_nothing(self):
        self.app.run()
        self.app.button[1].click().run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertEqual(len(self.app.error), 1)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_native_ui_invalid_configuration_is_visible(self):
        with patch.dict(os.environ, {'KFORGE_LOG_LEVEL': 'invalid'}):
            self.app.run()
        self.assertEqual(len(self.app.exception), 0)
        self.assertIn('Invalid log level', self.app.error[0].value)
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
