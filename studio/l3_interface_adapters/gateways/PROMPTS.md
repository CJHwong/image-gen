# Prompts

The templates and the Look were written and tested on Qwen-Image-2.1. FLUX.2 offers the part that passed its own test, in [The flux2 test](#the-flux2-test).

Qwen-Image-2.1 makes a good image from a short prompt. A longer prompt does not make it better. It gives you control over what you get. The templates below give that control with the least typing.

In the page, open **Templates** above the prompt. Pick one, then press Tab to jump from one `[placeholder]` to the next. The run button stays off until no `[bracket]` is left.

## What works

- **Name what you can see.** Use concrete nouns, named colors and materials, and the clothing. "A yellow oilskin jacket" lands. "Weathered" only partly lands.
- **Say where the light comes from.** "Soft light from the left, cool shadows" steers the image more than any quality word.
- **Give the camera.** A lens and a viewpoint, such as "85mm at f/1.8" or "shot from a high rim looking down", fix the framing.
- **Place things in the frame.** "Empty space on the left" and "subject on the right third" are followed.
- **Name the mood you want.** Mood words steer hard. "Minimal, neutral, catalog" gives a flat, plain image. Use it only when you want that.
- **Put text in double quotes.** Then say where the text goes and how big it is, and end with "no other text". This works in Traditional Chinese and English. Text without quotes gets misspelled, and fake glyphs appear around it.
- **Check Chinese titles in a hand-lettered style.** In one test, 麥田烘焙 came out with the Simplified 麦. The same poster's small printed 盛大開幕 was correct. If a glyph drifts, try a printed style or another seed.
- **Expect small details to drop.** A small prop far from the subject, such as a kayak on a river, may not appear. Put what matters near the subject or make it bigger.

## What to leave out

- **Quality suffixes** such as "Ultra HD, 4K, cinematic composition". They do not add quality. They make the image darker and more dramatic, and they change the framing.
- **A negative prompt.** It needs guidance above 1, which doubles the time per step. In the test, it gave little or no visible gain.

## Look

In the page, **Look** adds one sentence after your prompt when you press Generate. The prompt field keeps your own text. Pick at most one option per row.

| Row | Options | What it adds |
|---|---|---|
| Medium | Film photo, Documentary, Phone snapshot, Watercolor, Ink drawing, 3D render | A film stock, a camera habit, or a drawn or rendered style |
| Light | Soft window light, Golden hour, Studio, Overcast, Night with neon | Where the light comes from and how hard it is |
| Camera | Close-up 85mm, Wide 24mm, Top-down, Low angle | A lens and a viewpoint |
| Color | Warm, Cool, Muted, Vivid, Black and white | A palette |
| Room for text | Left, Right, Top | Where the subject sits, and which side stays empty |

Each option names what to show, never what to leave out. Edit mode has no Look, because the edit model already keeps the rest of the image.

## Generate templates

**Portrait photo**

```
Close-up portrait photograph of [who: age, hair, look] in [place], at [time of day]. Wearing [clothing and colors], [pose or gaze], [expression]. [Light: direction and quality], [background, softly blurred]. 85mm lens at f/1.8, shallow depth of field, natural skin texture, [color mood].
```

**Product shot**

```
Product photograph of [product: material, color, finish] on [surface] in [setting]. [Light: direction and quality], [one or two props] beside it. [Angle, e.g. three-quarter view at eye level], 85mm lens, empty space on the [side], [mood] mood.
```

**Landscape**

```
Wide photograph of [place] with [landmark] at [time of day and weather]. [A path, road or river] leads the eye from [where] toward [where]. [Sky and light]. Shot from [viewpoint], 24mm lens, deep focus, [detail] in the foreground, no text.
```

**Poster with text**

```
Minimalist poster for [what]. At the top, a [lettering style] title "[title text]" in [color], with "[second line]" below it in [typeface style]. In the center, [main image]. At the bottom, the text "[small text]" in small [color] letters. [Background], generous empty space, centered layout, no other text.
```

**Illustration**

```
[Medium, e.g. watercolor] illustration of [subject doing what] in [setting]. Palette of [3 or 4 colors], [line or brush quality], [light]. [Where the subject sits in the frame], [mood] mood, no text.
```

## Edit templates

The edit model keeps the rest of the image by itself. The prompt only has to name the exact target and the exact result.

**Change a color or material**

```
Change only the [object]'s [color or material] to [new color and finish], keeping its [shape, texture, details]. Do not change the background, the lighting or the camera angle.
```

**Replace the background**

```
Replace only the background with [new place, time, weather, 2 or 3 details]. Keep the [subject]'s face, expression, clothing, pose and framing exactly as they are, and match the light on the [subject] to the new scene.
```

**Add text**

```
Add [a sign, label or banner] at [position] with the text "[exact text]" in [color, letter style, size], spelled exactly. Match the scene's lighting and perspective, and keep everything else unchanged.
```

## How these were tested

All runs used 20 steps and seeds 1234 and 5678. Generate ran at 1024 x 1024 with guidance 1.0. Edit ran at 768 with true CFG 1.0.

Each of four subjects (a portrait, a product, a landscape and a poster) ran at four prompt levels. The levels were one short phrase, one sentence, a full description, and a full description with extra detail. Two variants were added: the sentence plus a quality suffix, and the detailed prompt plus a negative prompt at guidance 2.5. Each edit task (recolor, new background, add text) ran at three levels, from a short request to a precise one.

| Finding | Evidence |
|---|---|
| Base quality is high at every level | The one-phrase portrait was already photographic and well lit. |
| Detail buys control | The full description got the cap color, the jacket, the gaze, the mist and the light side right. The sentence did not. |
| Quotes make text exact | Unquoted: "Camellie Tea House", plus fake glyphs. Quoted, with a position: "山茶小館", "Camellia Tea House", "新品上市 New Arrivals" exact on both seeds. |
| The suffix changes the look | With the suffix, one portrait became a wide seated shot, and the product shot went dark and moody. |
| The negative prompt is not worth it | 157 to 161 s per image against 64 to 84 s, for a near-identical result. |
| The templates hold up | Each template ran with two different fill-ins at one seed. All 16 images followed their slots. Text was exact except one Simplified glyph in a hand-lettered title. |
| Edit text needs a position and a size | "Add a sign" gave "WELCOME" and, on one seed, a garbage second line. Without a size, the sign was too small to read. The precise request gave a legible "Welcome to Alpbach" on both seeds. |

### The Look test

Every Look option was added to "a cat wearing a suit" at 768 x 768, 20 steps, guidance 1.0, on seeds 1234 and 5678, next to the bare prompt. Edit options ran on two edits: a new background, and adding a dog. An option stayed only if it changed the image in the way its name says.

| Finding | Evidence |
|---|---|
| "Photo" did nothing | The bare prompt already gave a photograph. The option was cut. |
| The Keep row and "Match the new scene" and "Blend into the photo" did nothing | Both edits kept the face, pose, light and framing without them. The edit Look was cut. |
| "Studio softbox" put the softbox in the picture | Both seeds showed the light stand. "Clean, even studio lighting against a plain seamless backdrop" did not. |
| "3D render" worked on one seed | "Stylized 3D animated character, smooth rounded shapes, soft studio light" worked on both. |
| "Vivid, saturated colors" went pop art | "Rich, deep, saturated colors" kept the photograph. |
| "Top" is weak | Seed 1234 kept the head near the top with both wordings. Seed 5678 left the top empty. |
| Light options widen the shot | Most Light options pulled the camera back from a close-up to a full body. Add a Camera option to hold the framing. |
| Kodak film stocks land | "Kodak Portra 400" gave warm color and fine grain. "Kodak Tri-X 400" gave a grainy, high-contrast black and white. |

### The flux2 test

A sample, not every option: the options most likely to behave differently on FLUX.2 klein-base-9B. The runs used "a cat wearing a suit" at 768 x 768, 20 steps, guidance 4, int8, seed 1234, next to the bare prompt. Each template ran with its first fill-in.

| Option | Result on flux2 |
|---|---|
| Medium: Film photo, Watercolor, 3D render | All three work. 3D render turns the subject into a vinyl toy, which is still a 3D render. |
| Light: Studio | Works: a plain white studio. |
| Light: Night with neon | Works, but dark: the subject is hard to see. |
| Camera: Wide 24mm, Top-down | Both work. |
| Color: Vivid | Works. |
| Color: Black and white | The shared sentence names "Kodak Tri-X 400", and flux2 printed that name on a film frame. The flux2 sentence, "Black and white film photograph, strong grain, high contrast.", names no film. On the same seed it kept the grain and the contrast, with no frame and no text. |
| Room for text: Left, Top | Both work. Top is stronger than on qwen21. |
| The 5 generate templates | All work. The poster text came out exact. |
| The 3 edit templates | All work: the recolor, the new background and the added sign. |

The other 13 Look options were not tested on flux2, so flux2 does not offer them.
