"""Normalized observations. Never infer design-system values or accessibility compliance."""
from collections import Counter
import math
import re

PX = re.compile(r"^(-?(?:\d+(?:\.\d*)?|\.\d+))px$")
TIME = re.compile(r"^(-?(?:\d+(?:\.\d*)?|\.\d+))(ms|s)$")
RGB = re.compile(r"^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*(\d*\.?\d+))?\s*\)$")
SPACING = ("gap","row-gap","column-gap","padding-top","padding-right","padding-bottom",
           "padding-left","margin-top","margin-right","margin-bottom","margin-left","border-radius")
TEXT = ("font-size","line-height","letter-spacing")
COLOR = ("color","background-color","border-top-color","border-right-color","border-bottom-color","border-left-color")


def pixels(value):
    match=PX.fullmatch(value or "")
    if not match:
        return None
    number=float(match[1])
    return number if math.isfinite(number) else None


def milliseconds(value):
    match=TIME.fullmatch(value or "")
    if not match:
        return None
    number=float(match[1])*(1000 if match[2]=="s" else 1)
    return round(number,6) if math.isfinite(number) else None


def rgba(value):
    match=RGB.fullmatch(value or "")
    if not match:
        return None
    channels=tuple(int(v) for v in match.groups()[:3])
    alpha=float(match[4]) if match[4] is not None else 1.0
    if any(v>255 for v in channels) or not 0<=alpha<=1:
        return None
    return "#"+"".join(f"{v:02x}" for v in channels),alpha


def ranked(counter, limit=40):
    return [{"value":value,"count":count} for value,count in
            sorted(counter.items(),key=lambda item:(-item[1],item[0]))[:limit]]


def summarize_advanced(elements):
    numbers={p:Counter() for p in SPACING+TEXT}
    times={p:Counter() for p in ("transition-duration","transition-delay","animation-duration","animation-delay")}
    palette=Counter()
    headings=[]
    landmarks=[]
    containers=[]
    semantic_count=0
    images_without_alt=0
    for row in elements:
        style=row.get("style",{})
        for prop,counts in numbers.items():
            value=pixels(style.get(prop))
            if value is not None:
                counts[value]+=1
        for prop,counts in times.items():
            for raw in style.get(prop,"").split(","):
                value=milliseconds(raw.strip())
                if value is not None:
                    counts[value]+=1
        for prop in COLOR:
            color=rgba(style.get(prop))
            if color is not None:
                palette[color]+=1
        semantic=row.get("semantic")
        if semantic is not None:
            semantic_count+=1
            images_without_alt+=semantic.get("has_alt") is False
            if semantic.get("heading_level") is not None and len(headings)<40:
                headings.append({"selector":row["selector"],"level":semantic["heading_level"],
                                 "font_size":style.get("font-size"),"font_weight":style.get("font-weight"),
                                 "line_height":style.get("line-height"),"font_family":style.get("font-family")})
            if semantic.get("landmark_tag") and len(landmarks)<40:
                landmarks.append({"selector":row["selector"],"tag":row["tag"],"role":row.get("role","")})
        if (style.get("display") in ("grid","inline-grid","flex","inline-flex")
                or style.get("position") in ("fixed","sticky")) and len(containers)<60:
            containers.append({"selector":row["selector"],"parent_selector":row.get("parent_selector"),
                               "rect":row["rect"],"display":style.get("display"),"position":style.get("position"),
                               "gap":style.get("gap"),"grid_columns":style.get("grid-template-columns"),
                               "flex_direction":style.get("flex-direction"),"max_width":style.get("max-width")})
    return {
        "basis":"Sampled computed CSS; counts are property occurrences, not distinct design tokens",
        "spacing_px":{p:ranked(numbers[p]) for p in SPACING},
        "typography_px":{p:ranked(numbers[p]) for p in TEXT},
        "palette":[{"hex":hex_value,"alpha":alpha,"count":count} for (hex_value,alpha),count in
                   sorted(palette.items(),key=lambda item:(-item[1],item[0]))[:40]],
        "motion_ms":{p:ranked(counts) for p,counts in times.items()},
        "headings":headings,"containers":containers,
        "accessibility":{"sampled_metadata_count":semantic_count,"landmark_tag_candidates":landmarks,
                         "sampled_images_without_alt_attribute":images_without_alt,
                         "basis":"DOM metadata only; not accessible names, accessibility tree or compliance audit"},
        "limitations":["Unsupported CSS units, complex colors and multi-value lengths remain in raw styles",
                       "Normalized motion values are computed CSS timing, not measured playback",
                       "Heading, landmark and container lists are bounded samples"],
    }
