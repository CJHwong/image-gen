from dataclasses import asdict

from studio.l1_entities.video_capabilities import VideoCapabilities, VideoShape


def capabilities():
    return VideoCapabilities(
        backend_id="demo",
        name="Demo video",
        badge="24 fps",
        description="A local video model.",
        shapes=(VideoShape("16:9", 960, 544), VideoShape("1:1", 768, 768)),
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


def test_video_capabilities_are_plain_data_for_the_page_and_controller():
    record = asdict(capabilities())

    assert record["backend_id"] == "demo"
    assert record["shapes"] == (
        {"ratio": "16:9", "width": 960, "height": 544},
        {"ratio": "1:1", "width": 768, "height": 768},
    )
    assert (record["min_frames"], record["max_frames"], record["frame_step"]) == (9, 361, 8)
