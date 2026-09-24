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
- **A negative prompt.** It needs guidance above 1, which doubles the time per step. In the test, it gave little or no visible gain. The one exception is the Realism avoid part: see "The avoid-part test".

## Look

In the page, **Look** adds one sentence after your prompt when you press Generate. The prompt field keeps your own text. Pick at most one option per row.

| Row | Options | What it adds |
|---|---|---|
| Medium | Documentary, Phone snapshot, Watercolor, Ink drawing, 3D render | A camera habit, or a drawn or rendered style |
| Film | Portra 400, Fuji 400H, Ektachrome, Black and white | A film stock and its color |
| Color | Warm, Cool, Muted, Vivid | A palette |
| Light | Soft window light, Golden hour, Studio, Overcast, Night with neon | Where the light comes from and how hard it is |
| Camera | Close-up 85mm, Wide 24mm, Top-down, Low angle, Telephoto, Deep focus | A lens and a viewpoint |
| Room for text | Left, Right, Top | Where the subject sits, and which side stays empty |
| Realism | Real person | An everyday, unretouched person, plus an avoid part for the negative prompt |
| Portrait | Over the shoulder, Candid glance | A pose and a gaze |

The rows go from the style (Medium, Film, Color) to the shot (Light, Camera, Room for text) to the subject (Realism, Portrait). Every film stock sits in the Film row, so one pick per row keeps two stocks from fighting. Portra 400 was "Film photo" in Medium, and Black and white was in Color; their sentences did not change.

Each option names what to show, never what to leave out. The exception is Real person: its avoid part goes to the negative prompt, which raises guidance to 2.5 and doubles the time of each image. Realism fights Watercolor, Ink drawing and 3D render, because its avoid part names CGI and 3D render. Real person is for people. For an animal, Documentary is enough: see "The avoid-part test". Edit mode has no Look, because the edit model already keeps the rest of the image.

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

**Deadpan absurdity** (qwen21 only)

```
A realistic candid photograph of a completely ordinary [place] on [a weekday and time], except [one absurd thing] is calmly [doing what] beside [where]. The people carry on as if nothing unusual is happening. [3 or 4 everyday details], [ordinary light]. Shot with a 28mm lens at eye level, natural perspective, documentary photojournalism.
```

**Banner** (qwen21 only)

```
A 16:9 [kind, e.g. video thumbnail or ad banner] on [background and colors]. [Person or product: who, clothing, pose] on the [side]. On the [other side], huge [color] [letter style, e.g. extra-bold gothic] text reads "[headline]", and below it, smaller text reads "[second line]". [A button, badge or band] reads "[short label]". [Mood].
```

Keep each line short, and check every character. One dropped or swapped kanji is common, most often in the smaller lines. A batch of several seeds gives you a clean one to pick.

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

**Alternate reality** (qwen21 only)

```
Keep the camera position, the composition, the people and their poses exactly unchanged. Change only [which part of the world]: [the new reality, with 1 or 2 visible details]. Preserve the lighting, the lens and the photographic texture.
```

**Add an object** (qwen21 only)

