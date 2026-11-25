"""Stage-level pipeline checkpoints and reviewed kit generation."""
from pathlib import Path
from uuid import uuid4

from .manifest import build_kit, digest


class CaptureCancelled(Exception):
    pass


def make_kit(config, job, root: Path, destination: Path, attempts=2):
    """Retry only ZIP I/O, never repeat a successful browser capture."""
    if not 1 <= attempts <= 2:
        raise ValueError("Invalid retry budget")
    destination.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, attempts + 1):
        temporary = destination.parent / (str(uuid4()) + ".tmp")
        try:
            build_kit(config, job, root, temporary)
            checksum = digest(temporary)
            temporary.replace(destination)
            return {"sha256": checksum, "bytes": destination.stat().st_size, "attempts": attempt}
        except OSError:
            if attempt == attempts:
                raise
        finally:
            temporary.unlink(missing_ok=True)
    raise RuntimeError("Kit generation failed")
