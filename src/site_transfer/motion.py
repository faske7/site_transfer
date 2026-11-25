"""Observed animation timing and declared transition values."""
from .typography import frequency


def motion(snapshot):
    elements = snapshot["elements"]
    moving = [row for row in elements if row["style"].get("animation-name") not in (None, "", "none")
              or any(value.strip() not in ("0s", "0ms", "") for value in row["style"].get("transition-duration", "").split(","))]
    return {"declared": frequency(moving, (
        "transition-property", "transition-duration", "transition-delay", "transition-timing-function",
        "animation-name", "animation-duration", "animation-delay", "animation-timing-function",
        "animation-iteration-count")), "observed": snapshot["animations"],
        "keyframes": snapshot["keyframes"]}
