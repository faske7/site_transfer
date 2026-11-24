import json
from importlib.resources import files
from pathlib import Path

import pytest

from site_transfer.cli import main
from site_transfer.config import ConfigError, load_config
from site_transfer.documentation import initialize_project
from site_transfer.validation import REQUIRED_FILES, validate_project

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "remaxdelux.json"


def test_packaged_resources_match_public_files():
    resources = files("site_transfer").joinpath("resources")
    assert resources.joinpath("transfer.schema.json").read_bytes() == (ROOT / "schemas" / "transfer.schema.json").read_bytes()
    for name in REQUIRED_FILES:
        template = name + ".j2"
        assert resources.joinpath("templates", template).read_bytes() == (ROOT / "templates" / template).read_bytes()


def test_example_and_plan(capsys):
    assert main(["validate", str(EXAMPLE)]) == 0
    capsys.readouterr()
    assert main(["plan", str(EXAMPLE)]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["network_access"] is False
    assert "CONTEXT.md" in plan["required_documents"]
    assert "capture" in plan["pending"]


@pytest.mark.parametrize("change", [
    {"source": {"url": "file:///etc/passwd"}},
    {"source": {"url": "https://user:pass@example.com"}},
    {"source": {"url": "https://example.com:99999"}},
    {"execution": {"require_review_before_push": False}},
    {"documentation": {"context": False}},
    {"target": {"project_name": "../escape"}},
    {"viewports": [{"name": "a", "width": 390, "height": 844}, {"name": "a", "width": 400, "height": 900}]},
])
def test_invalid_config(tmp_path, change):
    config = load_config(EXAMPLE)
    config.update(change)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)
    assert main(["validate", str(path)]) == 1


def test_duplicate_json_keys(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"source": {}, "source": {}}', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


def test_generate_and_validate(tmp_path):
    output = tmp_path / "target"
    assert main(["init", str(EXAMPLE), "--output", str(output)]) == 0
    assert set(p.name for p in output.iterdir()) == set(REQUIRED_FILES)
    assert main(["validate-project", str(output)]) == 0
    assert "remaxdelux" in (output / "CONTEXT.md").read_text()
    (output / "CONTEXT.md").unlink()
    assert main(["validate-project", str(output)]) == 1


def test_no_overwrite(tmp_path):
    (tmp_path / "CONTEXT.md").write_text("existing")
    with pytest.raises(FileExistsError):
        initialize_project(load_config(EXAMPLE), tmp_path)
    assert (tmp_path / "CONTEXT.md").read_text() == "existing"
    assert not (tmp_path / "AGENTS.md").exists()


def test_context_sections_required(tmp_path):
    initialize_project(load_config(EXAMPLE), tmp_path)
    (tmp_path / "CONTEXT.md").write_text("# Incomplete context")
    assert any("Architecture" in error for error in validate_project(tmp_path))


def test_existing_broken_symlink_is_not_overwritten(tmp_path):
    (tmp_path / "CONTEXT.md").symlink_to(tmp_path / "missing")
    with pytest.raises(FileExistsError):
        initialize_project(load_config(EXAMPLE), tmp_path)
    assert (tmp_path / "CONTEXT.md").is_symlink()
