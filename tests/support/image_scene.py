"""Read a scene's four edges without including its central subject."""

from PIL import Image


def scene_border(path, side=64, edge_fraction=0.12):
    image = Image.open(path).convert("RGB").resize((side, side))
    band = int(side * edge_fraction)
    strips = [
        image.crop((0, 0, side, band)),
        image.crop((0, side - band, side, side)),
        image.crop((0, 0, band, side)).transpose(Image.Transpose.ROTATE_90),
        image.crop((side - band, 0, side, side)).transpose(Image.Transpose.ROTATE_90),
    ]
    out = Image.new("RGB", (side, band * 4))
    for index, strip in enumerate(strips):
        out.paste(strip, (0, band * index))
    return out
