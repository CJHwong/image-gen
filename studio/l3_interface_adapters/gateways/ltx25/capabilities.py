from studio.l1_entities.video_capabilities import VideoCapabilities, VideoShape


def ltx25_capabilities() -> VideoCapabilities:
    return VideoCapabilities(
        backend_id="ltx25",
        name="LTX-2.5",
        badge="24 fps",
        description="Local distilled video generation.",
        shapes=(
            VideoShape("16:9", 960, 544),
            VideoShape("9:16", 544, 960),
            VideoShape("1:1", 768, 768),
        ),
        min_frames=9,
        max_frames=361,
        frame_step=8,
        default_frames=121,
        frame_rate=24,
        max_references=8,
        min_dimension=256,
        max_dimension=1280,
        dimension_step=32,
    )
