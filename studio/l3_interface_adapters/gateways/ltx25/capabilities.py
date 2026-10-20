from studio.l1_entities.video_capabilities import VideoAdapter, VideoCapabilities, VideoMode, VideoShape
from studio.l3_interface_adapters.gateways.prompt_aids import VIDEO_LOOKS, VIDEO_TEMPLATES

# The adapters. One at a time: each one's prompt is load-bearing (a trigger word, or the empty
# scene described rather than the thing to remove named), so two of them in one run would
# fight over the same box, and no pair has been measured.
#
# Every measured fact here came from one daylight clip of 97 frames at 768 x 448, seed 7,
# relit on the office M5 Pro:
#
#   day to night, two stages, stage 2 BARE:      the frame darkens 107.2 to 39.2 and the
#       buildings and street hold, but the market stall is gone and a parked car stands in
#       its place. The unconditioned second stage redraws what it likes.
#   day to night, two stages, stage 2 CONDITIONED: the stall, its umbrella and the street
#       furniture all survive, so --stage-2-ic-lora is what keeps the scene.
#
# The card's own recipe asks for 30 steps, guidance 3.0 to 4.0, STG and a negative prompt.
# The distilled pipeline we drive samples 8 sigmas at CFG 1.0 and takes no negative, so that
# half of the recipe is out of reach here and is not offered as a control.
#
# The whole set then ran that same clip that same way on 2026-10-19, each adapter on its own,
# at 768 x 448 and 97 frames, seed 7, through `ltx_pipelines.ic_lora` with --stage-2-ic-lora.
# Each output was judged at frame 40 against its own input, at 1:1 as well as whole:
#
#   water simulation: the road becomes a wet reflective sheet with the crossing showing
#       through standing water. The crowd, the buildings and the light hold.
#   clean plate: the pedestrians, the cyclist, the market stalls and the parked cars are gone,
#       and the road and pavement are rebuilt continuous, with the buildings and the light
#       intact.
#   deblur, decompression: this clip cannot judge either, because it is already sharp and
#       already clean, and each returned its input unchanged. Both were re-run against a clip
#       that carries its defect: soft.mp4, blurred at radius 6, and crushed.mp4, encoded at
#       150 kbps. The verdicts are in the adapters below.
#   colorization: this clip cannot judge it either, being already in colour. The re-run on
#       grey.mp4 added no colour with the second stage conditioned (mean chroma 0.00 in, 0.52
#       out), so the second stage was the suspect: an unconditioned stage 2 is not shown the
#       grey reference again, and that is the card's own recipe. It ran bare and still added
#       almost none, 2.96 mean chroma against 11.5 for a colour clip of the same scene, and the
#       frame is grey to the eye while the composition shifts under it. So it is not declared.
#   pixel spatial upscaler: no clip at all, exit 1. It is not declared, and the reason is in
#       the note under that name below.
#
# Four more official adapters ran on 2026-10-20, each on one degraded clip at 384 x 384 and
# 121 frames, seed 7, through the same in-context pipeline, judged against its own input:
#   restore 1.0: a clip scaled to half and back, sepia, blurred and noisy came back in colour
#       (saturation 17.8 to 36.3), with the crowd, the street and the torches in place and the
#       damage gone. It is declared.
#   colorization 0.9: a grey clip stayed grey, saturation 0.00 to 0.5, as the earlier run on
#       the other file did. Not declared.
#   refine-details 1.0: sharper edges on faces at 384, and the card's own gain is in its tiled
#       workflow, which this pipeline does not tile. Not declared yet.
#   pixel spatial upscaler 2x 1.0: 384 to 768 works and the detail is real at 1:1, so the grid
#       failure above was the 224 height, not the adapter. The form asks for the doubled shape
#       when this adapter is picked, so it is declared.
#
# A difference number does not judge an adapter. water simulation scores 17.03 mean absolute
# frame difference against its input and clean plate 19.06, but so does decompression at 14.53,
# and decompression changed nothing. The model re-renders every frame, so the floor is
# re-render noise, and only a concentrated blob in the difference map marks a real change.
# The verdicts above come from the crops.
DAY_TO_NIGHT_PROMPT = (
    "A realistic nighttime scene of the same place: deep blue moonlight, warm street lamps "
    "and lit shop windows, deep natural shadows. Only the lighting changes from day to "
    "night; identical composition, framing, camera movement and motion."
)

# Three of these cards name a literal trigger word, which is why the prompt starts with it and
# keeps it in capitals. The clean plate card wants the empty scene described instead, because
# naming the thing to remove is what the card warns against. Every prompt names the same shot
# and asks for one continuous take, since the reference carries the structure and the prompt
# carries the change.
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
# The restore card wants the clean capture described, because the damage comes from the
# reference and the words name what should replace it.
RESTORE_PROMPT = (
    "The same shot as a clean, colour, high-resolution capture: natural colour and skin "
    "tones, sharp detail, stable frames, no scratches, no dust, no flicker, no sepia cast. "
    "One continuous shot."
)
# The upscaler card gives no example prompt and names no trigger word: the reference carries
# the shot and the target size carries the work. The prompt only says what the detail should
# look like, so it names texture rather than a scene the model would redraw.
UPSCALE_PROMPT = (
    "The same shot at twice the width and height: crisp edges, fine texture and natural "
    "detail, no blur, no ringing. One continuous shot."
)

