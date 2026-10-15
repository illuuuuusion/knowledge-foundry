"""Local discovery, ingestion, offline export and optional Streamlit CLI."""

import argparse
from dataclasses import asdict
import json
import importlib.util
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

from . import __version__
from .config import ConfigError, load_config
from .logging import configure_logging
from .ingest.discovery import discover
from .ingest.urls import parse_url_list
from .storage import migrate
from . import workflows
from .export.transcripts import group_size
from .builder import graph, jobs
from .knowledge import library


def _group_size(value: str) -> int | str:
    try:
        return group_size(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _budget(value: str) -> tuple[str, int]:
    preset, _, tokens = value.partition('=')
    if preset not in library.BUDGETS or not re.fullmatch(r'[0-9]+', tokens) or int(tokens) < 1:
        raise argparse.ArgumentTypeError('expected essentials|topic|full=<positive tokens>')
    return preset, int(tokens)


def _export_options(parser):
    parser.add_argument('--group-size', type=_group_size, default=1, metavar='1|N|all')
    parser.add_argument('--format', dest='formats', action='append',
                        choices=('markdown', 'txt', 'jsonl'), help='Repeat to select multiple formats')


def _source_options(parser):
    parser.add_argument('urls', nargs='*', help='Video, playlist or channel URLs')
    parser.add_argument('--url-file', type=Path, help='UTF-8 file with one URL per line')
    parser.add_argument('--limit', type=int, help='Maximum unique videos across sources')
    parser.add_argument('--order', choices=('source', 'id'), default='source')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kforge", description="Knowledge Foundry")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", type=Path, help="TOML configuration file")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("config", help="Show resolved paths and logging level")
    commands.add_parser("init", help="Create local directories and migrate SQLite")
    discovery = commands.add_parser("discover", help="Discover YouTube video metadata as JSON")
    _source_options(discovery)
    scrape = commands.add_parser('scrape', help='Discover, ingest captions and export the selected batch')
    _source_options(scrape)
    _export_options(scrape)
    scrape.add_argument('--language', dest='languages', action='append',
                        help='Preferred language code; repeat in priority order (default: en)')
    scrape.add_argument('--preference', choices=('manual', 'auto'), default='manual')
    scrape.add_argument('--retry-failed', action='store_true', help='Reattempt permanent caption failures')
    export = commands.add_parser('export', help='Export stored transcripts offline')
    _export_options(export)
    export.add_argument('--video-id', dest='video_ids', action='append',
                        help='Stable youtube:video:<id>; repeat to select videos (default: all stored)')
    job = commands.add_parser('jobs', help='File-based agent extraction jobs')
    job_commands = job.add_subparsers(dest='job_command', required=True)
    create = job_commands.add_parser('create', help='Write TASK.md/input.jsonl/schema.json job folders offline')
    importer = job_commands.add_parser('import', help='Validate and import agent result.json files')
    for sub in (create, importer):
        sub.add_argument('domain', type=Path, help='Domain YAML configuration')
    create.add_argument('--video-id', dest='video_ids', action='append',
                        help='Stable youtube:video:<id>; repeat to select videos (default: all stored)')
    consolidate = commands.add_parser('consolidate', help='Merge imported claims and research bundles into graph files')
    consolidate.add_argument('domain', type=Path, help='Domain YAML configuration')
    knowledge = commands.add_parser('knowledge', help='Build a portable knowledge library with INDEX.md and packs')
    knowledge.add_argument('domain', type=Path, help='Domain YAML configuration')
    knowledge.add_argument('--output', type=Path, help='Library folder (default: <output_dir>/knowledge/<domain>); '
                           'keep it outside the application repository')
    knowledge.add_argument('--topic', dest='topics', action='append', metavar='TYPE/NAME',
                           help='Also write a topic pack; repeat. Keys are listed under topics/')
    knowledge.add_argument('--budget', dest='budgets', action='append', type=_budget, metavar='PRESET=TOKENS',
                           help='Approximate token budget (characters/4) for essentials, topic or full; repeat')
    ui = commands.add_parser('ui', help='Run the local Streamlit interface (requires ui extra)')
    ui.add_argument('--port', type=int, default=8501)
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        config = load_config(args.config)
        configure_logging(config.log_level)
        if args.command == "config":
            print(json.dumps(asdict(config), default=str, indent=2))
        elif args.command == "init":
            for directory in (config.data_dir, config.source_dir, config.output_dir):
                directory.mkdir(parents=True, exist_ok=True)
            version = migrate(config.database)
            print(f"Initialized {config.database} (schema {version})")
        elif args.command == 'export':
            report = workflows.export(config, formats=args.formats or ('markdown',),
                                      grouping=args.group_size, video_ids=args.video_ids)
            print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, allow_nan=False))
        elif args.command == 'jobs':
            domain = jobs.load_domain(args.domain)
            if args.job_command == 'create':
                statuses = jobs.create_jobs(config.database, config.output_dir, domain, args.video_ids)
            else:
                statuses = jobs.import_results(config.database, config.output_dir, domain)
            print(json.dumps([asdict(status) for status in statuses], ensure_ascii=False, indent=2))
            return int(any(status.status == 'rejected' for status in statuses))
        elif args.command == 'consolidate':
            report = graph.consolidate(config.database, config.source_dir, config.output_dir,
                                       jobs.load_domain(args.domain))
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return int(any(bundle['status'] == 'rejected' for bundle in report['bundles']))
        elif args.command == 'knowledge':
            report = library.build(config.database, config.source_dir, config.output_dir,
                                   jobs.load_domain(args.domain), args.output, args.topics or (),
                                   dict(args.budgets or ()))
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return int(any(bundle['status'] == 'rejected' for bundle in report['graph']['bundles']))
        elif args.command == 'ui':
            if not 1 <= args.port <= 65535:
                raise ValueError('port must be between 1 and 65535')
            if importlib.util.find_spec('streamlit') is None:
                raise ValueError('Install the ui extra to run Streamlit: pip install ".[ui]"')
            env = os.environ.copy()
            if args.config is not None:
                env['KFORGE_CONFIG'] = str(args.config.resolve())
            return subprocess.run([sys.executable, '-m', 'streamlit', 'run',
                str(Path(__file__).with_name('ui.py')), '--server.address=127.0.0.1',
                f'--server.port={args.port}', '--server.headless=true',
                '--browser.gatherUsageStats=false'], env=env, check=False).returncode
        else:
            urls = list(args.urls)
            if args.url_file is not None:
                urls.extend(parse_url_list(args.url_file.read_text(encoding="utf-8")))
            if not urls:
                raise ValueError("Provide at least one URL or a nonempty URL file")
            if args.command == 'scrape':
                report = workflows.scrape(config, urls, limit=args.limit, order=args.order,
                    formats=args.formats or ('markdown',), grouping=args.group_size,
                    languages=tuple(args.languages or ('en',)), preference=args.preference,
                    retry_failed=args.retry_failed)
                print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, allow_nan=False))
                return int(report.has_errors)
            manifest = discover(urls, limit=args.limit, order=args.order)
            print(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, allow_nan=False))
            return int(any(source.issues for source in manifest.sources))
    except (ConfigError, OSError, UnicodeError, sqlite3.Error, ValueError, RuntimeError) as exc:
        print(f"kforge: {exc}", file=sys.stderr)
        return 1
    return 0
