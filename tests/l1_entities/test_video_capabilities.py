from dataclasses import asdict, replace

import pytest

from studio.l1_entities.errors import UnsupportedMode
from studio.l1_entities.video_capabilities import VideoAdapter, VideoCapabilities, VideoMode, VideoShape
from tests.support.fakes import fake_video_capabilities


def capabilities():
    return VideoCapabilities(
        backend_id="demo",
        name="Demo video",
        badge="24 fps",
        description="A local video model.",
        shapes=(VideoShape("16:9", 960, 544), VideoShape("1:1", 768, 768)),
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
        dimension_step=32,
    )


def test_video_capabilities_are_plain_data_for_the_page_and_controller():
    record = asdict(capabilities())

    assert record["backend_id"] == "demo"
    assert record["default_shape_ratio"] == "16:9"
    assert record["shapes"] == (
        {"ratio": "16:9", "width": 960, "height": 544},
        {"ratio": "1:1", "width": 768, "height": 768},
    )
    assert (record["min_frames"], record["max_frames"], record["frame_step"]) == (9, 361, 8)
    assert record["duration_presets"] == (121, 241, 361)
    assert (record["min_seed"], record["max_seed"]) == (0, 2**32 - 1)
    assert (
        record["min_reference_strength"],
        record["max_reference_strength"],
        record["reference_strength_step"],
        record["default_reference_strength"],
    ) == (0.05, 1.0, 0.05, 1.0)


def test_a_backend_with_no_modes_has_one_and_it_draws():
    """Every video backend before this one had a single way of working, and the form still
    draws that: no mode switch, no adapter picker, the run it always made."""
    capabilities = fake_video_capabilities()

    assert capabilities.modes == ()
    assert capabilities.mode("generate").label == "Generate"
    assert capabilities.mode("anything").needs_clip is False
    assert capabilities.adapters_for("edit") == ()


def test_a_mode_is_looked_up_by_id_and_an_unknown_one_is_refused():
    capabilities = replace(
        fake_video_capabilities(),
        modes=(VideoMode("edit", "Edit", needs_clip=True),),
    )

    with pytest.raises(UnsupportedMode, match="no generate mode"):
        capabilities.mode("generate")


def test_the_adapters_a_mode_offers_are_the_ones_declared_for_it():
    capabilities = replace(
        fake_video_capabilities(),
        adapters=(
            VideoAdapter("relight", "Relight", "hint", "edit", "relight.safetensors"),
            VideoAdapter("loop", "Loop", "hint", "generate", "loop.safetensors"),
        ),
    )

    assert [adapter.id for adapter in capabilities.adapters_for("edit")] == ["relight"]
    assert [adapter.id for adapter in capabilities.adapters_for("generate")] == ["loop"]


def test_an_adapter_declared_impossibly_is_refused_at_declaration():
    """A mode is generate or edit, a prompt is read, optional or refused, and an adapter that
    refuses a prompt cannot carry one: the page would otherwise offer a box the run rejects."""
    settled = VideoAdapter("x", "X", "hint", "edit", "x.safetensors")

    with pytest.raises(ValueError):
        replace(settled, mode="restore")
    with pytest.raises(ValueError):
        replace(settled, prompt_mode="sometimes")
    with pytest.raises(ValueError):
        replace(settled, prompt_mode="empty", prompt="say something")
