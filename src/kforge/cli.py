"""Foundation CLI; source ingestion is deliberately reserved for later phases."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import sys

from . import __version__
from .config import ConfigError, load_config
from .logging import configure_logging
from .storage import migrate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="kforge", description="Knowledge Foundry")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", type=Path, help="TOML configuration file")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("config", help="Show resolved paths and logging level")
    commands.add_parser("init", help="Create local directories and migrate SQLite")
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        config = load_config(args.config)
        configure_logging(config.log_level)
        if args.command == "config":
            print(json.dumps(asdict(config), default=str, indent=2))
        else:
            for directory in (config.data_dir, config.source_dir, config.output_dir):
                directory.mkdir(parents=True, exist_ok=True)
            version = migrate(config.database)
            print(f"Initialized {config.database} (schema {version})")
    except (ConfigError, OSError, sqlite3.Error, ValueError) as exc:
        print(f"kforge: {exc}", file=sys.stderr)
        return 1
    return 0
