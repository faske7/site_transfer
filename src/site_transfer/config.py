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
    scenarios = config.get("interactions", {}).get("scenarios", [])
    if scenarios:
        from .discovery import seed_routes
        ids = [s["id"] for s in scenarios]
        if len(ids) != len(set(ids)):
            raise ConfigError("Interaction scenario IDs must be unique")
        if not config["interactions"].get("enabled", True):
            raise ConfigError("Enable interactions before declaring scenarios")
        allowed_views = set(names or ["desktop", "mobile"])
        try:
            routes, _ = seed_routes(config)
        except ValueError as exc:
            raise ConfigError("Interaction scenarios require default HTTP(S) ports") from exc
        allowed_routes = {urlsplit(url).path or "/" for url in routes}
        for scenario in scenarios:
            if scenario["route"] not in allowed_routes:
                raise ConfigError("Interaction scenario route must be an explicit seed within the capture limit")
            if not set(scenario.get("viewports", allowed_views)).issubset(allowed_views):
                raise ConfigError("Interaction scenario references an unknown viewport")
    timeline = config.get("scroll_timeline", {})
    if timeline.get("enabled", False):
        from .discovery import seed_routes
        allowed_views = set(names or ["desktop", "mobile"])
        profiles = [p["viewport"] for p in timeline["profiles"]]
        if len(profiles) != len(set(profiles)) or not set(profiles).issubset(allowed_views):
            raise ConfigError("Timeline profiles must reference unique known viewports")
        try:
            routes, _ = seed_routes(config)
        except ValueError as exc:
            raise ConfigError("Timeline requires default HTTP(S) ports") from exc
        if not set(timeline.get("routes", ["/"])).issubset({urlsplit(url).path or "/" for url in routes}):
            raise ConfigError("Timeline routes must be explicit seeds within the capture limit")
        if len(profiles) * len(timeline.get("routes", ["/"])) > 2:
            raise ConfigError("Timeline supports at most two route/viewport sequences per run")
        if timeline.get("max_frames",150) <= timeline.get("stable_steps",5):
            raise ConfigError("Timeline frame budget must exceed stable steps")
    if config.get("documentation", {}).get("language", "en") != "en":
        raise ConfigError("PR-01 documentation supports only English")
    return config