```
Add [object or animal] [where, and how it touches the scene], [one person reacting to it]. Give it correct scale, shadows and floor contact. Do not change [what must stay], the lighting or the camera position.
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

### The avoid-part test

An avoid part is a list for the negative prompt that comes with a Look option. The test asked whether the avoid text itself helps, apart from the second pass it turns on. On qwen21, guidance 2.5 with a blank negative gives the same image and time as guidance 1: true CFG runs only for a set negative. So each option ran twice at guidance 2.5, with the neutral negative "low quality" and with its avoid part. The subject was "a woman in her thirties reading at a cafe window", at 768 x 768 and 20 steps. Options without an avoid part ran at guidance 1 next to the bare prompt. The candidates came from the image-prompt-curator skill.

| Option | Result |
|---|---|
| Realism, Medium tier ("Real person") | Works on seeds 1234, 5678 and 9012. With the neutral negative, each image was a posed, smooth beauty portrait. With the avoid part, each was a plain, candid person. |
| Realism, Light and Full tiers | Cut. Light gained little: both images stayed polished. Full looked more real but put a glass artifact in the foreground. |
| Studio, avoiding light stands | Cut. The neutral negative and the avoid part gave nearly the same image. |
| Room for text Top, avoiding the top edge | Cut. The avoid part made the head bigger and higher. |
| Candid glance | Kept without an avoid part. The gaze was off camera with either negative. |
| Deep focus | Kept without an avoid part. The avoid part was a little crisper, not enough to double the time. |
| Three-quarter | Kept as "Over the shoulder", which is what the sentence gave: the person turned away and looked back. |
| Telephoto, Fuji 400H, Ektachrome | Kept. Each changed the image as its name says. |

These ran on one seed each, except Real person. They were not tested on flux2.

A Real animal option was tested and not added. Its sentence asked for uneven fur, a wet nose, dust and a natural, unposed posture, with the eyes off the camera. It ran after Documentary on a dog and a horse, on seeds 1234 and 5678, at guidance 1. Documentary alone already gave four believable phone photos. The sentence made the coats a little rougher, but the animals mostly still looked at the camera, and it changed the dog's bowl on one seed.

### The template test

Each template ran once with its first fill-in, at 768 x 768, 20 steps and seed 1234. The edit templates changed a generated source image. The banner test ran 8 prompts from a Japanese banner gallery at 1280 x 720, 40 steps, guidance 1 and seed 1234, each next to the gallery's own image.

| Template | Result |
|---|---|
| Deadpan absurdity | Works: a horse stands in an ordinary office, and nobody reacts. |
| Alternate reality | Works: the office windows show Earth from a space station, and the people and the light stay the same. |
| Add an object | Works: a cow stands at the second desk with a shadow and floor contact, and the rest is unchanged. |
| Relighting (turn the rain into a downpour) | Cut. It added only rain streaks: the mean pixel change was 12.6 out of 255. |
| Era swap (1980s street to today) | Cut. The image came back almost unchanged. |
| Banner, the gallery's prompts word for word | Fails. The prompts are forms with labels such as "Main:" and hex colors, and the model drew the labels and the colors as text. Small, dense lines were garbled. No banner came out clean. |
| Banner, rewritten as prose | Works with short copy. At most 3 quoted lines, each with its place and size: 14 of 21 lines came out exact, and 3 of 8 banners were fully clean. Each error was one dropped or swapped character. The layouts followed the brief. |

In the prose banners, the quoted lines were Japanese and the rest of each prompt was English.

### The flux2 test

A sample, not every option: the options most likely to behave differently on FLUX.2 klein-base-9B. The runs used "a cat wearing a suit" at 768 x 768, 20 steps, guidance 4, int8, seed 1234, next to the bare prompt. Each template ran with its first fill-in.

| Option | Result on flux2 |
|---|---|
| Medium: Film photo (now Film: Portra 400), Watercolor, 3D render | All three work. 3D render turns the subject into a vinyl toy, which is still a 3D render. |
| Light: Studio | Works: a plain white studio. |
| Light: Night with neon | Works, but dark: the subject is hard to see. |
| Camera: Wide 24mm, Top-down | Both work. |
| Color: Vivid | Works. |
| Color: Black and white (now in the Film row) | The shared sentence names "Kodak Tri-X 400", and flux2 printed that name on a film frame. The flux2 sentence, "Black and white film photograph, strong grain, high contrast.", names no film. On the same seed it kept the grain and the contrast, with no frame and no text. |
| Room for text: Left, Top | Both work. Top is stronger than on qwen21. |
| The 5 generate templates | All work. The poster text came out exact. |
| The 3 edit templates | All work: the recolor, the new background and the added sign. |
| Deadpan absurdity, Banner, Alternate reality, Add an object | Not tested on flux2, so flux2 does not offer them. |

The other 19 Look options were not tested on flux2, so flux2 does not offer them.
