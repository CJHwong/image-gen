import io

from PIL import Image, PngImagePlugin

from studio.l3_interface_adapters.gateways.png_images import to_pil, to_png


def test_png_bytes_come_back_as_the_pixels_they_held():
    # The core carries PNG bytes and the engine wants PIL, so every round trip
    # between them has to keep the size and the colors.
    image = Image.new("RGB", (3, 2), "red")
    back = to_pil(to_png(image))
    assert back.size == (3, 2)
    assert back.getpixel((0, 0)) == (255, 0, 0)


def test_the_bytes_carry_no_text_chunk():
    # mflux writes the prompt into a PNG it saves. This path never saves, so the
    # prompt must not travel inside the image it returns.
    meta = PngImagePlugin.PngInfo()
    meta.add_text("prompt", "a cat on a sofa")
    source = io.BytesIO()
    Image.new("RGB", (4, 4)).save(source, format="PNG", pnginfo=meta)
    assert b"a cat on a sofa" in source.getvalue()  # the input really carries it
    assert b"a cat on a sofa" not in to_png(to_pil(source.getvalue()))


def test_the_image_is_read_before_the_buffer_goes_away():
    # to_pil loads the pixels while its BytesIO is alive. Without the load, the
    # returned image is a lazy handle on a closed buffer, and the first pixel
    # read raises.
    image = Image.new("RGB", (8, 8), "blue")
    assert to_pil(to_png(image)).getpixel((4, 4)) == (0, 0, 255)
