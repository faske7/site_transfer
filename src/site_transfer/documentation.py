"""Render the mandatory handoff documentation; never overwrite user files."""
from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from .validation import REQUIRED_FILES, validate_project


def initialize_project(config: dict, output: Path | str) -> Path:
    output = Path(output)
    resources = files("site_transfer").joinpath("resources", "templates")
    env = Environment(undefined=StrictUndefined, keep_trailing_newline=True, autoescape=False)
    target = config["target"]
    values = {
        "project_name": target["project_name"],
        "source_url": config["source"]["url"],
        "backend": target.get("backend", "To be decided"),
        "frontend": target.get("frontend", "To be decided"),
    }
    rendered = {
        name: env.from_string(resources.joinpath(name + ".j2").read_text(encoding="utf-8")).render(**values)
        for name in REQUIRED_FILES
    }
    if output.is_symlink():
        raise ValueError("Output directory must not be a symbolic link")
    output.mkdir(parents=True, exist_ok=True)
    conflicts = [name for name in REQUIRED_FILES if (output / name).exists() or (output / name).is_symlink()]
    if conflicts:
        raise FileExistsError("Refusing to overwrite: " + ", ".join(conflicts))
    created = []
    try:
        for name, content in rendered.items():
            path = output / name
            with path.open("x", encoding="utf-8") as handle:
                created.append(path)
                handle.write(content)
        errors = validate_project(output)
        if errors:
            raise ValueError("; ".join(errors))
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    return output
