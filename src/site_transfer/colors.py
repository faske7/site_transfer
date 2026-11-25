"""Observed CSS colors and background effects."""
from .typography import frequency


def colors(elements):
    return frequency(elements, ("color", "background-color", "border-top-color", "background-image"))
