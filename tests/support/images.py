"""Reference images for the gateway tests."""

import io

from PIL import Image

from studio.l1_entities.image_job import ReferenceImage


def png(width, height):
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "red").save(buffer, format="PNG")
    return ReferenceImage(png=buffer.getvalue(), width=width, height=height)
