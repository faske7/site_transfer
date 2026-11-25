"""Check tracked bundle inputs, not local ignored working-tree files."""
import subprocess
from pathlib import PurePosixPath

INPUTS = ("compose.yaml", "Dockerfile", ".dockerignore", "pyproject.toml", "README.md", "src", "frontend")


def check_records(records):
    for entry in records:
        if not entry:
            continue
        metadata, path = entry.split("\t", 1)
        mode, kind, _ = metadata.split()
        name = PurePosixPath(path).name.lower()
        if (kind != "blob" or mode not in {"100644", "100755"}
                or any(part.lower() in {".git", "node_modules", "target", "dist"} for part in PurePosixPath(path).parts)
                or name == ".env" or name.startswith(".env.") or name == ".npmrc"
                or name.endswith((".pem", ".key", ".p12", ".pfx"))):
            raise ValueError(f"Unsafe tracked runtime input: {path}")


def main():
    raw = subprocess.check_output(["git", "ls-tree", "-rz", "HEAD", "--", *INPUTS])
    check_records(raw.decode("utf-8").split("\0"))


if __name__ == "__main__":
    main()
