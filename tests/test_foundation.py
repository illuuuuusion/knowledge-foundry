from contextlib import closing, redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import kforge
from kforge.cli import main
from kforge.config import ConfigError, load_config
from kforge.storage import MIGRATIONS, migrate


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_import_and_defaults_without_side_effects(self):
        self.assertEqual(kforge.__version__, "0.1.0")
        config = load_config(cwd=self.root, environ={})
        self.assertEqual(config.data_dir, self.root / "data")
        self.assertEqual(config.source_dir, self.root / "sources")
        self.assertEqual(config.output_dir, self.root / "output")
        self.assertEqual(config.database, self.root / "data/state.sqlite3")
        self.assertEqual(config.log_level, "INFO")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_toml_paths_are_relative_to_config_and_environment_wins(self):
        folder = self.root / "settings"
        folder.mkdir()
        file = folder / "custom.toml"
        file.write_text('[paths]\ndata_dir="store"\nsource_dir="input"\n'
                        '[logging]\nlevel="WARNING"\n')
        config = load_config(file, cwd=self.root, environ={
            "KFORGE_OUTPUT_DIR": "exports", "KFORGE_LOG_LEVEL": "debug"
        })
        self.assertEqual(config.data_dir, folder / "store")
        self.assertEqual(config.database, folder / "store/state.sqlite3")
        self.assertEqual(config.source_dir, folder / "input")
        self.assertEqual(config.output_dir, self.root / "exports")
        self.assertEqual(config.log_level, "DEBUG")

    def test_environment_can_select_file_and_override_every_path(self):
        file = self.root / "custom.toml"
        file.write_text('[paths]\ndata_dir="unused"\n')
        config = load_config(cwd=self.root, environ={
            "KFORGE_CONFIG": "custom.toml", "KFORGE_DATA_DIR": "d",
            "KFORGE_SOURCE_DIR": "s", "KFORGE_OUTPUT_DIR": "o",
            "KFORGE_DATABASE": "db/custom.sqlite3",
        })
        self.assertEqual(config.data_dir, self.root / "d")
        self.assertEqual(config.source_dir, self.root / "s")
        self.assertEqual(config.output_dir, self.root / "o")
        self.assertEqual(config.database, self.root / "db/custom.sqlite3")

    def test_explicit_file_wins_over_file_environment(self):
        file = self.root / "custom.toml"
        file.write_text('[logging]\nlevel="ERROR"\n')
        self.assertEqual(load_config(file, environ={"KFORGE_CONFIG": "missing"})
                         .log_level, "ERROR")

    def test_missing_and_malformed_files_are_configuration_errors(self):
        file = self.root / "custom.toml"
        for content in (None, "[invalid", '[paths]\ndata_dir=0',
                        '[unknown]\nx=1', 'paths="invalid"',
                        '[logging]\nlevel=3', '[paths]\nunknown="x"'):
            with self.subTest(content=content):
                if content is not None:
                    file.write_text(content)
                with self.assertRaises(ConfigError):
                    load_config(file, environ={})

    def test_empty_paths_and_invalid_log_levels_are_rejected(self):
        for env in ({"KFORGE_DATA_DIR": " "}, {"KFORGE_LOG_LEVEL": "TRACE"}):
            with self.subTest(env=env), self.assertRaises(ConfigError):
                load_config(cwd=self.root, environ=env)

    def test_non_utf8_file_is_a_configuration_error(self):
        file = self.root / "custom.toml"
        file.write_bytes(b"\xff\xfe")
        with self.assertRaises(ConfigError):
            load_config(file, environ={})


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "nested/state.sqlite3"

    def test_fresh_and_repeated_migrations_preserve_one_row_per_version(self):
        self.assertEqual(migrate(self.database), 3)
        self.assertEqual(migrate(self.database), 3)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone(), (3,))
            self.assertEqual(connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version").fetchall(), [(1,), (2,), (3,)])

    def test_newer_database_is_rejected_without_downgrade(self):
        migrate(self.database)
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("PRAGMA user_version = 99")
        with self.assertRaisesRegex(ValueError, "newer"):
            migrate(self.database)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone(), (99,))

    def test_failed_migration_rolls_back_schema_and_version(self):
        migrate(self.database)
        from kforge.storage import MIGRATIONS
        with patch("kforge.storage.MIGRATIONS", MIGRATIONS + ((4, (
            "CREATE TABLE partial (id INTEGER)", "INVALID SQL"
        )),)):
            with self.assertRaises(sqlite3.Error):
                migrate(self.database)
        with closing(sqlite3.connect(self.database)) as connection:
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone(), (3,))
            self.assertEqual(connection.execute(
                "SELECT name FROM sqlite_master WHERE name = 'partial'").fetchall(), [])
            self.assertEqual(connection.execute(
                "SELECT version FROM schema_migrations ORDER BY version").fetchall(), [(1,), (2,), (3,)])


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {}, clear=True).start()

    def test_installed_console_help_and_module_help_without_writes(self):
        executable = Path(sys.executable).parent / "kforge"
        for command in ([str(executable), "--help"],
                        [sys.executable, "-m", "kforge", "--help"]):
            with self.subTest(command=command):
                result = subprocess.run(command, cwd=self.root, capture_output=True,
                                        text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Knowledge Foundry", result.stdout)
                self.assertIn("init", result.stdout)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_no_command_shows_help_and_version_is_available(self):
        with redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(main([]), 0)
        self.assertIn("usage: kforge", stream.getvalue())
        with redirect_stdout(io.StringIO()) as stream, self.assertRaises(SystemExit) as raised:
            main(["--version"])
        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(stream.getvalue().strip(), kforge.__version__)

    def test_config_prints_only_supported_settings_without_initializing(self):
        with patch.dict(os.environ, {"KFORGE_DATA_DIR": str(self.root / "d"),
                                     "UNRELATED_SECRET": "never-print-this"}):
            with redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(main(["config"]), 0)
        data = json.loads(stream.getvalue())
        self.assertEqual(data["data_dir"], str(self.root / "d"))
        self.assertNotIn("never-print-this", stream.getvalue())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_init_is_repeatable_with_custom_paths(self):
        env = {f"KFORGE_{name}_DIR": str(self.root / name.lower())
               for name in ("DATA", "SOURCE", "OUTPUT")}
        with patch.dict(os.environ, env), redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(main(["init"]), 0)
            self.assertEqual(main(["init"]), 0)
        for name in ("data", "source", "output"):
            self.assertTrue((self.root / name).is_dir())
        self.assertIn("schema 3", stream.getvalue())

    def test_invalid_config_returns_error_without_traceback(self):
        with redirect_stderr(io.StringIO()) as stream:
            self.assertEqual(main(["--config", str(self.root / "missing"), "init"]), 1)
        self.assertIn("Cannot read TOML", stream.getvalue())
        self.assertNotIn("Traceback", stream.getvalue())

    def test_database_error_returns_nonzero(self):
        file = self.root / "occupied"
        file.write_text("synthetic fixture")
        with patch.dict(os.environ, {"KFORGE_DATA_DIR": str(file)}):
            with redirect_stderr(io.StringIO()) as stream:
                self.assertEqual(main(["init"]), 1)
        self.assertTrue(stream.getvalue().startswith("kforge:"))
