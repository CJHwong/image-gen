from studio.l1_entities.video_capabilities import VideoCapabilities, VideoShape
from studio.l3_interface_adapters.gateways.prompt_aids import VIDEO_TEMPLATES


def ltx25_capabilities() -> VideoCapabilities:
    return VideoCapabilities(
        backend_id="ltx25",
        name="LTX-2.5",
        badge="24 fps",
        description="Local distilled video generation.",
        # The sizes the model renders, lowest first within each shape, and the form opens on
        # the first one: a prompt is tried before it is worth four minutes, and a small frame
        # is where that happens. Every rung here has rendered 121 frames on the office M5 Pro,
        # seconds each: 640x384 180, 768x448 267, 1024x576 431, 1280x704 491, 384x384 236,
        # 512x512 314, 768x768 365, 384x640 296, 448x768 365, 576x1024 462, 768x512 355,
        # 960x640 500, 1152x768 584, 512x768 343, 640x960 463 and 768x1152 603.
        #
        # A side is a multiple of the 64 pixel grid, so a small size cannot hold its shape
        # exactly: 640 x 384 is the wide shape at five to three, and the form prints the
        # pixels it will use under the field. 3:2 and 2:3 divide exactly, and use the same
        # numbers the image backends use for those shapes.
        shapes=(
            VideoShape("16:9", 640, 384),
            VideoShape("16:9", 768, 448),
            VideoShape("16:9", 1024, 576),
            VideoShape("16:9", 1280, 704),
            VideoShape("9:16", 384, 640),
            VideoShape("9:16", 448, 768),
            VideoShape("9:16", 576, 1024),
            VideoShape("1:1", 384, 384),
            VideoShape("1:1", 512, 512),
            VideoShape("1:1", 768, 768),
            VideoShape("3:2", 768, 512),
            VideoShape("3:2", 960, 640),
            VideoShape("3:2", 1152, 768),
            VideoShape("2:3", 512, 768),
            VideoShape("2:3", 640, 960),
            VideoShape("2:3", 768, 1152),
        ),
        default_shape_ratio="16:9",
        min_frames=9,
        max_frames=361,
        frame_step=8,
        duration_presets=(121, 241, 361),
        default_frames=121,
        frame_rate=24,
        max_references=8,
        min_reference_strength=0.05,
        max_reference_strength=1.0,
        reference_strength_step=0.05,
        default_reference_strength=1.0,
        min_seed=0,
        max_seed=2**32 - 1,
        min_dimension=256,
        max_dimension=1280,
        dimension_step=64,
        templates=VIDEO_TEMPLATES,
    )