# Every adapter here ran with the second stage conditioned, and stage 2 conditions the same
# clip as stage 1, so the strength the card ships is the strength the form offers.
_ADAPTER_STRENGTH = 1.0

# The pixel spatial upscaler's own run died inside the video VAE encoder on a clip 224 pixels
# tall: the latent height is 7 and the down block splits it by 2, so the reference must sit on
# the 64 pixel grid and the target on the 128 pixel grid. The form now asks for a target at
# twice the clip's matched rung, and the controller accepts that doubled shape for this
# adapter only. A clip whose rung doubles past the model's 1280 pixel limit is refused by the
# form with the numbers, rather than dying in the pipeline.
VIDEO_ADAPTERS = (
    VideoAdapter(
        id="day-to-night",
        label="Day to night",
        hint="Relight a daylight clip as the same shot at night",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-day-to-night-0.9.safetensors",
        prompt=DAY_TO_NIGHT_PROMPT,
        strength=_ADAPTER_STRENGTH,
        stage_2_conditioning=True,
    ),
    VideoAdapter(
        id="water-simulation",
        label="Water simulation",
        hint="Flood the same shot: rain, standing water, splashes underfoot",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-water-simulation-0.9.safetensors",
        prompt=WATER_SIMULATION_PROMPT,
        strength=_ADAPTER_STRENGTH,
        stage_2_conditioning=True,
    ),
    VideoAdapter(
        id="clean-plate",
        label="Clean plate",
        hint="Empty the shot: people and vehicles gone, the place kept",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-clean-plate-1.0.safetensors",
        prompt=CLEAN_PLATE_PROMPT,
        strength=_ADAPTER_STRENGTH,
        stage_2_conditioning=True,
    ),
    VideoAdapter(
        id="deblur",
        label="Deblur",
        hint="Sharpen a soft or out of focus clip",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-deblur-0.9.safetensors",
        prompt=DEBLUR_PROMPT,
        strength=_ADAPTER_STRENGTH,
        stage_2_conditioning=True,
    ),
    VideoAdapter(
        id="decompression",
        label="Decompression",
        hint="Clean up a clip crushed by heavy compression",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-decompression-0.9.safetensors",
        prompt=DECOMPRESSION_PROMPT,
        strength=_ADAPTER_STRENGTH,
        stage_2_conditioning=True,
    ),
    # Sampled on 2026-10-20 against a clip degraded on purpose: scaled down to half and back,
    # sepia, blurred and noisy. The output returned colour (saturation 17.8 to 36.3) and
    # rebuilt the detail, with the crowd, the street and the torches in place. The card's
    # tiled ladder is not what we drive; the plain in-context pipeline is enough here.
    VideoAdapter(
        id="restore",
        label="Restore",
        hint="Clean up old or damaged footage: colour, sharpness, no noise",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-restore-1.0.safetensors",
        prompt=RESTORE_PROMPT,
        strength=_ADAPTER_STRENGTH,
        stage_2_conditioning=True,
    ),
    # Sampled on 2026-10-20 at 384 x 384, 121 frames, seed 7: the 384 clip came back at 768
    # with the cuts in place and texture the lanczos source does not carry. The pipeline runs
    # stage 1 at the reference's size and stage 2 at the target's, which is the card's own
    # half-resolution relationship.
    VideoAdapter(
        id="upscale-2x",
        label="Upscale 2x",
        hint="Render the same shot at twice the width and height",
        mode="edit",
        file="ltx-2.5-22b-ic-lora-pixel-spatial-upscaler-x2-1.0.safetensors",
        prompt=UPSCALE_PROMPT,
        strength=_ADAPTER_STRENGTH,
        stage_2_conditioning=True,
        doubles_output=True,
    ),
)


def ltx25_capabilities() -> VideoCapabilities:
    return VideoCapabilities(
        backend_id="ltx25",
        name="LTX-2.5",
        badge="24 fps",
        description="Local distilled video generation.",
        precision="bf16",
        # The sizes the model renders, lowest first within each shape, and the form opens on
        # the first one of the default shape: a prompt is tried before it is worth four
        # minutes, and a small frame is where that happens. Every rung here has rendered 121
        # frames on the office M5 Pro, seconds each: 640x384 180, 768x448 267, 1024x576 431,
        # 1280x704 491, 384x384 236, 512x512 314, 768x768 365, 384x640 296, 448x768 365,
        # 576x1024 462, 768x512 355, 960x640 500, 1152x768 584, 512x768 343, 640x960 463 and
        # 768x1152 603. The square leads the row because the image form opens on it, and the
        # default clip should be the shape the still it comes from usually is.
        #
        # A side is a multiple of the 64 pixel grid, so a small size cannot hold its shape
        # exactly: 640 x 384 is the wide shape at five to three, and the form prints the
        # pixels it will use under the field. 3:2 and 2:3 divide exactly, and use the same
        # numbers the image backends use for those shapes.
        shapes=(
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
        ),
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
            VideoMode(
                "edit",
                "Edit",
                needs_clip=True,
                min_references=0,
                max_references=0,
                prompt_label="What to change",
                placeholder="Pick an effect, then describe the change.",
                run_label="Edit clip",
            ),
        ),
        adapters=VIDEO_ADAPTERS,
    )
