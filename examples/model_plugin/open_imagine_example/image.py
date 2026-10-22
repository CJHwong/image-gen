"""Replace this CPU image maker with your model's lazy engine adapter."""

import struct
import zlib

from studio.plugins import ModelPlugin
from studio.plugins.image import Cancelled, Capabilities, Choice, ImageBackendGateway, ImageResult, ModeSpec, ParamSpec

CAPABILITIES = Capabilities(
    backend_id="example_image",
    name="Example Image",
    badge="CPU",
    max_batch=16,
    description="Plugin example: a solid-color PNG, without a trained model.",
    modes=(
        ModeSpec(
            "generate",
            "Generate",
            (
                ParamSpec("size", "choice", "256x256", choices=(Choice("256x256", "1:1"),)),
                ParamSpec("steps", "number", 1, minimum=1, maximum=1, integer=True),
                ParamSpec("guidance", "number", 1, minimum=1, maximum=1),
                ParamSpec("seed", "number", 7, minimum=0, maximum=2147483647, integer=True),
            ),
        ),
    ),
)


class ExampleImageGateway(ImageBackendGateway):
    def capabilities(self):
        return CAPABILITIES

    def load(self):
        pass

    def run(self, job, on_step, should_stop):
        if should_stop():
            raise Cancelled("Example Image stopped")
        width, height = map(int, str(job.options["size"]).split("x"))
        color = bytes((job.seed >> shift) % 200 + 30 for shift in (0, 8, 16))
        raw = (b"\0" + color * width) * height

        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 2, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
        on_step(1, 1)
        return ImageResult(png, width, height, job.seed, 1)

    def release(self):
        pass


plugin = ModelPlugin(CAPABILITIES, lambda context: ExampleImageGateway())
