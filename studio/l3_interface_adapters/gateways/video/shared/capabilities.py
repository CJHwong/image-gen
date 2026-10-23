"""What the MLX q8 video packs offer the form.

Both packs use the same engine at 8 bits on Apple Silicon. Each pack declares its
measured prompt aids and modes here.
"""

from studio.l1_entities.capabilities import Template
from studio.l1_entities.video_capabilities import VideoAdapter, VideoCapabilities, VideoMode, VideoShape
from studio.l3_interface_adapters.gateways.prompt_aids import VIDEO_LOOKS, VIDEO_TEMPLATES

# These three first fills reproduce the API probes from 2026-10-20. The sideways and
# orbit probes also moved forward, so they do not earn separate templates.
_CAMERA_SCENE = (
    "[Subject] rests on [surface]. [Foreground object] stands closer to the camera, "
    "and [background object] stands behind [subject name]. [light]. "
)
LTX25_TEMPLATES = (
    *VIDEO_TEMPLATES,
    Template(
        "Speak to camera",
        "One speaker, quoted words, fixed camera",
        "A front-facing medium close-up shows [speaker] against [background]. [light]. "
        '[Subject pronoun] looks into the lens and clearly says in [language], "[dialogue]" '
        "[Possessive pronoun] lips and jaw move naturally with each word. "
        "The camera stays fixed throughout the continuous shot. "
        "[Possessive pronoun] voice is clear over [sound].",
    ),
    Template(
        "Fixed composition",
        "A still subject with a fixed camera",
        _CAMERA_SCENE + "The camera stays fixed, holding the same composition. One continuous shot with [sound].",
    ),
    Template(
        "Slow push-in",
        "Move closer while the subject stays still",
        _CAMERA_SCENE
        + "The camera slowly moves toward [subject name], ending in a closer view while [subject name] stays still. "
        "One continuous shot with [sound].",
    ),
)

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
    VideoShape("16:9", 1920, 1088),
    VideoShape("9:16", 384, 640),
    VideoShape("9:16", 448, 768),
    VideoShape("9:16", 576, 1024),
    VideoShape("9:16", 1088, 1920),
    VideoShape("3:2", 768, 512),
    VideoShape("3:2", 960, 640),
    VideoShape("3:2", 1152, 768),
    VideoShape("2:3", 512, 768),
    VideoShape("2:3", 640, 960),
    VideoShape("2:3", 768, 1152),
)


# Existing effects retain their measured single-stage recipes (2026-10-20).
# Layout to Render uses its own two-stage recipe. Its earlier mosaic was traced
# to the port silently leaving its upscaler untrained when v1_1 was absent;
# the dedicated child requires the LTX-2.5 pack's v1_0 weights (2026-10-23).
DAY_TO_NIGHT_PROMPT = (
    "A realistic nighttime scene of the same place: deep blue moonlight, warm street lamps "
    "and lit shop windows, deep natural shadows. Only the lighting changes from day to "
    "night; identical composition, framing, camera movement and motion."
)
WATER_SIMULATION_PROMPT = (
    "ADD WATER. A sudden downpour floods the same shot, water running along every surface and "
    "splashing underfoot, the same composition and the same subjects. One continuous shot."
)
CLEAN_PLATE_PROMPT = (
    "The same shot with nobody in it: the place empty, the same setting and the same light, "
    "with the people, the animals and the vehicles gone. One continuous shot."
)
DEBLUR_PROMPT = (
    "DEBLUR. The same shot, sharp and in focus, every edge crisp and the texture of each "
    "surface visible. One continuous shot."
)
DECOMPRESSION_PROMPT = (
    "ENHANCE QUALITY. The same shot with clean edges, no blocking or banding, honest colour. One continuous shot."
)
RESTORE_PROMPT = (
    "The same shot as a clean, colour, high-resolution capture: natural colour and skin "
    "tones, sharp detail, stable frames, no scratches, no dust, no flicker, no sepia cast. "
    "One continuous shot."
)
UPSCALE_PROMPT = (
    "The same shot at twice the width and height: crisp edges, fine texture and natural "
    "detail, no blur, no ringing. One continuous shot."
)

