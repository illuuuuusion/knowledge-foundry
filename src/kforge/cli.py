"""Local configuration, initialization and metadata discovery CLI."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys

from . import __version__
from .config import ConfigError, load_config
from .logging import configure_logging
from .ingest.discovery import discover
from .ingest.urls import parse_url_list
from .storage import migrate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kforge", description="Knowledge Foundry")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", type=Path, help="TOML configuration file")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("config", help="Show resolved paths and logging level")
    commands.add_parser("init", help="Create local directories and migrate SQLite")
    discovery = commands.add_parser("discover", help="Discover YouTube video metadata as JSON")
    discovery.add_argument("urls", nargs="*", help="Video, playlist or channel URLs")
    discovery.add_argument("--url-file", type=Path, help="UTF-8 file with one URL per line")
    discovery.add_argument("--limit", type=int, help="Maximum unique videos across sources")
    discovery.add_argument("--order", choices=("source", "id"), default="source")
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
        else:
            urls = list(args.urls)
            if args.url_file is not None:
                urls.extend(parse_url_list(args.url_file.read_text(encoding="utf-8")))
            if not urls:
                raise ValueError("Provide at least one URL or a nonempty URL file")
            manifest = discover(urls, limit=args.limit, order=args.order)
            print(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, allow_nan=False))
            return int(any(source.issues for source in manifest.sources))
    except (ConfigError, OSError, UnicodeError, sqlite3.Error, ValueError) as exc:
        print(f"kforge: {exc}", file=sys.stderr)
        return 1
    return 0
