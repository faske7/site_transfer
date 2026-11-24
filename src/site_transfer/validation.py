"""Validate the required target-project documentation."""
from pathlib import Path

REQUIRED_FILES = ("CONTEXT.md", "AGENTS.md", "TASK.md", "README.md")
CONTEXT_SECTIONS = (
    "Purpose", "Architecture", "Technology stack", "Important files",
    "Development commands", "Current status", "Technical decisions",
    "Known issues", "Next steps",
)


def validate_project(root: Path | str) -> list[str]:
    root = Path(root)
    errors = []
    for name in REQUIRED_FILES:
        path = root / name
        if path.is_symlink() or not path.is_file():
            errors.append(f"Missing regular file: {name}")
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            errors.append(f"Unreadable file: {name}")
            continue
        if not content.strip():
            errors.append(f"Empty file: {name}")
        if name == "CONTEXT.md":
            headings = {line.strip() for line in content.splitlines()}
            for section in CONTEXT_SECTIONS:
                if f"## {section}" not in headings:
                    errors.append(f"CONTEXT.md missing section: {section}")
    return errors
