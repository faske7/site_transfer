"""Compare recorded screenshots without browser navigation or rescaling."""
import json
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image, ImageChops

from .manifest import evidence_file, digest

PIXEL_TOLERANCE = 16
PASS_PERCENT = 1.0
MAX_PIXELS = 16_000_000
MAX_PAIRS = 30
MAX_TOTAL_PIXELS = 120_000_000


def key(item):
    return (urlsplit(item["url"]).path or "/", item["viewport"], item["width"], item["height"])


def index_artifacts(manifest):
    result = {}
    for index, item in enumerate(manifest.get("artifacts", [])):
        k = key(item)
        if k in result:
            raise ValueError("Ambiguous route and viewport in capture")
        result[k] = (index, item)
    return result


def verified_png(root, item):
    name = item["path"]
    if not name.startswith("screenshots/") or not name.endswith(".png"):
        raise ValueError("Invalid screenshot path")
    path = evidence_file(root, name)
    if digest(path) != item["sha256"]:
        raise ValueError("Screenshot checksum mismatch")
    return path


def png_size(path):
    with Image.open(path) as image:
        if image.format != "PNG":
            raise ValueError("Expected PNG screenshot")
        if image.width * image.height > MAX_PIXELS:
            raise ValueError("Screenshot exceeds comparison pixel budget")
        return image.size


def compare_pixels(reference, implementation, output):
    a_size, b_size = png_size(reference), png_size(implementation)
    width, height = max(a_size[0], b_size[0]), max(a_size[1], b_size[1])
    if width * height > MAX_PIXELS:
        raise ValueError("Combined canvas exceeds comparison pixel budget")
    # White background, top-left aligned, never stretch either screenshot.
    def canvas(path):
        with Image.open(path) as image:
            rgba = image.convert("RGBA")
            result = Image.new("RGB", (width, height), "white")
            result.paste(rgba, (0, 0), rgba.getchannel("A"))
            return result
    a, b = canvas(reference), canvas(implementation)
    diff = ImageChops.difference(a, b)
    channels = diff.split()
    peak = ImageChops.lighter(ImageChops.lighter(channels[0], channels[1]), channels[2])
    mask = peak.point([255 if i > PIXEL_TOLERANCE else 0 for i in range(256)])
    # Non-overlapping real screenshot area is always different, even if white.
    from PIL import ImageDraw
    coverage = []
    for w, h in (a_size, b_size):
        m = Image.new("L", (width, height))
        ImageDraw.Draw(m).rectangle((0, 0, w-1, h-1), fill=255)
        coverage.append(m)
    mask = ImageChops.lighter(mask, ImageChops.difference(*coverage))
    union = ImageChops.lighter(*coverage)
    mask = ImageChops.multiply(mask, union)
    count = mask.histogram()[255]
    pixels = union.histogram()[255]
    percent = count * 100 / pixels
    overlay = a.convert("L").point(lambda v: v // 3).convert("RGB")
    overlay.paste((255, 55, 75), mask=mask)
    overlay.save(output, format="PNG")
    return {"reference_size": list(a_size), "implementation_size": list(b_size),
            "dimensions_match": a_size == b_size, "pixels_compared": pixels,
            "changed_pixels": count, "changed_percent": percent,
            "similarity_percent": 100-percent,
            "passes": a_size == b_size and percent <= PASS_PERCENT,
            "difference_bounds": list(mask.getbbox()) if count else None}


def sampled_structure(a, b):
    """Compare matching positional selectors, not semantic DOM equivalence."""
    left = {row["selector"]:row for row in a.get("elements", [])}
    right = {row["selector"]:row for row in b.get("elements", [])}
    if not left or not right:
        return None
    shared = sorted(left.keys() & right.keys())
    differences = []
    for selector in shared:
        x, y = left[selector], right[selector]
        delta = {k: round(y["rect"][k] - x["rect"][k], 2) for k in ("x","y","width","height")}
        styles = [k for k in ("font-size","font-family","font-weight","color","background-color","display","gap")
                  if k in x["style"] and k in y["style"] and x["style"][k] != y["style"][k]]
        if any(abs(v) > 1 for v in delta.values()) or styles:
            differences.append({"selector":selector,"rect_delta":delta,"changed_style_properties":styles})
    return {"basis":"Sampled positional selectors; not semantic equivalence",
            "matched":len(shared),"reference_only":len(left.keys()-right.keys()),
            "implementation_only":len(right.keys()-left.keys()),
            "changed":len(differences),"examples":differences[:50]}


def design_for(root, manifest, index):
    for entry in manifest.get("design_reports", []):
        if entry.get("screenshot_index") == index:
            name = entry["path"]
            if not name.startswith("design/") or not name.endswith(".json"):
                raise ValueError("Invalid design report path")
            path = evidence_file(root, name)
            if path.stat().st_size > 16 * 1024 * 1024:
                raise ValueError("Design report exceeds size limit")
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def compare_runs(reference, implementation, reference_root, implementation_root, output):
    for job in (reference, implementation):
        if job["status"] not in ("completed", "partial"):
            raise ValueError("Select terminal completed or partial captures")
    if reference["id"] == implementation["id"]:
        raise ValueError("Choose two distinct capture runs")
    left, right = (index_artifacts(j["manifest"]) for j in (reference, implementation))
    common = sorted(left.keys() & right.keys())
    if not common:
        raise ValueError("No matching route and viewport dimensions")
    if len(common) > MAX_PAIRS:
        raise ValueError("Too many matching pairs (max 30)")
    pairs = []
    budget = 0
    for k in common:
        i, a = left[k]
        j, b = right[k]
        ap, bp = verified_png(reference_root, a), verified_png(implementation_root, b)
        aw, ah = png_size(ap)
        bw, bh = png_size(bp)
        budget += max(aw,bw)*max(ah,bh)
        if budget > MAX_TOTAL_PIXELS:
            raise ValueError("Comparison exceeds total pixel budget")
        pairs.append((k,i,j,ap,bp))
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for number, (k,i,j,ap,bp) in enumerate(pairs):
        name = f"diff-{number:03d}.png"
        metrics = compare_pixels(ap,bp,output/name)
        a = design_for(reference_root, reference["manifest"], i)
        b = design_for(implementation_root, implementation["manifest"], j)
        results.append({"route":k[0],"viewport":k[1],"width":k[2],"height":k[3],
                        "reference_index":i,"implementation_index":j,
                        "diff":name,"diff_sha256":digest(output/name),"metrics":metrics,
                        "structure":sampled_structure(a,b) if a is not None and b is not None else None})
    missing = [list(k) for k in sorted(left.keys()-right.keys())]
    extra = [list(k) for k in sorted(right.keys()-left.keys())]
    passed = not missing and not extra and all(x["metrics"]["passes"] for x in results)
    return {"schema_version":1,"reference_run":str(reference["id"]),"implementation_run":str(implementation["id"]),
            "pixel_tolerance":PIXEL_TOLERANCE,"max_changed_percent":PASS_PERCENT,
            "pairs":results,"reference_only":missing,"implementation_only":extra,
            "passes":passed,"limitations":["Pixel match is not functional correctness","Dynamic content is not masked",
            "Structural sample is not semantic DOM equivalence","Only successful screenshot pairs are matched"]}
