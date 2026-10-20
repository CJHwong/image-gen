"""What the MLX q8 video packs offer the form.

Both packs are the same engine at 8 bits on Apple Silicon. A pack decides the model
version, and that is all: the modes, sizes, Looks and templates below are the ones a
person can choose, and every difference between the two models stays in the runner.
"""

from studio.l1_entities.video_capabilities import VideoCapabilities, VideoMode, VideoShape
from studio.l3_interface_adapters.gateways.prompt_aids import VIDEO_LOOKS, VIDEO_TEMPLATES

# The rungs the 22B model renders. Every side is a multiple of 64 and every shape follows
# the image form's own. Only 384 x 384 and 121 frames was timed on the q8 packs: 40.9 s from
# text on 2.5, 39.7 s on 2.3, and 45.1 s for a two keyframe run on 2.3. The remaining rungs
# are the model's declared sizes, not measurements of this engine.
SHAPES = (
    VideoShape("1:1", 384, 384),
    VideoShape("1:1", 512, 512),
    VideoShape("1:1", 768, 768),
    VideoShape("16:9", 640, 384),
    VideoShape("16:9", 768, 448),
    VideoShape("16:9", 1024, 576),
    VideoShape("16:9", 1280, 704),
    VideoShape("9:16", 384, 640),
    VideoShape("9:16", 448, 768),
    VideoShape("9:16", 576, 1024),
    VideoShape("3:2", 768, 512),
    VideoShape("3:2", 960, 640),
    VideoShape("3:2", 1152, 768),
    VideoShape("2:3", 512, 768),
    VideoShape("2:3", 640, 960),
    VideoShape("2:3", 768, 1152),
)


def _capabilities(backend_id: str, name: str) -> VideoCapabilities:
    return VideoCapabilities(
        backend_id=backend_id,
        name=name,
        badge="24 fps",
        description="Native MLX on Apple Silicon, 8-bit weights.",
        precision="int8",
        shapes=SHAPES,
        default_shape_ratio="1:1",
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
        # The port accepts any side on the 64 pixel grid; the form keeps its own bounds so a
        # typo cannot ask for a shape the model was never sampled at.
        min_dimension=256,
        max_dimension=1280,
        dimension_step=64,
        templates=VIDEO_TEMPLATES,
        modes=(
            VideoMode(
                "generate",
                "Generate",
                accepts_audio=True,
                looks=VIDEO_LOOKS,
                min_references=0,
                max_references=8,
                prompt_label="Prompt",
                placeholder="Describe how the subject should look and move.",
                run_label="Generate video",
            ),
        ),
    )


def ltx25_mlx_capabilities() -> VideoCapabilities:
    return _capabilities("ltx25_mlx", "LTX-2.5 q8")


def ltx23_mlx_capabilities() -> VideoCapabilities:
    return _capabilities("ltx23_mlx", "LTX-2.3 q8")
