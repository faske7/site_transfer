"""Read and validate the versioned configuration without network access."""
import json
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator


class ConfigError(ValueError):
    """Invalid or unreadable configuration."""


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ConfigError(f"Non-standard JSON constant: {value}")


def _validate_url(url):
    if any(ch.isspace() or ord(ch) < 32 for ch in url) or "\\" in url:
        raise ConfigError("source.url must not contain whitespace or backslashes")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ConfigError("source.url is malformed") from exc
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.fragment or port == 0):
        raise ConfigError("source.url must be an HTTP(S) URL without credentials or fragment")


def load_config(path: Path | str) -> dict:
    try:
        config = json.loads(Path(path).read_text(encoding="utf-8"),
                            object_pairs_hook=_unique_keys,
                            parse_constant=_invalid_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"Cannot read configuration: {exc}") from exc
    return validate_config(config)


def validate_config(config: object) -> dict:
    """Validate an already decoded JSON value for CLI and API callers."""
    schema = json.loads(files("site_transfer").joinpath("resources", "transfer.schema.json").read_text(encoding="utf-8"))
    error = next(Draft202012Validator(schema).iter_errors(config), None)
    if error:
        location = ".".join(map(str, error.absolute_path)) or "<root>"
        # Do not echo entire values; configuration must not contain secrets.
        raise ConfigError(f"Invalid configuration at {location} ({error.validator})")
    _validate_url(config["source"]["url"])
    names = [v["name"] for v in config.get("viewports", [])]
    if len(names) != len(set(names)):
        raise ConfigError("Viewport names must be unique")
    if config.get("documentation", {}).get("language", "en") != "en":
        raise ConfigError("PR-01 documentation supports only English")
    return config
