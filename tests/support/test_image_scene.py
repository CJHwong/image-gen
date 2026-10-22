"""All four scene edges stay separate from the image's central subject."""

from PIL import Image, ImageDraw

from tests.support.image_scene import scene_border


def test_scene_border_reads_each_whole_edge_without_central_pixels(tmp_path):
    image = Image.new("RGB", (64, 64), "magenta")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 63, 6), fill="red")
    draw.rectangle((0, 57, 63, 63), fill="blue")
    draw.rectangle((0, 0, 6, 63), fill="green")
    draw.rectangle((57, 0, 63, 63), fill="yellow")
    path = tmp_path / "scene.png"
    image.save(path)
    border = scene_border(path)
    assert border.size == (64, 28)
    assert [border.getpixel((32, 3 + 7 * index)) for index in range(4)] == [
        (255, 0, 0),
        (0, 0, 255),
        (0, 128, 0),
        (255, 255, 0),
    ]
    assert (255, 0, 255) not in [pixel for _, pixel in border.getcolors()]
