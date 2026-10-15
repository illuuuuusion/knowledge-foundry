"""AI-authored offline P5 tests: synthetic transcripts, hand-written agent extraction
results and research bundles. No web access or model call; URLs are example.org."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kforge.builder.graph import ResearchBundle, check_graph, consolidate, merge_entities
from kforge.builder.jobs import Domain, create_jobs, import_results
from kforge.cli import main
from kforge.config import load_config
from kforge.export.transcripts import read_snapshot
from kforge.ingest.transcripts import TranscriptStore, ingest
from test_jobs import IDS, INJECTION, PAYLOAD, urls
from test_transcripts import Captions, manifest


DOMAIN = {'id': 'gpu-repair', 'title': 'Synthetic GPU repair', 'guidance': '',
          'entity_types': ['gpu_model', 'board', 'component'],
          'claim_kinds': ['observation', 'procedure_step'], 'max_input_chars': 70}
STATUSES = {'unverified', 'corroborated', 'contradicted', 'contested'}
TEXT = 'Synthetic page.\nThe rail   inductor fails when overheated.\nReplace pads after reflow.'


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.config = load_config(cwd=self.root, environ={})
        store = TranscriptStore(self.config.database, self.config.data_dir / 'canonical')
        ingest(manifest(urls(*IDS[:2])), store, adapter=Captions(payload=PAYLOAD))
        self.domain = Domain.model_validate(DOMAIN)
        self.jobs = create_jobs(self.config.database, self.config.output_dir, self.domain)
        self.research = self.config.source_dir / 'research' / 'gpu-repair'
        self.output = self.config.output_dir / 'graph' / 'gpu-repair'

    def submit(self, index, entities=(), claims=(('c1', 'Synthetic claim', ()),), line=0):
        status = self.jobs[index]
        segment = json.loads(Path(status.path, 'input.jsonl').read_text(encoding='utf-8').splitlines()[line])
        value = {'schema_version': 1, 'job_id': status.job_id,
                 'entities': [{'id': i, 'name': n, 'type': t, 'aliases': list(a)} for i, n, t, a in entities],
                 'claims': [{'id': c, 'statement': s, 'kind': 'observation', 'entity_ids': list(e),
                             'confidence': 'medium', 'verification_status': 'unverified',
                             'visual_dependency': 'none',
                             'citations': [{'source_id': segment['source_id'], 'start': segment['start'],
                                            'end': segment['end']}]} for c, s, e in claims]}
        Path(status.path, 'result.json').write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        report = import_results(self.config.database, self.config.output_dir, self.domain)
        self.assertNotIn('rejected', {item.status for item in report}, report)

    def claim(self, index, local='c1'):
        return f'claim:{self.jobs[index].job_id}:{local}'

    def document(self, identifier='d1', url='https://example.org/a', text=TEXT, **changes):
        file = self.research / 'texts' / f'{identifier}-{hashlib.sha256((url + text).encode()).hexdigest()[:8]}.md'
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding='utf-8')
        return {'id': identifier, 'url': url, 'title': 'Synthetic page',
                'retrieved_at': '2026-10-15T10:00:00Z', 'retrieval_method': 'synthetic fixture',
                'text_file': str(file.relative_to(self.research)), **changes}

    def bundle(self, name, documents=(), evidence=(), conflicts=(), raw=None):
        self.research.mkdir(parents=True, exist_ok=True)
        value = {'schema_version': 1, 'documents': list(documents), 'evidence': list(evidence),
                 'conflicts': list(conflicts)}
        (self.research / name).write_bytes(raw if raw is not None else json.dumps(value).encode())

    def evidence(self, claim, stance='supports', quote='The rail inductor fails', document='d1', **changes):
        return {'claim_id': claim, 'document_id': document, 'stance': stance, 'quote': quote, **changes}

    def run_consolidate(self, domain=None):
        return consolidate(self.config.database, self.config.source_dir, self.config.output_dir,
                           domain or self.domain)

    def read(self, name):
        return [json.loads(line) for line in (self.output / name).read_text(encoding='utf-8').splitlines()]

    def claims(self):
        return {claim['id']: claim for claim in self.read('claims.jsonl')}

    def test_alias_merge_never_bridges_models_revisions_units_or_types(self):
        def labels(*entities):
            mapping, nodes = merge_entities((f'job{index}', {'id': 'e', 'aliases': [], **entity})
                                            for index, entity in enumerate(entities))
            self.assertEqual(len(mapping), len(entities))
            return sorted(sorted([node['label'], *node['aliases']]) for node in nodes)
        gpu = lambda name, *aliases: {'name': name, 'type': 'gpu_model', 'aliases': list(aliases)}
        board = lambda name, *aliases: {'name': name, 'type': 'board', 'aliases': list(aliases)}
        unit = lambda name: {'name': name, 'type': 'measurement'}
        self.assertEqual(labels(gpu('3080', 'RTX 3080'), gpu('3080', 'RTX 3080 Ti'), gpu('RTX 3080'),
                                gpu('RTX 3080 Ti')),
                         [['3080', 'RTX 3080', 'RTX 3080 Ti'], ['RTX 3080'], ['RTX 3080 Ti']])
        self.assertEqual(labels(gpu('RTX 3080', '3080'), gpu('3080', 'RTX 3080 Ti'), gpu('RTX 3080 Ti')),
                         [['3080', 'RTX 3080'], ['3080', 'RTX 3080 Ti'], ['RTX 3080 Ti']])
        # Equal short names merge even if aliases disagree, but never pull in either model.
        self.assertEqual(labels(gpu('RTX 3080'), gpu('3080', 'RTX 3080'), gpu('3080', 'RTX 3080 Ti')),
                         [['3080', 'RTX 3080', 'RTX 3080 Ti'], ['RTX 3080']])
        self.assertEqual(labels(gpu('RTX 3080', 'RTX3080', 'GeForce RTX 3080'), gpu('RTX3080'),
                                gpu('GeForce RTX 3080', 'RTX 3080')),
                         [['GeForce RTX 3080', 'RTX 3080', 'RTX3080']])
        self.assertEqual(len(labels(board('PG132', 'PG132 rev 1.0'), board('PG132', 'PG132 rev 1.1'),
                                    board('PG132 rev 1.0'), board('PG132 rev 1.1'))), 3)
        self.assertEqual(labels(unit('10 mΩ'), unit('10 MΩ'), unit('100 mV'), unit('100 MV'), unit('10 m\u2126')),
                         [['10 MΩ'], ['10 mΩ', '10 m\u2126'], ['100 MV'], ['100 mV']])
        self.assertEqual(labels(gpu('RTX 3080'), gpu('RTX  3080'), gpu('rtx 3080'), board('RTX 3080')),
                         [['RTX  3080', 'RTX 3080'], ['RTX 3080'], ['rtx 3080']])
        self.assertEqual(labels(gpu('GeForce RTX 3090', 'RTX 3090', 'RTX3090'), gpu('RTX 3090', 'RTX3090'),
                                gpu('RTX3090'), board('PG132', 'PG132-A'), board('PG132-A')),
                         [['GeForce RTX 3090', 'RTX 3090', 'RTX3090'], ['PG132', 'PG132-A']])

    def test_merged_entities_map_back_to_claims(self):
        self.submit(0, [('a', 'RTX 3080', 'gpu_model', ['RTX3080']), ('b', 'RTX 3080 Ti', 'gpu_model', [])],
                    [('c1', 'Synthetic claim', ('a', 'b'))])
        self.submit(3, [('a', 'RTX3080', 'gpu_model', []), ('b', 'RTX  3080', 'gpu_model', [])],
                    [('c1', 'Synthetic claim', ('a', 'b'))])
        report = self.run_consolidate()
        entities = {node['label']: node for node in self.read('nodes.jsonl') if node['type'] == 'entity'}
        self.assertEqual((report['entities'], sorted(entities)), (2, ['RTX 3080', 'RTX 3080 Ti']))
        self.assertEqual(entities['RTX 3080']['aliases'], ['RTX  3080', 'RTX3080'])
        claims = self.claims()
        self.assertEqual(claims[self.claim(3)]['entities'], [entities['RTX 3080']['id']])
        self.assertEqual(sorted(claims[self.claim(0)]['entities']),
                         sorted(node['id'] for node in entities.values()))

    def test_reused_short_name_never_links_claims_about_different_models(self):
        self.submit(0, [('a', 'RTX 3080', 'gpu_model', [])], [('c1', 'Non-Ti claim', ('a',))])
        self.submit(1, [('a', '3080', 'gpu_model', ['RTX 3080'])], [('c1', 'Short-name claim', ('a',))])
        self.submit(4, [('a', '3080', 'gpu_model', ['RTX 3080 Ti'])], [('c1', 'Ti claim', ('a',))])
        self.run_consolidate()
        claims = self.claims()
        self.assertNotEqual(claims[self.claim(4)]['entities'], claims[self.claim(0)]['entities'])
        self.assertEqual(claims[self.claim(4)]['entities'], claims[self.claim(1)]['entities'])

    def test_every_claim_traces_to_video_timestamps_and_graph_has_no_dangling_edges(self):
        self.submit(0, [('e', 'Inductor', 'component', [])], [('c1', 'One', ('e',)), ('c2', 'Two', ('e',))])
        self.submit(4, line=0)
        self.run_consolidate()
        segments = {envelope['record']['id']: (envelope['record']['url'], envelope['record']['segments'])
                    for envelope in read_snapshot(self.config.database)}
        claims = self.claims()
        self.assertEqual(len(claims), 3)
        for claim in claims.values():
            self.assertEqual(claim['verification_status'], 'unverified')
            self.assertTrue(claim['citations'])
            for citation in claim['citations']:
                url, video = segments[citation['source_id']]
                self.assertEqual(citation['url'], url)
                self.assertTrue(any(s['start'] <= citation['start'] and citation['end'] <= s['end'] for s in video))
        nodes, edges = self.read('nodes.jsonl'), self.read('edges.jsonl')
        identifiers = {node['id'] for node in nodes}
        self.assertEqual(len(identifiers), len(nodes))
        self.assertTrue(all(edge['source'] in identifiers and edge['target'] in identifiers for edge in edges))
        cited = {(edge['source'], edge['target'], edge['start'], edge['end']) for edge in edges
                 if edge['type'] == 'cited_in'}
        self.assertEqual(cited, {(c['id'], x['source_id'], x['start'], x['end'])
                                 for c in claims.values() for x in c['citations']})
        self.assertEqual({node['id'] for node in nodes if node['type'] == 'video'},
                         {'youtube:video:' + value for value in IDS[:2]})
        with self.assertRaisesRegex(ValueError, 'missing node'):
            check_graph(nodes, edges + [{'source': self.claim(0), 'target': 'entity:missing', 'type': 'mentions'}])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            check_graph(nodes + nodes[:1], edges)

    def test_evidence_and_conflicts_are_retained_and_nothing_becomes_verified(self):
        self.submit(0, claims=[(name, 'Synthetic ' + name, ()) for name in ('c1', 'c2', 'c3', 'c4')])
        self.submit(3)
        self.bundle('a.json', [self.document('d1'), self.document('d2', 'https://example.org/b')], [
            self.evidence(self.claim(0, 'c1')), self.evidence(self.claim(0, 'c2')),
            self.evidence(self.claim(0, 'c3'), 'contradicts', 'Replace pads', 'd2')])
        self.bundle('b.json', [self.document('x', 'https://example.org/c', 'Inductors never fail.')],
                    [self.evidence(self.claim(0, 'c1'), 'contradicts', 'Inductors never fail.', 'x')],
                    [{'claim_ids': [self.claim(3), self.claim(0, 'c4')], 'note': 'Opposite advice'}])
        report = self.run_consolidate()
        self.assertEqual([bundle['status'] for bundle in report['bundles']], ['accepted', 'accepted'])
        claims = self.claims()
        self.assertEqual({key: claim['verification_status'] for key, claim in claims.items()}, {
            self.claim(0, 'c1'): 'contested', self.claim(0, 'c2'): 'corroborated',
            self.claim(0, 'c3'): 'contradicted', self.claim(0, 'c4'): 'contested',
            self.claim(3): 'contested'})
        self.assertEqual(report['statuses'], {'contested': 3, 'contradicted': 1, 'corroborated': 1})
        self.assertEqual(claims[self.claim(0, 'c4')]['conflicts'], [self.claim(3)])
        self.assertEqual(claims[self.claim(3)]['conflicts'], [self.claim(0, 'c4')])
        evidence = self.read('evidence.jsonl')
        self.assertEqual(sorted((item['claim_id'][-2:], item['stance']) for item in evidence),
                         [('c1', 'contradicts'), ('c1', 'supports'), ('c2', 'supports'), ('c3', 'contradicts')])
        for item in evidence:
            self.assertEqual(item['document']['id'], item['document_id'])
            self.assertTrue(item['document']['url'].startswith('https://example.org/'))
            self.assertEqual(item['document']['retrievals'][0]['retrieved_at'], '2026-10-15T10:00:00Z')
            self.assertIn(item['id'], claims[item['claim_id']]['evidence'])
        edges = self.read('edges.jsonl')
        self.assertEqual([(edge['notes'], edge['bundles']) for edge in edges if edge['type'] == 'conflicts_with'],
                         [(['Opposite advice'], ['b.json'])])
        self.assertEqual(sorted(edge['type'] for edge in edges if edge['type'] in ('supports', 'contradicts')),
                         ['contradicts', 'contradicts', 'supports', 'supports'])
        for path in self.output.iterdir():
            self.assertNotIn('"verified"', path.read_text(encoding='utf-8'), path.name)
        self.assertTrue({node.get('verification_status') for node in self.read('nodes.jsonl')
                         if node['type'] == 'claim'} <= STATUSES)

    def test_duplicate_documents_and_evidence_merge_but_keep_every_retrieval(self):
        self.submit(0)
        same = self.evidence(self.claim(0))
        self.bundle('a.json', [self.document()], [same])
        self.bundle('b.json', [self.document(retrieved_at='2026-10-16T08:00:00+02:00', title='Other title')],
                    [{**same, 'quote': 'The  rail\ninductor fails'}])
        self.bundle('c.json', [self.document(text=TEXT + ' Updated.')], [same])
        report = self.run_consolidate()
        self.assertEqual((report['documents'], report['evidence']), (2, 2))
        evidence = self.read('evidence.jsonl')
        merged = next(item for item in evidence if item['bundles'] == ['a.json', 'b.json'])
        self.assertEqual([r['retrieved_at'] for r in merged['document']['retrievals']],
                         ['2026-10-15T10:00:00Z', '2026-10-16T08:00:00+02:00'])
        self.assertEqual([r['title'] for r in merged['document']['retrievals']], ['Synthetic page', 'Other title'])
        self.assertEqual(len({item['document']['content_sha256'] for item in evidence}), 2)
        self.assertEqual(self.claims()[self.claim(0)]['verification_status'], 'corroborated')

    def test_invalid_bundles_and_missing_evidence_are_rejected_without_effect(self):
        self.submit(0, claims=[('c1', 'One', ()), ('c2', 'Two', ())])
        self.bundle('a-valid.json', [self.document()], [self.evidence(self.claim(0))])
        outside = self.root / 'outside.md'
        outside.write_text(TEXT, encoding='utf-8')
        (self.research / 'texts').mkdir(parents=True, exist_ok=True)
        (self.research / 'texts' / 'link.md').symlink_to(outside)
        (self.research / 'texts' / 'latin1.md').write_bytes('Grüße'.encode('latin-1'))
        claim = self.claim(0, 'c2')
        evidence = self.evidence(claim)
        doc = self.document()
        cases = {
            'malformed JSON': {'raw': b'{"schema_version": 1, '},
            'unknown claim': {'evidence': [self.evidence(self.claim(1))]},
            'malformed claim ID': {'evidence': [self.evidence('c2')]},
            'unknown document': {'evidence': [{**evidence, 'document_id': 'd9'}]},
            'duplicate document IDs': {'documents': [doc, doc]},
            'quote not in document': {'evidence': [{**evidence, 'quote': 'Invented quote'}]},
            'missing quote': {'evidence': [{k: v for k, v in evidence.items() if k != 'quote'}]},
            'blank quote': {'evidence': [{**evidence, 'quote': '  '}]},
            'too short quote': {'evidence': [{**evidence, 'quote': ' fails '}]},
            'unreferenced document': {'documents': [doc, {**doc, 'id': 'd2'}]},
            'bundle as text file': {'documents': [{**doc, 'text_file': 'a-valid.json'}]},
            'bundle as text file, upper case': {'documents': [{**doc, 'text_file': 'A-VALID.JSON'}]},
            'NUL in text path': {'documents': [{**doc, 'text_file': 'texts/a\x00b.md'}]},
            'missing URL': {'documents': [{k: v for k, v in doc.items() if k != 'url'}]},
            'non-HTTP URL': {'documents': [{**doc, 'url': 'javascript:alert(1)'}]},
            'URL with credentials': {'documents': [{**doc, 'url': 'https://user:secret@example.org/a'}]},
            'naive retrieval time': {'documents': [{**doc, 'retrieved_at': '2026-10-15T10:00:00'}]},
            'missing retrieval method': {'documents': [{k: v for k, v in doc.items() if k != 'retrieval_method'}]},
            'path traversal': {'documents': [{**doc, 'text_file': '../../../outside.md'}]},
            'absolute path': {'documents': [{**doc, 'text_file': str(outside)}]},
            'missing text file': {'documents': [{**doc, 'text_file': 'texts/none.md'}]},
            'symlinked text file': {'documents': [{**doc, 'text_file': 'texts/link.md'}]},
            'non-UTF-8 text': {'documents': [{**doc, 'text_file': 'texts/latin1.md'}]},
            'evidence sets verified': {'evidence': [{**evidence, 'verification_status': 'verified'}]},
            'bundle adds claims': {'raw': json.dumps({'schema_version': 1, 'claims': [{'id': 'x'}]}).encode()},
            'invalid stance': {'evidence': [{**evidence, 'stance': 'verifies'}]},
            'self conflict': {'conflicts': [{'claim_ids': [claim, claim], 'note': 'n'}]},
            'unknown conflict claim': {'conflicts': [{'claim_ids': [claim, self.claim(1)], 'note': 'n'}]},
            'three-way conflict': {'conflicts': [{'claim_ids': [claim, self.claim(0), claim], 'note': 'n'}]},
        }
        for name, case in cases.items():
            with self.subTest(name):
                arguments = {'documents': [doc], 'evidence': [evidence], **case}
                self.bundle('b-invalid.json', **arguments)
                report = self.run_consolidate()
                self.assertEqual([(b['file'], b['status']) for b in report['bundles']],
                                 [('a-valid.json', 'accepted'), ('b-invalid.json', 'rejected')])
                self.assertTrue(report['bundles'][1]['errors'])
                self.assertEqual({k: c['verification_status'] for k, c in self.claims().items()},
                                 {self.claim(0): 'corroborated', claim: 'unverified'})
                self.assertEqual((report['evidence'], report['conflicts']), (1, 0))
        (self.research / 'b-invalid.json').unlink()
        (self.research / 'c-link.json').symlink_to(self.research / 'a-valid.json')
        self.assertEqual(self.run_consolidate()['bundles'][1],
                         {'file': 'c-link.json', 'status': 'rejected', 'errors': ['bundle: must be a regular file']})

    def test_rebuild_is_deterministic_stale_results_are_excluded_and_text_stays_data(self):
        self.submit(1, claims=[('c1', INJECTION, ())])
        empty = self.run_consolidate()
        self.assertEqual((empty['evidence'], empty['bundles']), (0, []))
        self.bundle('a.json', [self.document(text=TEXT + ' ' + INJECTION)],
                    [self.evidence(self.claim(1), quote=INJECTION)])
        self.run_consolidate()
        files = {path.name: path.read_bytes() for path in self.output.iterdir()}
        self.assertEqual(sorted(files), ['RESEARCH.md', 'claims.jsonl', 'edges.jsonl', 'evidence.jsonl',
                                         'nodes.jsonl', 'research.schema.json'])
        self.run_consolidate()
        self.assertEqual({path.name: path.read_bytes() for path in self.output.iterdir()}, files)
        self.assertEqual(json.loads(files['research.schema.json']), ResearchBundle.model_json_schema())
        research = files['RESEARCH.md'].decode()
        self.assertNotIn(INJECTION, research)
        self.assertIn('untrusted', research)
        self.assertIn(str(self.research), research)
        self.assertEqual(self.claims()[self.claim(1)]['statement'], INJECTION)
        self.assertEqual(list(self.root.rglob('escape.txt')), [])
        changed = Domain.model_validate({**DOMAIN, 'max_input_chars': 1000})
        report = consolidate(self.config.database, self.config.source_dir, self.root / 'other', changed)
        self.assertEqual((report['claims'], report['bundles'][0]['status']), (0, 'rejected'))
        self.assertIn('evidence.0.claim_id: unknown or stale claim', report['bundles'][0]['errors'])
        target = self.root / 'elsewhere'
        target.mkdir()
        link = self.root / 'linked' / 'graph' / 'gpu-repair'
        link.parent.mkdir(parents=True)
        link.symlink_to(target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            consolidate(self.config.database, self.config.source_dir, self.root / 'linked', self.domain)


class ConsolidateCliTests(unittest.TestCase):
    def test_cli_reports_and_fails_on_rejected_bundles(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            environment = {'KFORGE_DATA_DIR': str(root / 'data'), 'KFORGE_SOURCE_DIR': str(root / 'sources'),
                           'KFORGE_OUTPUT_DIR': str(root / 'output')}
            with patch.dict(os.environ, environment, clear=True):
                config = load_config()
                ingest(manifest(), TranscriptStore(config.database, config.data_dir / 'canonical'),
                       adapter=Captions())
                domain = root / 'domain.yaml'
                domain.write_text(json.dumps(DOMAIN), encoding='utf-8')
                for expected, bundle in ((0, None), (1, b'[]')):
                    if bundle is not None:
                        research = root / 'sources' / 'research' / 'gpu-repair'
                        research.mkdir(parents=True)
                        (research / 'bad.json').write_bytes(bundle)
                    with redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()) as errors:
                        result = main(['consolidate', str(domain)])
                    self.assertEqual(result, expected, errors.getvalue())
                    report = json.loads(output.getvalue())
                    self.assertEqual((report['claims'], report['nodes'], report['edges']), (0, 0, 0))
                self.assertEqual(report['bundles'][0]['status'], 'rejected')
                self.assertTrue((root / 'output' / 'graph' / 'gpu-repair' / 'RESEARCH.md').is_file())


if __name__ == '__main__':
    unittest.main()
