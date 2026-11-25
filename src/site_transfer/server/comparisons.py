"""Persist comparison results in the existing project volume."""
import json
import shutil
from uuid import UUID, uuid4

from site_transfer.comparison import compare_runs
from site_transfer.manifest import evidence_file, digest
from .settings import project_root
from .storage import run_root
from . import jobs


def base(project_id):
    return project_root() / str(project_id) / "design" / "comparisons"


def read(project_id, comparison_id):
    folder = base(project_id) / str(comparison_id)
    try:
        return json.loads(evidence_file(folder,"comparison.json").read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise FileNotFoundError from None


def create(project_id, reference_id, implementation_project_id, implementation_id):
    reference = jobs.get(project_id, reference_id)
    implementation = jobs.get(implementation_project_id, implementation_id)
    if reference is None or implementation is None:
        raise FileNotFoundError("Capture not found")
    comparison_id = uuid4()
    output = base(project_id) / str(comparison_id)
    try:
        result = compare_runs(reference, implementation, run_root(project_id,reference_id),
                              run_root(implementation_project_id,implementation_id),output)
        result.update({"id":str(comparison_id),"reference_project":str(project_id),
                       "implementation_project":str(implementation_project_id)})
        temporary = output / "comparison.tmp"
        temporary.write_text(json.dumps(result, indent=2), encoding="utf-8")
        temporary.replace(output / "comparison.json")
    except Exception:
        if output.exists():
            shutil.rmtree(output)
        raise
    return result


def list_results(project_id):
    root = base(project_id)
    if not root.is_dir():
        return []
    results = []
    for folder in sorted(root.iterdir(),key=lambda p:p.stat().st_mtime,reverse=True):
        try:
            result = read(project_id, UUID(folder.name))
        except (ValueError, FileNotFoundError):
            continue
        results.append({"id":result["id"],"reference_run":result["reference_run"],
                        "implementation_run":result["implementation_run"],"passes":result["passes"]})
        if len(results) == 50:
            break
    return results


def diff_path(project_id, comparison_id, index):
    result = read(project_id, comparison_id)
    if not 0 <= index < len(result["pairs"]):
        raise FileNotFoundError
    entry = result["pairs"][index]
    try:
        path = evidence_file(base(project_id)/str(comparison_id),entry["diff"])
        if path.suffix != ".png" or digest(path) != entry["diff_sha256"]:
            raise ValueError("Invalid diff")
    except ValueError:
        raise FileNotFoundError from None
    return path
