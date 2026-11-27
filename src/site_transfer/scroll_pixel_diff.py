"""Pixel-equivalent timeline differences; at most one retained RGB frame."""
from contextlib import closing
from io import BytesIO
from time import perf_counter

from PIL import Image, ImageChops

PIXEL_THRESHOLD = 12
_DIM = [x // 3 for x in range(256)]
_THRESHOLD = [255 if x > PIXEL_THRESHOLD else 0 for x in range(256)]


def _decode(data):
    # Explicit ownership transfer: only a fully decoded RGB frame escapes.
    with BytesIO(data) as source:
        image = Image.open(source)
        try:
            image.load()
            if image.mode == "RGB":
                return image
            rgb = image.convert("RGB")
        except BaseException:
            image.close()
            raise
        image.close()
        return rgb


def _render(a, b):
    if a.size != b.size:
        raise ValueError("Timeline viewport dimensions changed")
    with closing(ImageChops.difference(a, b)) as diff:
        r, g, blue = diff.split()
    with closing(r), closing(g), closing(blue), closing(ImageChops.lighter(r, g)) as rg, \
            closing(ImageChops.lighter(rg, blue)) as maximum:
        mask = maximum.point(_THRESHOLD)
    with closing(mask):
        percent = round(mask.histogram()[255] / (a.width * a.height) * 100, 4)
        with closing(b.convert("L")) as gray, closing(gray.point(_DIM)) as dark:
            background = dark.convert("RGB")
        with closing(background), BytesIO() as output:
            # The mask is binary: in-place paste is pixel-equivalent to composite.
            background.paste((255, 45, 45), (0, 0, b.width, b.height), mask)
            background.save(output, format="PNG")
            return percent, output.getvalue()


def visual_diff(previous, current):
    """Compatibility entry point for callers with two raw PNGs."""
    with closing(_decode(previous)) as a, closing(_decode(current)) as b:
        return _render(a, b)


class PixelDiffSequence:
    def __init__(self, diagnostics=None):
        self.previous = None
        self.diagnostics = diagnostics

    def advance(self, data):
        start = perf_counter()
        current = None
        try:
            try:
                current = _decode(data)
            finally:
                if self.diagnostics is not None:
                    self.diagnostics.add_time("png_decode_ms", start)
            result = (None, None) if self.previous is None else _render(self.previous, current)
            self.close()
            self.previous, current = current, None
            return result
        finally:
            if current is not None:
                current.close()
            if self.diagnostics is not None:
                self.diagnostics.add_time("pixel_diff_ms", start)

    def close(self):
        if self.previous is not None:
            self.previous.close()
            self.previous = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