VIDEO_ADAPTERS = (
    VideoAdapter(
        id="custom",
        label="Custom",
        hint="No LoRA: experimental clip conditioning with your own prompt; source fidelity may vary",
        mode="edit",
        file="",
        min_strength=1.0,
        max_strength=1.0,
    ),
    VideoAdapter(
        id="layout-to-render",
        label="Layout to Render",
        hint="Turn a layout animation into a finished shot. Add a look image made from its first frame; describe the finished materials and lighting.",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-layout-to-render-1.0.safetensors",
        stage_2_conditioning=True,
        min_references=1,
        max_references=1,
        reference_frame_index=0,
        card="Layout-To-Render",
    ),
    VideoAdapter(
        id="day-to-night",
        label="Day to night",
        hint="Relight a daylight clip as the same shot at night",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-day-to-night-0.9.safetensors",
        prompt=DAY_TO_NIGHT_PROMPT,
        width=768,
        height=448,
        num_frames=97,
        card="Day-To-Night",
    ),
    VideoAdapter(
        id="water-simulation",
        label="Water simulation",
        hint="Flood the same shot: rain, standing water, splashes underfoot",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-water-simulation-0.9.safetensors",
        prompt=WATER_SIMULATION_PROMPT,
        # The card's production size is 1920 x 1088. This pair is the one measured: at
        # 1280 x 704 a daylight room floods, the floor becomes water and the splash shows at
        # the feet. At 960 x 544, the card's dev-base validation size, no water appeared
        # (2026-10-20). At 1920 x 1088 the single-stage path runs out of Metal memory on a
        # 64 GB Mac, so the shipped pair is the largest that fits.
        width=1280,
        height=704,
        num_frames=97,
        card="Water-Simulation",
    ),
    VideoAdapter(
        id="clean-plate",
        label="Clean plate",
        hint="Empty the shot: people and vehicles gone, the place kept",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-clean-plate-1.0.safetensors",
        prompt=CLEAN_PLATE_PROMPT,
        width=1024,
        height=576,
        num_frames=49,
        card="Clean-Plate",
    ),
    VideoAdapter(
        id="deblur",
        label="Deblur",
        hint="Sharpen a soft or out of focus clip",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-deblur-0.9.safetensors",
        prompt=DEBLUR_PROMPT,
        width=960,
        height=544,
        num_frames=121,
        card="Deblur",
    ),
    VideoAdapter(
        id="decompression",
        label="Decompression",
        hint="Clean up a clip crushed by heavy compression",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-decompression-0.9.safetensors",
        prompt=DECOMPRESSION_PROMPT,
        width=960,
        height=544,
        num_frames=121,
        card="Decompression",
    ),
    VideoAdapter(
        id="restore",
        label="Restore",
        hint="Clean up old or damaged footage: colour, sharpness, no noise",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-restore-1.0.safetensors",
        prompt=RESTORE_PROMPT,
        width=960,
        height=544,
        num_frames=97,
        card="Restore",
    ),
    VideoAdapter(
        id="upscale-2x",
        label="Upscale 2x",
        hint="Render the same shot at twice the width and height",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors",
        prompt=UPSCALE_PROMPT,
        doubles_output=True,
        card="Pixel-Spatial-Upscaler",
    ),
)


def _capabilities(backend_id: str, name: str, edit: bool = False) -> VideoCapabilities:
    generate = VideoMode(
        "generate",
        "Generate",
        accepts_audio=True,
        looks=VIDEO_LOOKS,
        min_references=0,
        max_references=8,
        prompt_label="Prompt",
        placeholder="Describe how the subject should look and move.",
        run_label="Generate video",
    )
    edit_mode = VideoMode(
        "edit",
        "Edit",
        needs_clip=True,
        min_references=0,
        max_references=0,
        prompt_label="What to change",
        placeholder="Pick an effect, then describe the change.",
        run_label="Edit clip",
    )
    return VideoCapabilities(
        backend_id=backend_id,
        name=name,
        badge="24 fps",
        description="Native MLX on Apple Silicon, 8-bit weights.",
        precision="int8",
        fast_mode=backend_id == "ltx25_mlx",
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
        # 1080p class. Measured on the office M5 Pro: a 1920 x 1088 generate of 97 frames
        # took 790 s on 2.5 q8 and stayed inside 64 GB, on the distilled two-stage path.
        max_dimension=1920,
        dimension_step=64,
        templates=LTX25_TEMPLATES if backend_id == "ltx25_mlx" else VIDEO_TEMPLATES,
        modes=(generate, edit_mode) if edit else (generate,),
        adapters=VIDEO_ADAPTERS if edit else (),
    )


def ltx25_mlx_capabilities() -> VideoCapabilities:
    return _capabilities("ltx25_mlx", "LTX-2.5", edit=True)


def ltx23_mlx_capabilities() -> VideoCapabilities:
    return _capabilities("ltx23_mlx", "LTX-2.3")
