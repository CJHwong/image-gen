"""Image size helpers that every mflux adapter shares."""


def match_reference_size(width: int, height: int, budget: int = 1024 * 1024) -> tuple[int, int]:
    """The reference's own aspect ratio at about `budget` pixels, on a 16 grid.

    mflux resizes the reference to the target size with a plain resize, so a
    square output from a 16:9 photo would squash it. This keeps the shape.
    """
    scale = (budget / (width * height)) ** 0.5
    return max(16, 16 * round(width * scale / 16)), max(16, 16 * round(height * scale / 16))
