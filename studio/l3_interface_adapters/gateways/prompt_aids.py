"""The Look rows and the prompt templates, shared by the backends.

They were tuned on Qwen-Image-2.1. Another model follows the same words
differently, so each backend offers only the options that passed a test on it:
pick_looks cuts the rows down to those. PROMPTS.md holds the tests. They sit
beside the adapters, not in the page, because the backend decides what it
offers. Each Look option adds one concrete
sentence after the prompt: concrete wording is what steers the model, and
quality words such as "4K" only darken the image. Each line says what to
show, never what to leave out.
"""

from collections.abc import Mapping

from studio.l1_entities.capabilities import LookRow, Template

GENERATE_TEMPLATES = (
    Template(
        "Portrait photo",
        "A person, with light and lens",
        "Close-up portrait photograph of [who: age, hair, look] in [place], at [time of day]. Wearing [clothing and colors], [pose or gaze], [expression]. [Light: direction and quality], [background, softly blurred]. 85mm lens at f/1.8, shallow depth of field, natural skin texture, [color mood].",
    ),
    Template(
        "Product shot",
        "An object on a surface, with space for copy",
        "Product photograph of [product: material, color, finish] on [surface] in [setting]. [Light: direction and quality], [one or two props] beside it. [Angle, e.g. three-quarter view at eye level], 85mm lens, empty space on the [side], [mood] mood.",
    ),
    Template(
        "Landscape",
        "A place, with the time and the view",
        "Wide photograph of [place] with [landmark] at [time of day and weather]. [A path, road or river] leads the eye from [where] toward [where]. [Sky and light]. Shot from [viewpoint], 24mm lens, deep focus, [detail] in the foreground, no text.",
    ),
    Template(
        "Poster with text",
        "Exact lettering, in any language",
        'Minimalist poster for [what]. At the top, a [lettering style] title "[title text]" in [color], with "[second line]" below it in [typeface style]. In the center, [main image]. At the bottom, the text "[small text]" in small [color] letters. [Background], generous empty space, centered layout, no other text.',
    ),
    Template(
        "Illustration",
        "A drawn or painted style",
        "[Medium, e.g. watercolor] illustration of [subject doing what] in [setting]. Palette of [3 or 4 colors], [line or brush quality], [light]. [Where the subject sits in the frame], [mood] mood, no text.",
    ),
)

EDIT_TEMPLATES = (
    Template(
        "Change a color or material",
        "One object, the rest untouched",
        "Change only the [object]'s [color or material] to [new color and finish], keeping its [shape, texture, details]. Do not change the background, the lighting or the camera angle.",
    ),
    Template(
        "Replace the background",
        "Keep the subject, move the scene",
        "Replace only the background with [new place, time, weather, 2 or 3 details]. Keep the [subject]'s face, expression, clothing, pose and framing exactly as they are, and match the light on the [subject] to the new scene.",
    ),
    Template(
        "Add text",
        "A sign, label or banner",
        'Add [a sign, label or banner] at [position] with the text "[exact text]" in [color, letter style, size], spelled exactly. Match the scene\'s lighting and perspective, and keep everything else unchanged.',
    ),
)

GENERATE_LOOKS = (
    LookRow(
        "Medium",
        options=(
            ("Film photo", "Shot on Kodak Portra 400 film, warm natural colors, fine grain."),
            (
                "Documentary",
                "Documentary photograph with natural exposure, physically plausible light, accurate shadows and reflections, realistic skin and material texture, subtle sensor noise.",
            ),
            (
                "Phone snapshot",
                "Unedited phone photo straight out of the camera, candid and unposed, imperfect framing, uneven everyday light.",
            ),
            ("Watercolor", "Watercolor painting on textured paper, soft washes, visible brush edges."),
            ("Ink drawing", "Black ink drawing with fine linework and cross-hatching on white paper."),
            ("3D render", "Stylized 3D animated character, smooth rounded shapes, soft studio light."),
        ),
    ),
    LookRow(
        "Light",
        options=(
            ("Soft window light", "Soft daylight from a window on the left, gentle shadows."),
            ("Golden hour", "Warm low sun from the side, long shadows."),
            ("Studio", "Clean, even studio lighting against a plain seamless backdrop."),
            ("Overcast", "Overcast sky, soft diffuse light, gentle shadows."),
            ("Night with neon", "At night, lit by colored neon signs, reflections on wet surfaces."),
        ),
    ),
    LookRow(
        "Camera",
        options=(
            ("Close-up 85mm", "Close-up, 85mm lens at f/1.8, shallow depth of field."),
            ("Wide 24mm", "Wide shot, 24mm lens, deep focus."),
            ("Top-down", "Shot from directly above."),
            ("Low angle", "Low angle, looking up at the subject."),
        ),
    ),
    LookRow(
        "Color",
        options=(
            ("Warm", "Warm palette of amber, cream and brown."),
            ("Cool", "Cool palette of blue, teal and grey."),
            ("Muted", "Muted, desaturated colors."),
            ("Vivid", "Rich, deep, saturated colors."),
            ("Black and white", "Black and white photograph on Kodak Tri-X 400 film, strong grain, high contrast."),
        ),
    ),
    LookRow(
        "Room for text",
        options=(
            ("Left", "Subject on the right third, empty space on the left."),
            ("Right", "Subject on the left third, empty space on the right."),
            ("Top", "Subject in the bottom third, a wide plain empty area across the top of the frame."),
        ),
    ),
)


def pick_looks(picks: Mapping[str, tuple[str, ...]], sentences: Mapping[str, str] | None = None) -> tuple[LookRow, ...]:
    """The rows named in `picks`, each cut to the named options, in the shared order.

    `sentences` replaces the sentence of an option by its name, for a model that
    reads the shared wording in a way the option does not mean. A name that
    matches nothing raises, so a typo cannot drop an option without a word.
    """
    rows = {row.name: row for row in GENERATE_LOOKS}
    unknown = [name for name in picks if name not in rows]
    unknown += [
        option for name in picks if name in rows for option in picks[name] if option not in dict(rows[name].options)
    ]
    if unknown:
        raise ValueError(f"no Look named {', '.join(unknown)}")
    replaced = sentences or {}
    return tuple(
        LookRow(
            row.name, tuple((name, replaced.get(name, text)) for name, text in row.options if name in picks[row.name])
        )
        for row in GENERATE_LOOKS
        if row.name in picks
    )
