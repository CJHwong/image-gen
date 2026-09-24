"""PNG bytes to PIL images and back. The core carries bytes; engines want PIL."""

import io

from PIL import Image


def to_pil(png: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(png))
    image.load()
    return image


def to_png(image: Image.Image) -> bytes:
    """No EXIF and no text chunks: mflux writes the prompt into a PNG it saves, and this path never saves."""
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
