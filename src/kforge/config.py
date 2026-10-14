"""Explicit TOML/environment configuration without filesystem side effects."""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping
import tomllib


class ConfigError(ValueError):
    """Invalid local configuration."""


@dataclass(frozen=True)
class Config:
    data_dir: Path
    source_dir: Path
    output_dir: Path
    database: Path
    log_level: str = "INFO"


def load_config(
    config_path: Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> Config:
    env = os.environ if environ is None else environ
    base = (Path.cwd() if cwd is None else cwd).resolve()
    selected = config_path if config_path is not None else env.get("KFORGE_CONFIG")
    settings: dict = {}
    file_base = base
    if selected is not None:
        file = Path(selected).expanduser()
        file = file if file.is_absolute() else base / file
        try:
            with file.open("rb") as stream:
                settings = tomllib.load(stream)
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"Cannot read TOML configuration: {file}") from exc
        file_base = file.resolve().parent
    if set(settings) - {"paths", "logging"}:
        raise ConfigError("Unknown configuration section")
    paths = settings.get("paths", {})
    logging = settings.get("logging", {})
    if not isinstance(paths, dict) or set(paths) - {
        "data_dir", "source_dir", "output_dir", "database"
    }:
        raise ConfigError("Invalid paths configuration")
    if not isinstance(logging, dict) or set(logging) - {"level"}:
        raise ConfigError("Invalid logging configuration")

    def resolve(name: str, default: str | Path) -> Path:
        key = f"KFORGE_{name.upper()}"
        value = env.get(key, paths.get(name, default))
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise ConfigError(f"Path {name} must be a nonempty string")
        path = Path(value).expanduser()
        root = base if key in env else file_base
        return (path if path.is_absolute() else root / path).resolve()

    data = resolve("data_dir", "data")
    level = env.get("KFORGE_LOG_LEVEL", logging.get("level", "INFO"))
    if not isinstance(level, str) or level.upper() not in {
        "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
    }:
        raise ConfigError("Invalid log level")
    return Config(
        data, resolve("source_dir", "sources"), resolve("output_dir", "output"),
        resolve("database", data / "state.sqlite3"), level.upper(),
    )
