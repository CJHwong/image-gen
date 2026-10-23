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
| Medium | Documentary, Phone snapshot, Watercolor, Ink drawing, 3D render, Skeleton (qwen21 only) | A camera habit, or a drawn or rendered style |
| Film | Portra 400, Fuji 400H, Ektachrome, Black and white | A film stock and its color |
| Color | Warm, Cool, Muted, Vivid | A palette |
| Light | Soft window light, Golden hour, Studio, Overcast, Night with neon | Where the light comes from and how hard it is |
| Camera | Close-up 85mm, Wide 24mm, Top-down, Low angle, Telephoto, Deep focus | A lens and a viewpoint |
| Room for text | Left, Right, Top | Where the subject sits, and which side stays empty |
| Realism | Real person | An everyday, unretouched person, plus an avoid part for the negative prompt |
| Portrait | Over the shoulder, Candid glance | A pose and a gaze |

The rows go from the style (Medium, Film, Color) to the shot (Light, Camera, Room for text) to the subject (Realism, Portrait). Every film stock sits in the Film row, so one pick per row keeps two stocks from fighting. Portra 400 was "Film photo" in Medium, and Black and white was in Color; their sentences did not change.

Each option names what to show, never what to leave out. The exception is Real person: its avoid part goes to the negative prompt, which raises guidance to 2.5 and doubles the time of each image. Realism fights Watercolor, Ink drawing, 3D render and Skeleton, because its avoid part names CGI and 3D render. Real person is for people. For an animal, Documentary is enough: see "The avoid-part test". These are the rows for a run that draws. The edit form has its own rows, below, and the reason the earlier note said it had none was the style rows, which the edit model does not draw: it keeps the rest of the picture.

## Edit Look

The edit form offers its own **Look**, and a pick adds one sentence after your instruction. These rows are separate from the generate ones because the edit model keeps the rest of the picture by itself: an option here is either a change to the whole frame or a change to the area you marked. Every option passed a test on Qwen-Image-2.1 on 2026-10-10, one seed, 20 steps, 768 on the short side, each one beside the bare fixture: see "The edit Look test". Viggle Turbo offers the same 15, because its own six steps kept them all: see "The edit rows, measured 2026-10-10". The official Turbo checkpoint offers them as well, on its own eight-node table: see "The official Turbo test". FLUX.2 offers no edit rows yet, because it has not been sampled on its own.

| Row | Options | What it adds |
|---|---|---|
| Exposure | Brighter, Darker | The exposure of the whole frame |
| White balance | Cooler, Warmer | The color of the light, not the palette |
| Grade | Teal and orange, Muted filmic | A color grade |
| Lens | Shallow depth, Wider view, Telephoto | A lens, and with it the framing |
| Finish | Film grain, Vignette, Halation | A film finish over the frame |
| Retouch | Smooth the skin, Brighten the eyes, Clear a blemish | Skin and eyes, and the area you mark is what they change |

**Retouch** is the one row that wants a mark. Its sentences carry the page's own token for the region, `[the region you marked]`, and the page puts the number of the image holding the mask where that token stands: "Smooth the skin on the face, keeping the pores and the natural texture visible in the area marked in <image2>. Keep the background and everything else unchanged." That is the sentence the Retouch row was measured with, character for character. A pick that wants a mark and has none blocks the run and asks for one, the same way the "Mark a region" template does. The other five rows carry no token, so a mark does not scope them: a grade, an exposure or a film finish applies to the whole frame whether a region is drawn or not, and the sentence says what it does.

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

**Turn into a skeleton** (qwen21 only)

```
Turn the [subject] into its 3D anatomical skeleton in exactly the same pose, position and camera angle: every bone in its true place and number, ivory bone. Replace the background with a plain dark studio backdrop and soft museum lighting.
```

**Turn into a pose figure** (qwen21 only)

```
Turn the [subject] into a 3D pose mannequin in exactly the same pose, position and camera angle: a smooth gray jointed figure with a ball joint at every joint, matching its body proportions. Replace the background with a plain light gray backdrop and even studio light.
```

On a person, both keep the face and hair. See "The skeleton test".

## Video templates

The four older video templates were sampled on 2026-10-17 and 2026-10-18. Their verdicts sit in the comment above `VIDEO_TEMPLATES` in `prompt_aids.py`, next to the template text.

Three more were added on 2026-10-19, from the vendor's 2.5 prompt guide, its native-audio guide, and its audio-driven guide. The shape is theirs; the text is not, and every slot stays a bracket.

| Template | Result |
|---|---|
| Multi-shot | Works. Two hard cuts read at frames 38 and 82 against a 0.27 median frame difference, 28.6 and 16.9 at the cuts. The sheet shows the wide wash, the hood close-up and the doorway wide, in the order the prompt names. |
| Dialogue | Works as a shot. One continuous two-shot of two men at a kitchen table, no cuts (max difference 1.76). The audio is 54 percent speech band with a 2 Hz envelope and a 118 Hz fundamental. The words were not transcribed, so line accuracy is unproven here; the vendor's own samples are the evidence for that. |
| Soundscape | Works. One continuous medium shot of a woman sanding a board, no cuts. The audio envelope follows the hand motion at r 0.56 with a 0.6 Hz modulation, and no musical score dominates its strongest bins. |

Each ran once at 384 x 384, 121 frames, seed 7, with a filled-in prompt and no reference image, through the studio's own endpoint and the distilled pipeline. A filled-in prompt is not the template; it is one reading of it.

## Video Look

The video Look appends one sentence after the prompt, so its options can only name what composes with any prompt: light, weather, palette and the mix. Camera moves and shot scales stay in the templates, where a prompt that already names one cannot fight the appended text.

Each option ran once against one bare control clip on 2026-10-19, at 384 x 384, 121 frames, seed 7, through the studio's endpoint and the distilled pipeline. The control prompt was a woman walking along an empty stone street. The Mix options needed a second scene, because that control carried no score to remove: they ran against a city-at-dusk control that did.

| Row | Option | Result |
|---|---|---|
| Light | Golden hour | Works. Warm low sun and long shadows. Luminance 120.4 to 82.3, red minus blue -0.2 to +30.4. |
| Light | Soft daylight | Works. Natural, soft light with no hard shadows. Luminance 105.9, red minus blue +17.3. |
| Light | Neon night | Works. A dark street with lit shop signs and coloured reflections. Luminance 52.9. |
| Atmosphere | Wet street | Works as wetness. The stone turns wet, darker and reflective, luminance 120.4 to 89.1. Falling drops did not read at 384 x 384, so the row is named for what the clip shows. |
| Atmosphere | Fog | Works. Thick fog, the far end of the street softened. |
| Grade | Warm | Works. Amber cast, red minus blue +151.7 against -0.2. |
| Grade | Cool | Works. Teal cast, red minus blue -66.8. |
| Mix | No music | Works on a scene that invites a score. The control carried tones at 350, 263 and 522 Hz with 7.4 envelope crossings a second; with "no music" the clip was 33 times quieter, with no tonal peak above 0.8 percent. |
| Mix | Ambient only | Cut. On a scene the model had already left unscored it produced a 524 Hz hum, so it changes nothing for the better. |

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

### The edit Look test, measured 2026-10-10

Eighteen options ran on Qwen-Image-2.1, bf16, on the M5 Pro (64 GB), one seed, 20 steps, 768 on the short side, true CFG 1.0, no negative prompt. The seed was 20261010 and it was the same for every sample, so a difference in a pair is the sentence and nothing else. Two fixtures were generated at the same settings, one portrait for the Retouch row and one street for the other five, and each option ran beside its own fixture, which is the control: for an edit the question is what the sentence changed, and the bare fixture is the picture it started from.

| Fixture | Size | What it is |
|---|---|---|
| portrait.png | 768 x 768 | The face the Retouch row was marked on |
| scene.png | 768 x 512 | The street the whole frame rows were run on |

```
Portrait: Close-up portrait photograph of a woman in her thirties with dark shoulder-length hair and a few freckles, in a plain studio, at midday. Wearing a grey sweater, looking at the camera, neutral expression, no makeup. Soft light from the left, plain grey background, softly blurred. 85mm lens at f/1.8, shallow depth of field, natural skin texture, neutral colour mood.

Scene: Street photograph of a young man in a yellow oilskin jacket walking through a narrow European street in the afternoon. Old shopfronts, a bicycle against a wall, wet cobblestones, a striped awning. Soft light from the left, cool shadows. Shot at eye level, 35mm lens, deep focus.
```

A whole-frame row was sent as its sentence alone, which is the instruction a user would type, since the form refuses an empty prompt. A Retouch row was sent as the page composes it: the sentence with its token replaced by the number of the image holding the mask, then "Keep the background and everything else unchanged." A script cannot draw with a hand, so the mark was an ellipse in the palette colour on black, at the picture's own size: over the face for the skin and eye options, 0.33 to 0.67 across and 0.17 to 0.62 down, and a small one on the cheek for the blemish option, 0.56 to 0.64 across and 0.38 to 0.46 down. Both figures are of the picture's own width and height.

Fifteen samples took 32 to 41 s each at 768 x 512, and the three at 768 x 768 took 52 to 60 s. The Retouch three ran in a second pass with the same seed, settings and fixtures, because the scratch harness that composed the marked sentence failed on the first pass. Nothing else about them changed.

| Row | Option | Verdict | What the panel showed |
|---|---|---|---|
| Exposure | Brighter | Kept | Clearly brighter, the pale walls and the shopfronts keep their texture |
| Exposure | Darker | Kept | Clear darkening, the shadow side goes moody, the highlights stay |
| Exposure | Recover the highlights | Cut | Read as darker and more contrasty, not as recovered highlights |
| White balance | Cooler | Kept | Cooler, blue in the shopfronts and on the paving. Subtle, and present |
| White balance | Warmer | Kept | Strong and clean, the left wall goes golden, the composition untouched |
| White balance | Correct for tungsten | Cut | The fixture carries no tungsten cast, so there was nothing to correct |
| Grade | Teal and orange | Kept | Strong, teal in the street, warm on the wall, the jacket stays yellow |
| Grade | Bleach bypass | Cut | Changed the picture, but it read flat and cool, not bleached |
| Grade | Muted filmic | Kept | Soft contrast, lifted blacks, a warm fade |
| Lens | Shallow depth | Kept | Convincing, the subject sharp against a heavy bright bokeh |
| Lens | Wide angle 24mm | Kept, reworded | It works, but it moves the camera: the subject shrinks and the framing changes |
| Lens | Telephoto | Kept | The subject comes closer, the frame tightens, the background softens |
| Finish | Film grain | Kept, reworded | Grain lands. At 1:1 it is coarse and colored, not fine |
| Finish | Vignette | Kept | The corners fall off gradually, with no visible circle |
| Finish | Halation | Kept | A warm bloom on the bright edges, and a mild warm lift with it |
| Retouch | Smooth the skin | Kept | The face reads retouched, the pores kept, the hair and sweater untouched |
| Retouch | Brighten the eyes | Kept, reworded | The eyes opened up and the iris went richer amber, against its own clause |
| Retouch | Clear a blemish | Kept | The skin cleared, and well past the mark: see below |

**The style rows do nothing and a look does.** This is the distinction the earlier note missed. The edit Look that was cut in "The Look test" held a Keep row, "Match the new scene" and "Blend into the photo", and every one of them did nothing, because the edit model keeps the rest of the picture whether it is asked to or not. Nine of these options are changes rather than promises to keep something, and they all landed. The composition, the person, the clothing and the light held in all eighteen, so a whole-frame change does not cost the picture its identity.

**The mark does not bound a retouch.** The blemish sample marked a patch of cheek 62 px wide at 768. The freckles cleared across the whole cheek, including the area well outside the mark, and the two larger marks went with them. So the sentence works and the mark only tells the model where to look. This is the same finding the region table records as spill, measured there on a recolour, and it is why a Retouch option is not a substitute for a local edit tool.

**Three sentences shipped with different words.** Each promised something its panel contradicted, so the meaning was corrected rather than the option dropped.

| Sampled | Ships as | Why |
|---|---|---|
| Wide angle 24mm look, more of the street visible, mild perspective stretch at the edges | Wider view, 24mm: more of the scene in frame and the subject further off, mild perspective stretch at the edges | The camera moves, so the option names the framing rather than a focal length alone |
| Add fine film grain across the frame, like 400 ISO film | Add visible film grain across the frame, like a high ISO color film | The grain is coarse and carries color mottle. Grain size is fixed in pixels, so it reads finer on a larger output than the 768 it was judged at |
| Brighten the eyes slightly, keeping the iris colour and the catchlights | Brighten the whites of the eyes and deepen the iris, keeping the catchlights | The iris did change, and richer amber is what the option does |

**What this sample does not settle.** One seed per option, which is the bar the generate rows were held to and no more; a look that failed here can still be re-run on a second seed. The two fixtures are one portrait and one street, so the exposure, white balance and grade verdicts are statements about those scenes and not about the words in general. The Retouch sentences were measured at one mark shape each, drawn by a script. Nothing here measures Viggle Turbo, the official Turbo checkpoint or FLUX.2. The first two have rows of their own, in "The Viggle Turbo test" and "The official Turbo test"; FLUX.2 offers no edit rows, because it has not been sampled on its own schedule.

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

### The skeleton test

The Skeleton Look ran on three prompts: a woman jogging, a dog leaping for a frisbee, and a heron on one leg. Each ran at 768 x 768, 20 steps and guidance 1.0, on seeds 1234 and 5678, next to the bare prompt. The edit templates changed the seed 1234 images, plus a snake coiled on a rock, at 768 x 768, 20 steps and seed 1234. Two more wordings of each template ran to fix the person case.

| Option | Result |
|---|---|
| Look, anatomical skeleton | Works, 6 of 6: a person, a dog and a heron, each a plausible skeleton. In generate the pose is new: the dogs rear up where the bare dogs leap. |
| Look, pose mannequin | Cut, 2 of 6. It works on the person. On the dog and the heron it drew a human mannequin, once beside a real dog and once with a heron head. |
| Template, skeleton | Works on the dog and the snake, in the same pose. The heron stands on two legs, not one. The person keeps her hair and a see-through outline of her body. |
| Template, pose figure | Works on the dog, the heron and the snake, each a jointed figure in the same pose. The person keeps her real face, hair and shoes. |
| "The whole body, head and face included" | Did nothing: the person kept her face and hair. |
| "Replace the [subject] with a figure of its species" | Fixed the person, and broke the animals: the snake grew legs, and the pose figure became a human mannequin with a ball head on the dog and the heron. It was cut. |

The edit model protects a person's identity. No wording that kept the animals right also changed the face.

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

### The Viggle Turbo test

Viggle Turbo samples Qwen-Image-2.1 on a distilled six-step schedule, so the aids
were sampled again on that schedule rather than inherited. Measured 2026-10-05 on
the M5 Pro, six steps, seed 1234, 768 x 768, bf16, the adapter unmerged.

The fixture was "a cat wearing a suit", the one the Look test used. Each option ran
next to the bare prompt, one contact sheet per row. Two rows are about people and a
cat cannot judge them, so Realism and Portrait ran again on "a woman in her thirties
reading at a cafe window", the fixture of the avoid-part test. That is 35 images in
the first run and 4 in the second.

The sheets were lost on 2026-10-06 to a delete glob wider than its folder, and all ten
were rebuilt the same day. Eight came back from this file's own set: the fixtures, seed,
schedule and option names, at 19 to 24 seconds an image, and every verdict below held,
Deep focus included, which still reads as no change in focus at any of its three seeds,
so the cut stands.

The two template sheets came back from the run's own log, which had survived the glob:
it held all 35 prompts, the seven fill-ins, the two sources and the seven instructions,
word for word. Every template verdict held as well. That log was scratch and is gone, so
the fill-ins it carried are not in this repo. A later re-run picks its own, since the
verdict below is about the template working with a sensible fill-in and not about the
words this one used. Two things the log did not carry, and what I did with each: the
size, taken as 768 x 768 except the banner at 16:9, which its own sentence and its
verdict ask for; and which source each edit used, which the verdicts name for six of the
seven and leave open for Add text, so it ran on the woman. The 18 prompts of the rebuilt
row sheets were checked against that log and every one matches the words the sample
itself used.

| Row | Option | Result |
|---|---|---|
| Medium | Documentary | Works: plausible daylight on a carpeted floor, real fur and cloth. |
| Medium | Watercolor | Works: soft washes on textured paper, visible brush edges. |
| Medium | Skeleton | Works: skull, spine, ribs and limb bones in the pose, the suit still on the body. |
| Film | Portra 400 | Works: warm natural color. |
| Film | Black and white | Works: high contrast and strong grain, the Tri-X look its sentence names. |
| Color | Warm | Works: amber and cream, a warm brown suit. |
| Color | Vivid | Works: saturated without going poster flat. |
| Light | Soft window light | Works: a visible window, soft shadow on the left. The shot widens, as it does on the base model. |
| Light | Golden hour | Works: low warm sun from the side, long shadows. Widens the shot. |
| Light | Night with neon | Works: a neon sign, a wet street and its reflections. Widens the shot. |
| Camera | Close-up 85mm | Works: tighter on the head, more blur behind. |
| Camera | Wide 24mm | Works: the room comes back into the frame. |
| Camera | Top-down | Works: a true overhead view. |
| Room for text | Left | Works: the subject on the right third, the left side empty. |
| Room for text | Top | Partly works: the empty band across the top is there, the subject stays near the centre. The same weakness the base model shows. |
| Realism | Real person | Works on the person fixture, and without its avoid part: messy hair, a plain cardigan, unretouched skin. This backend declares no negative prompt, so the avoid part cannot be sent, and the sentence alone carried it. |
| Portrait | Over the shoulder | Works: the person turns three-quarters away, one side of the face in shadow. |
| Portrait | Candid glance | Works: the gaze off camera, a small smile, unposed. |

| Mode | Template | Result |
|---|---|---|
| Generate | Portrait photo | Works: every slot followed, the window light and the blurred background included. |
| Generate | Product shot | Works: the teapot, the props, the empty side. |
| Generate | Landscape | Works: the path leads the eye, the light is dawn. |
| Generate | Poster with text | Works: the title 山茶小館 came out exact and Traditional, with the second line and the small line below it. |
| Generate | Illustration | Works: washes, the named palette, the fox asleep on the log. |
| Generate | Deadpan absurdity | Works: a horse at the water cooler, and nobody reacts. |
| Generate | Banner | Works: a clean 16:9 thumbnail, all three quoted lines exact, the layout as briefed. |
| Edit | Change a color or material | Works: the chair turned deep matte blue, the floor and the light untouched. |
| Edit | Replace the background | Works: a snowy night street, the woman and her umbrella unchanged. |
| Edit | Add text | Works: "Studio 4" exact, on a sign at the top left. |
| Edit | Alternate reality | Works: Earth and stars above the buildings, the pose and the light preserved. |
| Edit | Add an object | Works: a dog beside the woman, with a shadow and floor contact. |
| Edit | Turn into a skeleton | Works, and better on a person than on the base model: the head came back a bare skull. On qwen21 the person keeps her face and hair. |
| Edit | Turn into a pose figure | Works on the body: a grey jointed figure with a ball joint at every joint. The head keeps the real face and hair, the limit the base model has too. |

#### The edit rows, measured 2026-10-10

The 15 edit options ran on this schedule: six steps, which is the only one its distillation samples, no guidance and no negative prompt because it was trained without CFG, one seed, 768 on the short side, each option beside the bare fixture. The fixtures are the base model's own, regenerated at the same seed, prompts and settings, so the pictures are the same and only the editing model differs from the table above. Each sample went through the page's own path: the adapter unmerged, and the viggle schedule supplied for the length of the edit call, which is what `ViggleTurboBackendGateway` does. A Retouch option's sentence carries the mark's token, so it was sent with the token replaced by the number of the image holding the mask, which is what the page does.

| Row | Option | Verdict | What the panel showed |
|---|---|---|---|
| Exposure | Brighter | Kept | Clearly brighter, the pale walls and the shopfronts keep their texture |
| Exposure | Darker | Kept | Clear darkening, the shadow side goes moody |
| White balance | Cooler | Kept | Cool in the shopfronts and on the paving, the jacket stays yellow |
| White balance | Warmer | Kept | Strong and clean, the left wall goes golden |
| Grade | Teal and orange | Kept | Strong, teal in the street, warm on the wall |
| Grade | Muted filmic | Kept | Soft contrast, greyer paving, a gentle fade |
| Lens | Shallow depth | Kept | Convincing, the subject sharp against a heavy bokeh |
| Lens | Wider view | Kept | Wider, and the camera moves with it: the subject smaller and further off |
| Lens | Telephoto | Kept | The subject closer, the frame tighter |
| Finish | Film grain | Kept | A fine speckle over the frame at 1:1, less colored than the base model's |
| Finish | Vignette | Kept | The corners fall off gradually, with no visible circle |
| Finish | Halation | Kept | A warm bloom on the bright edges |
| Retouch | Smooth the skin | Kept | The skin reads retouched, the pores kept |
| Retouch | Brighten the eyes | Kept | The whites brighter and the iris richer: the overreach the base model shows too |
| Retouch | Clear a blemish | Kept | The freckles cleared, and well past the mark: see below |

Fifteen of 15 landed, so this backend offers the whole catalog and not a subset. That is the opposite of its generate sample, which dropped Deep focus and kept 30 of 31 options. Nothing was reworded for this schedule.

**The mark still does not bound a retouch.** The blemish sample marked a patch of cheek 62 px wide at 768, and the freckles cleared across the whole cheek, including well outside the mark. That is the same finding the base model's table records, so a Retouch pick on six steps changes the area its sentence names rather than the area the mark covers.

**What this sample does not settle.** One seed per option, the bar the generate rows were held to and no more. Six steps is the only schedule this distillation runs, so there is no second step count to compare against, and whether these sentences would hold at another count is not a question this model can be asked. The two fixtures are one portrait and one street, so the exposure, white balance and grade verdicts are statements about those scenes. The Retouch sentences were measured at one mark shape each, drawn by a script, and not by a hand with the brush. The timings were 10 to 23 s an image at 768 x 512 and 29 to 37 s at 768 x 768, on the M5 Pro, with nothing else on the GPU.

#### The options the first pass left out, measured 2026-10-06

Thirteen options were missing from the sample above, so they ran on the same fixture,
the same seed and the same schedule, each beside the bare prompt. Twelve did what their
sentence says and one did not.

| Row | Option | Result |
|---|---|---|
| Medium | Phone snapshot | Works: a candid phone photo, plainer light and framing. |
| Medium | Ink drawing | Works: black linework and cross-hatching on white paper. |
| Medium | 3D render | Works: a smooth rounded character under soft studio light. |
| Film | Fuji 400H | Works: cool soft pastels and fine grain. |
| Film | Ektachrome | Works: high contrast, vivid color, deep clean shadows. |
| Color | Cool | Works: a blue and grey palette. |
| Color | Muted | Works: desaturated greys. |
| Light | Studio | Works: even light on a plain backdrop, with no light stand in the picture. The base model needed its wording rewritten for exactly that. |
| Light | Overcast | Works: soft diffuse light, gentle shadows. |
| Camera | Low angle | Works: the subject looms and the view looks up at it. |
| Camera | Telephoto | Works: shot from a distance, the background compressed. |
| Room for text | Right | Works: the subject on the left third, the right side empty. |
| Camera | Deep focus | Cut, on three seeds. At seed 1234 it changed nothing visible. At 5678 and 9012 it changed the picture, but not in the direction the sentence names: the framing pulled tighter and the background became a readable textured surface rather than a sharp version of the same shot. No seed read as an even f/11 focus. The base model kept it at "a little crisper" at best, so it is weak on both. |

So one option is out and this backend offers the other 30.

#### What this sample does not settle

One seed and one fixture per row, except deep focus, which was run at three seeds because
one image is thin ground for dropping an option. The distilled schedule has no other step
count, so there is nothing to compare a six-step result against, and no option was run
twice otherwise.

An avoid part cannot be tested on this backend, because it declares no negative prompt
and the page sends none. Real person keeps its avoid part in the shared wording, where a
mode with a negative prompt would send it.

#### The cost, re-measured 2026-10-06

The generate cost was checked twice on 2026-10-06, and both checks were wrong. The first,
at about 01:00, read 8.0s, 27.8s and 68.7s, and the constant in
`gateways/image/viggle_turbo/capabilities.py` was replaced on that evidence. The Look sample above
ran at about 21s an image at 768 x 768 on 2026-10-05, which agreed with it.

Measured again on 2026-10-06 at 11:25, GPU free, one job at a time, two passes of six
steps each at seed 1234 on the cat fixture:

| Tier | The two runs | Mean | The pair in the file predicts |
|---|---|---|---|
| 0.26 MP | 4.9, 6.1 | 5.5 | 5.4s |
| 0.59 MP | 10.3, 9.9 | 10.1 | 11.4s |
| 1.05 MP | 23.9, 23.5 | 23.7 | 23.4s |

The pair in the file is the base model's, and it stands: 13% high at the middle tier and
within 2% at the other two. Six runs with this spread do not improve on it.

A busy machine was the explanation for the 8.0, 27.8 and 68.7 check, and the machine is
not that simple. Thirty-six of the same runs at 1024 x 1024, back to back at 11:33, took
between 20.0s and 51.6s, median 30.7s. The first 27 averaged 33.7s and the last 9
averaged 21.4s, which is the figure above again. The load average recorded beside each
run correlates with the time at 0.56: the two highest loads gave the two slowest runs,
and one run took 45.2s at load 1.71. So most of the spread is inside the machine, and I
did not instrument which part of it.

What that means for the constant: the idle figure is the one to ship, because the page
shows the estimate before a run and learns this device's own rate from the run itself,
so a machine at the slow end corrects the page within one run. The check that recorded
8.0, 27.8 and 68.7 read that slow end as the machine's speed, which would have promised
about three times the time an idle machine gives.

The edit half needed no change, and it is now measured rather than inherited: its 19.3s
at 0.59 MP was reproduced at 20.2s and 26.3s against a pair that predicts 24.0s.

One process drawing many prompts also grows, and the sample above is where that showed.
Across fourteen of its images the MLX active memory read 16.9 GB, then 30.6 GB, then
33.7 GB, while its peak reached 64.4 GB on a 64 GB machine.

The cause is not a cache. mflux's MemorySaver drops the text encoder before every
denoising loop, and a prompt that is not already in the model's cache needs it back.
Studio's only way back is to drop the whole model and rebuild it, which re-applies the
LoRA, and the frame that asked for the rebuild still named the old model. So the rebuild
built a second copy of the weights while the first was live. Measured 2026-10-06 on three
prompts at 768 x 768 in one process, the peak read 16.9 + 30.7 = 47.6 GB, and the active
memory climbed for the same reason, because each rebuild leaves a set behind.

Dropping that name before the release lets the old set go first. Measured the same way
with one line changed: the peak reads 30.7 GB, the weights alone, and the active memory
holds at 16.9 GB across the three instead of climbing to 32.2 GB. That is the difference
between fitting on a 64 GB machine and reaching its ceiling, which is why the first
attempt at this sample died at image 21 with no traceback. A later death was a plain
Python error, so the two were not the same event.

The time follows the same line. Four separate processes alternating the two arms put the
changed one ahead in both pairs, 16.1 seconds an image against 18.5 and 19.6 against
21.5, but their means rose in run order, so the machine's drift over those six minutes
was as large as the effect. Alternating the two inside one process controls it, and with
the order reversed in half the pairs so the drift lands on both arms in turn: twelve
images, 14.8 seconds an image against 21.5, and all six pairs reading the same way, by
6.6, 5.5, 10.6, 6.9, 5.3 and 5.3 seconds. So the rebuild over a live copy was costing a
third of the time of every image with a new prompt, not only the memory it doubled.

#### What a cancelled rewrite gives back, measured 2026-10-06

The cancel frees the rewriter, and MLX reports its own memory, so the free is read
rather than inferred. Active memory is the live tensors.

| Moment | Active | Cache | Peak |
|---|---|---|---|
| The rewriter resident and writing | 31.58 GB | 0.00 GB | 31.58 GB |
| Stopped, model still in hand | 31.58 GB | 0.17 GB | 33.27 GB |
| After the free | 14.05 GB | 0.00 GB | 33.27 GB |

So the free gives back **17.53 GB**. The 14.05 GB the last row starts from is that
script's own earlier image-engine phase, so the delta belongs to the rewriter. The peak
never falls, which is what a peak is.

#### Several pictures at once, measured 2026-10-12

The page's note claimed that the rewriter reads the pictures, so its answer names the one
it read. Four pictures of four different subjects were put to it: a golden retriever, a
black cat, a grey rabbit and a red parrot, each generated on the M5 Pro at the
first tier size the form offers, eight steps. The same words go with them both ways:
"make it a chihuahua sitting in a dog bed".

| What was asked | What came back |
|---|---|
| all four pictures in one call | one paragraph of 1588 characters, about one of the four. Its first sentence places "the golden retriever from `<image1>`", and the other three are named nowhere |
| one picture per call | four answers of four, 643 to 1950 characters, and each names its own subject: the golden retriever, the black cat, the grey rabbit, the red parrot |

The single calls took 14, 16, 24 and 30 seconds, and the one call over the four took 49: the
other three are encoded and attended to and then left out of the answer.

So one picture is what the rewriter can be asked about, and a run of several pictures that
takes one instruction for all of them is pulled toward whichever one the answer names. The
page gives the rewriter one picture at a time for a batch, and each answer lands in that
image's own row.

Asked one picture at a time, the rewriter keeps its own reading of the words. In a later run
of four, with "make it a chihuahua sitting in a dog bed" and one picture per call, three of the
four answers carried the transformation: one turned the parrot's plumage into the chihuahua's
own coat, as its own instruction asked. The fourth left its subject alone. Given the black cat,
the answer was to keep the cat completely unchanged and set it in a bed, so the result is a cat
in a bed and not the change the words asked for. A press is one model's reading, and the row
it lands in is the user's to correct.

What this does not settle: one sample, one seed and one instruction, and the answer's own
quality is not read here. The subject each answer names is found by looking for that
subject's own words in it, which is a reader and not a judgement.

### The official Turbo test

The official Turbo checkpoint samples its own eight-node sigma table, so the aids
were sampled on that schedule rather than inherited. Measured 2026-10-16 on the
M5 Pro, eight steps on that table, seed 1234, 768 x 768, bf16.

The fixture was "a cat wearing a suit", the one the Look test used. Each option ran
next to the bare prompt, one contact sheet per row. Two rows are about people and a
cat cannot judge them, so Realism and Portrait ran again on "a woman in her thirties
reading at a cafe window", the fixture of the avoid-part test. Every prompt went
through the page's own composition: the option's sentence after the user's text,
closed with a full stop, and an avoid part sent as the negative prompt, which is what
raises the scale to 2.5 and turns true CFG on.

The sample covered every aid this backend offers: 31 generate options, the 15 edit
options, and all 15 templates, in 61 runs of the image plus their bare controls.

| Row | Option | Result |
|---|---|---|
| Medium | Documentary | Works: natural exposure, real fur and cloth |
| Medium | Phone snapshot | Works: flatter light, uneven framing, a room behind |
| Medium | Watercolor | Works: soft washes on textured paper, visible brush edges |
| Medium | Ink drawing | Works: fine black linework and cross-hatching on white |
| Medium | 3D render | Works: smooth rounded shapes, soft studio light |
| Medium | Skeleton | Works: skull, spine, ribs and limb bones in the pose, the suit still on the body |
| Film | Portra 400 | Works: warm natural color |
| Film | Fuji 400H | Works: cool soft pastel tones |
| Film | Ektachrome | Works: high contrast, deep clean shadows |
| Film | Black and white | Works: strong grain and high contrast, the Tri-X look its sentence names |
| Color | Warm | Works: amber and cream, a warm brown suit |
| Color | Cool | Works: blue and teal, a cool grey cat |
| Color | Muted | Works: desaturated |
| Color | Vivid | Works: saturated without going poster flat |
| Light | Soft window light | Works: a visible window, soft shadow on the left. The shot widens, as on the base model |
| Light | Golden hour | Works: low warm sun, long shadows. Widens the shot |
| Light | Studio | Works: even light, a plain seamless backdrop, and no light stand in the picture |
| Light | Overcast | Works: soft diffuse light, gentle shadows |
| Light | Night with neon | Works: a neon sign, a wet street and its reflections. Widens the shot |
| Camera | Close-up 85mm | Works: tighter on the head, more blur behind |
| Camera | Wide 24mm | Works: a bookshelf comes back into the frame |
| Camera | Top-down | Works: a true overhead view |
| Camera | Low angle | Works: looking up at the subject |
| Camera | Telephoto | Works: the subject comes closer and the background compresses |
| Camera | Deep focus | Does not land: identical to the bare fixture, which has no depth in it to recover. The Viggle sample cut this option for the same reason. It ships here anyway, because this backend's catalog is the base model's by design and one option that changes nothing costs a user nothing |
| Room for text | Left | Works: the subject moves right and a plain area opens on the left |
| Room for text | Right | Works: the subject moves left and a plain area opens on the right |
| Room for text | Top | Works: the subject drops and a wide plain area opens across the top |
| Realism | Real person | Works on the woman fixture, with its avoid part at guidance 2.5: a plain, candid person rather than a posed beauty portrait |
| Portrait | Over the shoulder | Works: the person turns three-quarters, one side of the face in shadow |
| Portrait | Candid glance | Works: caught unposed, gaze slightly off camera |

#### The edit rows

The 15 options ran on this checkpoint's own two fixtures, generated at the seed and
prompts the earlier edit table records: a street at 768 x 512 for the five whole-frame
rows, and a portrait at 768 x 768 for Retouch. Each option ran beside its own fixture,
because for an edit the question is what the sentence changed. A Retouch sentence
carries the mark's token, so it went with the token replaced by the number of the image
holding the mask, and the mask itself was an ellipse in the palette's orange on black
over the face, which is what the page sends.

| Row | Option | Result |
|---|---|---|
| Exposure | Brighter | Works: clearly brighter, the pale walls keep their texture |
| Exposure | Darker | Works: the shadow side goes moody and the highlights stay |
| White balance | Cooler | Works: blue in the shopfronts and on the paving |
| White balance | Warmer | Works: a strong clean golden cast, the composition untouched |
| Grade | Teal and orange | Works: teal in the street, warm on the wall, the jacket stays yellow |
| Grade | Muted filmic | Works: soft contrast, lifted blacks, a warm fade |
| Lens | Shallow depth | Works: the subject sharp against a heavy bright bokeh |
| Lens | Wider view | Works: more of the street in frame, the subject further off |
| Lens | Telephoto | Works: the subject closer, the frame tighter, the background softer |
| Finish | Film grain | Works: visible grain across the frame |
| Finish | Vignette | Works: the corners fall off gradually, with no visible circle |
| Finish | Halation | Works: a warm bloom on the bright edges |
| Retouch | Smooth the skin | Works: the face reads retouched, the hair and sweater untouched |
| Retouch | Brighten the eyes | Works: the eyes open up and read brighter |
| Retouch | Clear a blemish | Works: the skin clears. The mark does not bound it, as the region table below and the base model's own note both record |

#### The templates

Each template ran with its first fill-in, and the two that ask for lettering were
judged on the lettering.

| Template | Result |
|---|---|
| Portrait photo | Works: every slot followed, light from the left, 85mm, a plain blurred background |
| Product shot | Works: the mug, the oak table, the napkin, the window light, space on the right |
| Landscape | Works: the fjord, the red boathouse, the gravel path leading the eye |
| Poster with text | Works: "Midnight Sessions", "Friday, doors at eight" and "The Old Ship, Hackney" all exact |
| Illustration | Works: gouache, the fox on the right third, the palette named |
| Deadpan absurdity | Works: a horse waiting by the launderette machines while the people carry on |
| Banner | Works: "BUILD FASTER" and "Ship every Friday" exact, the badge reads "New", 16:9 |
| Change a color or material | Works: the oilskin jacket goes deep red and matte, the same cut, seams and pockets |
| Replace the background | Works: the woman in a sunlit kitchen with a kettle and a window box |
| Add text | Works: a "Bakery" sign above the shopfront, dark green painted serif, legible |
| Alternate reality | Works: the same street in 1920, a horse cart and gas lamps |
| Add an object | Works: the dog on the cobbles with its shadow, the man glancing down and smiling |
| Turn into a skeleton | Works: the woman's bones reading a book, in her pose |
| Turn into a pose figure | Works: a jointed grey figure in the same pose |
| Mark a region | Works, subtly: the eyes read slightly brighter than the bare portrait and it is hard to separate the two by eye at this size |

**What this sample does not settle.** One seed per option, the bar the generate rows
were held to and no more; an option that failed here can still be re-run on a second
seed. The two fixtures are one cat and one woman, so the exposure, white balance and
grade verdicts are statements about those scenes and not about the words in general.
The Retouch and Mark a region sentences were measured at one mark shape each, drawn by
a script. Deep focus is the only option this schedule did not reward; the Viggle sample
cut it and this one keeps it, for the reason its row above gives. The mark's containment
on this checkpoint is measured separately, in "The same metric on three scenes" below.

## Marking a region

The page's **Mark a region** tool sends the marked area as the last image of the
run: the model takes the original image and a separate mask as two inputs. The
mask file carries each region in the palette colour that names it, on black, with
hard edges and at the reference's own pixel size. A default single region is
therefore orange, not white.

The black is not a prohibition. See "What the mask does not do" below: nothing in
the pipeline pins the latents to the marked pixels, so the mask steers the model
rather than constraining it.

Measured 2026-09-25 on Qwen-Image-2.1, one seed, 20 steps, one image at 832 x
1248, each result compared against its input. Concentration is the mean change
inside the region divided by the mean change outside it.

| What the run sent | Inside | Outside | Concentration | The ink survived? |
|---|---|---|---|---|
| Circles drawn on the image, named by colour | 18.2 | 3.0 | 6.2 | not measurable |
| A white scrawl on the image, named as white | 68.1 | 11.8 | 5.8 | no: 4.20% white to 0.00% |
| Original and mask, plain instruction | 30.8 | 3.1 | 9.9 | not applicable |
| **Original and mask, instruction names the image** | **52.4** | **2.5** | **20.7** | not applicable |
| The vendor's own mask example, measured the same way | 35.8 | 8.7 | 4.1 | not applicable |

### Several regions and several colours, measured 2026-09-26

A drawn scene, so its content is known without looking: a yellow circle on the left
and a green square on the right. Two changes in one prompt, written the blog's way,
naming the object that is there rather than one to add. One seed, 20 steps. The
numbers are colour fractions of the result, because a recolour is what both an eye
and a count can see.

| What the run sent | The circle | The square | The marks | Background |
|---|---|---|---|---|
| Rings painted on the image (the blog's way) | yellow to 0.01%, blue only 0.07% | green to 1.56%, red 5.63% | the ring's orange 0 to 1.73%: it stayed | 87.32 to 84.14% |
| The original and one colour coded mask | yellow to 0.00%, **blue 0 to 6.12%** | green to 0.00%, **red 0 to 6.21%** | none: separate image | 87.32 to **87.29%** |

The colour coded mask followed both instructions and left the background alone. The
rings did neither: the circle never took the colour it was told to, and the ring's
own colour stayed in the picture. That is the failure a run of "make circled area
McDonald logo" showed, reproduced on a scene whose content is known, and it is the
method, not the wording.

So several regions travel as one mask whose areas carry the colours, and the prompt
names each area's colour. The mean delta concentration is not the metric here
(x0.4): a recolour changes the objects while the model re-renders the background's
texture, so the colour fractions are the evidence.

Read that row with its fixture in mind. The marked area and the object under it were
the same circle, so the mask's edge sat on the object's edge and a mask that paints
its own colour has nowhere to show. The loose-region measurement below finds exactly
that: a hand-drawn region comes back in the mask's colour wherever the mask reaches
past the object. So this row says the colour coded mask works when the two edges
coincide, which is what a drawn shape gives and what a hand on a track pad does not.

### The leak, measured 2026-09-26

The table above measured locality only. It never asked whether the mask's own shape
lands in the result, which is the failure a run of "make circled area McDonald
logo" showed. Measured again on the same image and seed with 20 steps, adding a
small red apple, with a second number: the edge strength along the mask's own
outline against the frame's average. A ratio near 1 means no edge was drawn there;
a ratio over 2 means the outline is visible.

| Prompt, after the instruction | Locality | Outline edge |
|---|---|---|
| "in the area marked in <image2>" | x8.8 | x1.10 |
| "in the area you marked in <image2>" | x8.5 | x1.13 |
| "in the area marked in white in <image2>" | x19.7 | **x2.18** |

So the phrase that named white nearly doubled the change in the region and painted
the mask's outline into the picture. Reading it as the best wording was wrong: that
reading came from a metric that cannot see a leak. The template says "the area
marked in [the region you marked]", and naming white is not how to make the model
work harder inside the region.

So this repo sends the mask as the last image and names it in the prompt. Naming
the image doubles the concentration over a plain instruction, and beats the
model vendor's own published example on the identical measurement.

Read that number knowing what the later measurements found. A high concentration is what
repainting the marked area looks like, so it says the mark was followed. It does not say
the change stayed inside the object under the mark, and on a hand-drawn region it does not.

Two things these numbers do not say. Local means the change lands in the region,
not that the rest is untouched: outside it the frame shifts by a mean of 2.5 to
11.8, which is the model re-rendering the whole picture. And one seed and one
image is a signal, not a benchmark. The cost is 97 to 149 seconds an edit at
about one megapixel and 20 steps.

### What the mask does not do, measured 2026-09-26

The section above describes the mask file. It does not say what the pipeline does with it, and the pinned source answers that plainly. `pipeline_qwenimage21.py` at the pin `9f1246971` takes no mask argument. The only `mask=` in the file is line 270, and it is PIL alpha compositing for the vision-encoder copy. Every other mask in the file is a token attention mask.

```python
if img.mode == "RGBA":
    white = PILImage.new("RGB", img.size, (255, 255, 255))
    white.paste(img, mask=img.getchannel("A"))
    img = white
```

So nothing pins the latents to the marked pixels. The mask reaches the model as a second image in the vision context. The model reads it, then paints where its own reading of the instruction says. That is the mechanism behind the overreach on the shirt photograph: "change the cloth" names one object, the model finds cloth across the marked yoke and the unmarked overalls, and the mask cannot veto the second one.

A drawn scene cannot reproduce that. A flat shirt, one sleeve marked, one seed, 20 steps, two runs: one prompt bare, one naming the body and the right sleeve as unchanged. The number is the fraction of each part that took the target red.

| Region | Marked | Red, bare prompt | Red, naming what stays |
|---|---|---|---|
| The left sleeve | yes, the mask covers it fully | 98.6% | 98.6% |
| The body | no, the mask touches 2.6% of it | 0.0% | 0.0% |
| The right sleeve | no | 0.0% | 0.0% |

Both runs are the same picture. The mean delta between them is 0.41 levels, and the only box where they differ by more than 12 levels sits inside the marked sleeve. The change stayed in the mask, and the rest of the frame moved by 2 to 3 levels, which is noise.

So naming what must stay has no measurable effect on this scene, and the scene cannot show one. The model's reading and the mask agree, so nothing needs correcting. The result is a limit of the fixture, not a verdict on the wording. A test of the wording needs a case where the instruction's object spans the mask's edge, which is what the photograph gave.

One rule survives, and the mechanism explains it. Make the marked area have exactly one plausible reading, because the model will take the unmarked part of any object the instruction names.

### The wording the page sends, measured 2026-09-26

The page writes the sentence itself, so the page's own wording was the one shape never measured. `composedPrompt` sends `<row text> in the orange area of <image2>. Keep the background and everything else unchanged.` over the colour coded mask. The table above measured a different prompt, on a white mask, so `region_marking` shipped on borrowed evidence until this run.

A drawn scene, so its content is known: a yellow circle on the left and a green square on the right. The circle is marked in orange and told to turn blue. The square is not marked. One seed, 20 steps, at 1024.

| Prompt | The circle | Blue | The square | The mark's ink | Background | Concentration |
|---|---|---|---|---|---|---|
| `...in the orange area of <image2>.` (what the page writes) | yellow 6.21% to 0.00% | 0.00% to 6.13% | 6.21% to 6.21% | 0.00% to 0.00% | 87.32% to 87.29% | x24.2 |
| `...in the area marked in <image2>.` | yellow 6.21% to 0.00% | 0.00% to 6.13% | 6.21% to 6.21% | 0.00% to 0.00% | 87.32% to 87.29% | x24.7 |

Both wordings did the same thing. The recolour is exact: the circle's 6.21% of yellow left and 6.13% of blue arrived, which is the same area. The unmarked square is unchanged to the digit. The background holds within 0.03%. No ink from the mark appears. Naming the colour costs nothing measurable against naming the image, so the sentence the page writes stands, and the token it writes that sentence around is the page's to fill.

Two things this does not settle. The concentration is fixture-dependent, so x24.2 here and 8.8 in the table above are a different scene, a different mask and a different prompt, and neither is a benchmark on one seed. And the outline metric is confounded on a drawn scene: a flat circle already has an edge at its own boundary in the input (x14.8 there, against x22.4 in the result), so it cannot separate a painted mask outline from the stronger contrast of the recolour itself. The outline rows above come from a photograph. They are not a claim about this wording.

### A loose region, measured 2026-09-26

A hand-drawn region is not accurate, so a test of that case needs the mask's edge away from the object's. This fixture is a hard-edged block and a wobbly mask that covers it and bulges into the background all the way round. The mask covers 17.9% of the frame and the block 11.0%, so the recolour's own area says which of the two the model followed. The question was whether a clause about keeping the object's shape would help.

| Prompt | Green | The block's blue | The mask's orange | Stray, the change outside the block | Concentration |
|---|---|---|---|---|---|
| The sentence the page sends | 10.82% | 0.00% | **6.78%** | 38.4% | x11.4 |
| Plus "Keep the object's own shape exactly as it is." | 10.82% | 0.00% | 6.77% | 38.3% | x10.8 |
| Plus "The marked area is a guide, not a boundary: keep the shape of the object in the original image." | 10.79% | 0.00% | 6.71% | 38.2% | x10.1 |

Two things fall out, and neither is the wording. The model already keeps the object's shape: green is 10.82% against the block's 10.89%, so it recoloured the block, not the mask's wider area. A clause asking for that changes nothing measurable, and the three rows being the same is that answer.

The model also renders the mask's own fill. The annulus between the block and the mask's edge comes back orange, sampled at 251,128,0 on all four sides of the block, bounded exactly by the mask, with the background outside it unchanged. On the fixtures above the mask's edge sat on the object's edge, so the halo had no width and nothing showed. A loose region is the halo, drawn at the wobble, and it is 6.78% of the frame.

So the next thing to measure is the colour, not the wording: a white mask named with "in the area marked in `<image2>`", against the palette colour with a clause that says the colour labels the area rather than belonging to the picture.

That measurement, on the same fixture and seed, two more runs:

| Mask, and the wording | Green | The mask's orange | Stray, the change outside the block | Concentration | The ring outside the mask |
|---|---|---|---|---|---|
| Orange, "in the orange area of `<image2>`" | 10.82% | 6.78% | 38.4% | x11.4 | x21.90 |
| Orange, plus "the orange is only a label for where to work, and is not part of the picture" | 10.82% | 6.78% | 38.3% | x11.8 | x22.55 |
| **White, "in the area marked in `<image2>`"** | 10.82% | **0.00%** | **1.2%** | x6.3 | x2.51 |

The halo is the mask's colour, not the wording. A clause saying the colour is a label changes nothing, and the white mask takes the halo away: the change lands inside the block instead of painting the mask's shape, 1.2% of it straying against 38.4%.

Two costs to weigh. The concentration halves, x11.4 to x6.3, though the higher figure is the halo counted as change inside the region, so the fall is not as bad as it reads. And the ring outside the mask rises from 0.63 to 1.59, a hairline edge at 2.51 times a baseline that is nearly flat, against a frame whose own mean edge is about 1.5. So a faint outline is drawn where the mask's boundary is, which is the failure the white wording showed on the photograph at x2.18. It is far smaller than the halo: 1.59 against 13.87.

That row put the white mask ahead for one region, and the next measurement takes it back. Two things are wrong with it as evidence: its fixture is flat, and every measurement above had the mask's edge on the object's edge, where a halo has no width and cannot show. So the two-region rows are not evidence that the palette is safe on a loose region, and the white row is not evidence that it is unsafe.

#### The flat fixture was too easy, measured 2026-09-26

Everything above is drawn flat: one colour against another, with the object's edge the only edge on the frame. That hands the model the object. Measured again on a textured scene, a garment with folds on a noisy background, the same loose mask in two colours, one seed, 20 steps:

| Mask, and the wording | Green, the change | The garment as drawn | Stray | The ring outside the mask |
|---|---|---|---|---|
| Orange, "in the orange area of `<image2>`" | 21.62% | 17.47% | 23.9% | 4.90 to 19.49 |
| White, "in the area marked in `<image2>`" | 21.56% | 17.47% | 23.9% | 4.90 to 18.09 |

The mask covers 21.9% of that frame and the garment 17.5%. Both runs painted about 21.6% green, so both painted the mask's area and not the garment's, and the two masks behaved the same. The white mask no longer helps, so the mask's colour is not the lever, and the white row above is not a reason to change the page's palette.

#### The template and a row say it twice, resolved 2026-09-26

The region template is written as `Change only [what changes] in the area marked in
[the region you marked].`, and the page writes one clause per row after it and then its own
pin on the background. So a run that picks the template and fills a row asked for the change
twice, and the row was required whenever a region was drawn, so following the UI's own hints
reached it.

Fixed on the call that the user's experience should win over the page's tidiness. A row is
optional once the prompt names the region, and an empty row writes nothing rather than
leaving ` in the orange area of <image2>` in the sentence with no instruction in front of it:

    the template, a region drawn, the row left empty:
    Change only turn the wall blue in the area marked in <image2>. Keep the background and
    everything else unchanged.

So the template's sentence is the instruction, or the rows are, and the page writes whichever
the user filled. The template also lost its own trailing `Leave the rest of the image
unchanged.`, because the page pins the background after every prompt that carries a mask, and
two pins are the same duplication one level down.

#### What the model does with a marked region

Put the loose measurements together and one thing holds across all of them: **the model repaints the area the mask marks.** On a flat frame it can find the object instead, and on a frame where the mark and the object are the same shape there is no difference to see, which is why this stayed hidden. Two-region runs do the same thing twice over: each region comes back filled, sometimes with the change asked for and sometimes with a blend of the mark's own colour, and the boundary of what changed is the mask's boundary.

#### The boundary's own quality, measured 2026-09-26, unresolved

If the model repaints the marked area, then the boundary it bakes is the drawn one, and
a track pad's tremor is high-frequency noise worth removing before the run. Two masks on
the textured garment, one seed, 20 steps: one carrying a tremor, and the same contour
blurred and re-thresholded to smooth it.

| Mask drawn | Covers | Its boundary roughness | Green, the change | Stray |
|---|---|---|---|---|
| With a tremor | 22.0% | 1.86 | 21.35% | 21.4% |
| Smoothed | 18.9% | 1.38 | 18.80% | 14.0% |
| The plain contour, for reference | 21.9% | 1.35 | not run | not run |

Roughness here is the changed area's boundary length against a circle of the same area,
so 1.00 is perfect. Smoothing took the spill from 21.4% to 14.0% and the recoloured area
from 21.35% to 18.80%, which is nearer the garment's 17.5%.

That looked like smoothing helping, and it was the area. Growing the smoothed mask back to
22.0% with `MaxFilter(19)`, so the two masks cover the same and only the edge differs:

| Mask, both covering 22.0% | Boundary roughness | Green, the change | Stray |
|---|---|---|---|
| With a tremor | 1.86 | 21.35% | 21.4% |
| Smoothed, grown back to the same area | 1.33 | 21.63% | 21.4% |

The same spill either way. So the extent of what comes back is the area the mask covers and
not how its edge was drawn: smoothing is not a lever, and the earlier gain was the mask
being 3.1 points smaller. The changed-area measure above is confounded besides, coming out
at 52 to 57% of the frame because the noisy background re-renders above the threshold.

So the one thing that moves the spill is the area the user marks. That is why a finer brush,
a loupe on the print, and copy that says the whole marked area is repainted are the
improvements left, and not the wording, the colour, or the edge.

Three levers were measured against that and none of them moves it. The mask's colour does not (palette and white are the same on a textured frame). Naming the object's shape does not, 38.4% stray against 38.3% and 38.2%. Calling the colour a label does not, 38.3% against 38.4%. So the wobble in a hand-drawn region lands in the result, and the thing to attack is the quality of the boundary rather than the wording or the colour.

### The same metric on three scenes, measured 2026-10-06

Two of this file's figures read as a contradiction for a while. One harness scored a
six-step edit at 21 to 26x and another at 2.2 to 2.5x, on scenes believed to match, and
both reproduced bit-identically. One run settles it: every scene the two harnesses used
went through **one** metric, one seed, one prompt shape and one code path, on the M5 Pro,
and the two means are printed beside their ratio, because the ratio on its own hides which
of them moved.

| Engine | Scene | Steps | The mark covers | Inside | Outside | Ratio |
|---|---|---|---|---|---|---|
| Qwen-Image-2.1 | wall | 20 | 12.6% | 89.55 | 29.18 | 3.1x |
| Qwen-Image-2.1 | sign | 20 | 12.8% | 67.81 | 4.29 | 15.8x |
| Qwen-Image-2.1 | circle | 20 | 7.9% | 123.68 | 4.29 | 28.8x |
| Viggle Turbo | wall | 6 | 12.6% | 78.89 | 35.78 | 2.2x |
| Viggle Turbo | sign | 6 | 12.8% | 67.72 | 5.69 | 11.9x |
| Viggle Turbo | circle | 6 | 7.9% | 117.04 | 5.58 | 21.0x |
| Turbo, rebuilt scenes | wall | 8 | 12.7% | 104.67 | 2.10 | 49.8x |
| Turbo, rebuilt scenes | sign | 8 | 12.9% | 164.86 | 5.47 | 30.2x |
| Turbo, rebuilt scenes | circle | 8 | 8.0% | 164.89 | 5.77 | 28.6x |
| Qwen-Image-2.1, engine built directly | wall | 20 | 12.6% | 89.55 | 29.18 | 3.1x |

`wall` marks a patch of a uniform surface. `sign` marks a filled rectangle that has an
edge of its own. `circle` is the 2026-09-26 fixture, rebuilt from what this file records,
so it is a reconstruction and not the same run.

The three Turbo rows are this checkpoint's own, measured 2026-10-16 at its eight steps, on
scenes rebuilt the same way. Read them as the same method on different pictures, and not
as three more points on the rows above: the ratio is the mean change inside the mark over
the mean change outside it, so a flat scene with little outside the mark to move scores
high. The circle is the row to compare, because it is drawn as the 2026-09-26 fixture was,
which puts the mark's edge on the circle's edge exactly: Turbo holds the mark as well as
the twenty-step base model does, 28.6x against 28.8x, and better than the six-step
distillation's 21.0x. Its wall and sign read higher than every row above them, and that is
a statement about the reconstructions rather than about the mark.

Three readings, and none of them is a defect in a harness:

1. **The construction path is not a variable.** The wall scene through the composition
   root and through the engine built directly are bit-identical, inside 89.55 and outside
   29.18 both times. The two harnesses differed in that path, and it changes nothing.
2. **The scene is the variable, and the inside mean is not what moves.** Inside reads
   89.55, 67.81 and 123.68 across the three scenes, which is one kind of recolour each
   time. Outside reads 29.18, 4.29 and 4.29. The ratio divides by that, so the figure is
   a property of the scene: a mark on a uniform surface cannot bound anything, because the
   prompt names the wall and the model repaints the wall, marked or not. This file already
   said the concentration is fixture-dependent; these numbers are what that costs.
3. **Every figure this file and the README carry reproduces.** 15.8x, 28.8x, the 3.1x
   against the diffusers child's 2.4x, and the 2.2x and 21.0x that read as a
   contradiction. They were the wall scene and the circle scene, measured once each and
   set side by side.

What that means for the backend that was blocked on it: **six steps holds a mark as well
as forty does** where there is an edge to hold it, 21.0x against 28.8x, with the same kind
of recolour inside (117.04 against 123.68). Where there is no edge, neither engine bounds
it, 2.2x against 3.1x. A region figure is only ever a statement about the picture it was
taken on, and two figures from two scenes say nothing about either engine.

### The page path on Viggle Turbo, measured 2026-10-06

Every figure above comes from the engine, driven with the sentence and the palette the
page writes. The page's own path was never run on this backend: its tool and its brush
were checked against the stub. Three runs close that, on the M5 Pro against a
server on this backend, and nothing in them is a fixture. The page drew the scene, the
mark is a mouse stroke on the print, the sentence is the page's own, and the mask scored
is the one the page posted.

The scene is the prompt "a single flat orange circle centred on a plain light grey studio
background", 1024 x 1024 and six steps. The mark is drawn on the circle and the
instruction is "change the circle to blue". The run is one second under two minutes,
which is the load of the edit model and a six-step edit.

| Run | The mark covers | Inside | Outside | Ratio | What the mark covered |
|---|---|---|---|---|---|
| 1 | 15.7% | 127.9 | 29.4 | 4.4x | About half the circle |
| 2 | 16.2% | 155.1 | 18.9 | 8.2x | The circle, drawn one stroke per chord |
| 3 | 7.2% | 151.4 | 5.9 | 25.8x | As run 2, with a narrower brush |

The spread across the three is the mark and the scene, and not the path. Run 1 marked
half the object, so the rest of it counted as outside and the ratio fell to 4.4x. Run 3
is the shape the engine table records: 25.8x against the engine's 21.0x on the circle
scene, with the outside mean 5.9 against 5.58. Run 2 sits between them on the same
sentence and the same object shape, which is the same warning this file gives everywhere
else: one figure from one mark is not a property of the tool.

All three runs did the same thing to the picture. The whole circle came back blue,
including the part outside the mark, the grey background held, and the model's own
shading on the circle's rim stayed. So the mark reached the engine through the page, the
sentence named it, and the change landed on the object the mark was drawn over.

## The video templates

### How they were sampled

Eight templates were written for LTX-2.5, each rendered once at the model's own defaults:
121 frames, 24 fps, 1024 x 576, seed 7, no references, one clip each, the same flags the
studio's runner passes. A ninth clip carried the bare sentence "A woman in a red coat walks
along a beach at sunset", which is the subject of the first template without its direction,
so a template's effect could be told apart from the subject's own motion. Every clip was
then judged against what its own text promises, from six frames spread across it and from
four numbers: the change between consecutive sampled frames, the same for the top quarter of
the frame, the mean level, and, for the two keyframe templates, the distance from the still
they were given.

The top quarter is in the measure because a subject walking across a locked-off shot leaves
it alone: a strip that moves says the frame itself moved. That is what separates a camera
move from a walk.

Seed 7, the M5 Pro, one clip each. The clips cost 308 to 496 seconds each, 430.9 for
the first.

Four more clips followed. One re-sampled the light template with a different wording, and
three chased the frame the style template drew. Each one kept the same seed, the same shape
and the same fill-in, so a pair differs by the one clause that changed. They cost 389 to 471
seconds each.

### What works

| Template | Evidence |
| --- | --- |
| Camera move | The top strip moved 16.7 across the clip against the bare control's 3.9, and the whole frame 19.3 against 12.8. The frame moves and the subject stays framed |
| First frame | Frame 0 sits 3.52 of 255 from the still it was given, and the clip evolves from there |
| Last frame | The last frame sits 5.5 from the still against 12.8 at the first, so the ending converged on it |
| Product turn | The pot turns, stays centred, and the label "PEARL" is rendered and held across all six frames |

The control is the useful half of the sample. With no template the frame is locked off: top
strip 3.9, whole frame 12.8, and every change in it is the subject walking.

The style template's own words were rewritten after this sample, and that rewrite rests on a
number that belongs to another clip. Its first text opened "shot on [film stock or camera]
with [palette and light]", and that wording draws a frame the text never asked for: black
bands down both sides with rounded corners on the picture, like a phone upload. The outer 4%
band of the frame measures 5.6 on the left and 1.2 on the right, where the bare control
measures 107.3 and 81.2. Three wordings left it standing: a clause asking for the picture to
fill the frame (3.4 and 1.0), a fill that named an editorial style instead of a documentary one
(5.6 and 1.2), and the reworded stock clause on its own. The reading that fills the frame,
38.0 and 36.5, belongs to 13-style-nofilm, and its fill differs from its pair in more than the
stock clause: it says "in the warm natural colours and fine grain of Kodak Portra 400, in a
clean editorial style", where the other says "shot on Kodak Portra 400 film with warm natural
colours and fine grain, in a 1990s documentary style". Crediting those two numbers to the
stock clause alone was wrong.

The shipped text, which reads "in the [colours and grain] of [film stock or camera]", still
draws the frame. Measured 2026-10-18: 16-audio-style-stock reads 5.6 and 1.7, and its control
08-style-stock, filled the way the template invites, reads 5.5 and 1.7, and the contact sheets
of both show the black columns and the rounded corners. Taking the word film out of the fill
does not lift it: 17-style-no-word-film reads 5.6 and 1.8 against 16's 5.6 and 1.7, with every
other word, the seed and the shape held. So the template is not proven, and one clip that
fills the frame against five that do not is not enough to name the words that decide it.

That paragraph was rewritten again on 2026-10-18, when the clip that fills the frame was run
again beside its pair. Two clips, the stock clause held and the style phrase moved, everything
else the same, seed 7, 1024 x 576, 121 frames: `30-style-editorial-fill`, which reads "in the
warm natural colours and fine grain of Kodak Portra 400, in a clean editorial style", measures
5.3 and 0.9 on the outer 4% band, and `31-style-documentary-fill`, one style phrase away,
measures 5.2 and 1.6. Both are pillarboxed, so the style phrase does not decide it, and the
38.0 that 13-style-nofilm measured does not reproduce: the same clause and the same style
phrase draw the frame tonight. Seven of the eight fills sampled now sit between 5.2 and 6.1,
against a bare control's 107.3 and 81.2, and six wordings were tried, among them one that asks
the picture to fill the frame. So the frame is what asking a video prompt for a film look
does, and the template was dropped rather than offered with the fault. Its text is in
`prompt_aids.py`, where it sat, with this evidence.

### What did not, and why they are not offered

| Template | Evidence |
| --- | --- |
| Style and stock | Draws the film look and a frame the text never asked for: black columns down both sides with rounded corners on the picture. 5.2 to 6.1 on the outer 4% band for seven of eight fills, against a bare control's 107.3 and 81.2, and no wording lifted it. Dropped 2026-10-18 |
| Loop | First frame against last 14.72 while the palette matched to a point, so the content moved rather than the light. A seamless loop wants near zero |
| One action | One continuous shot, but the empty cup to full arc never read, and the camera drifted closer after being told to stay put |
| Light changes | Two wordings, and both lose on the camera. The first asked for a pan and brightened where dusk should darken: level 91.6 to 96.6, and the top strip 43 to 49. The second asks for the camera locked off and names no pan, and the top strip still moves 38 to 42 against the bare control's 1.7 to 2.0, while the picture drifts forward down the street. The level turns the right way this time, 79.1 to 76.7, so the words can name the direction; they cannot hold the camera |

The last frame template shipped with the sentence that failed removed: it promises the ending
still and says nothing about an empty opening, which the clip did not deliver.

### The sound direction, sampled 2026-10-18

Each of the five shipped templates was rendered again with a sentence that names what is
heard. The vendor's guide lists audio as one of the six elements of a video prompt, and the
model's own enhancer writes one on every enhanced run, which the shipped templates did not
invite. Every clip held its template's fill-in, its seed 7, its shape 1024 x 576 and its
length of 121 frames, so a clip differs from the one it is paired with by that sentence and
nothing else. One clip each, 330 to 444 seconds a clip.

| Template | With the sentence, against its pair without |
| --- | --- |
| Camera move | The frame still moves: the top strip 22.08 from first to last against 16.66, the whole frame 24.58 against 19.33 |
| First frame | The opening frame sits 3.48 of 255 from the still it was given, against 3.52 |
| Last frame | The ending sits 5.52 from the still against 5.50, and the opening 12.88 against 12.76 |
| Product turn | The pot turns, stays centred, and holds "PEARL" on every one of the six frames, as its pair does |
| Style and stock | The look is unchanged, level 89.1 against 90.2, and both frames are pillarboxed, which is the fault above and not this sentence |

The sentence costs no template its own promise. The soundtrack changed in all five pairs, by
the mean level of the audio track: 12-audio-camera-move is 2.5 dB louder than 01-camera-move,
and the other four run 6.2 to 32.9 dB quieter, the largest being 13-audio-first-frame at -61.2
dB against -28.3 dB. Every clip carries an AAC track either way, 5.01 seconds, so nothing is
lost to silence.

What these numbers cannot say is whether the words named the sound the model made. A level
says the track changed, not that the sea is the sea. Two things follow. The words are kept,
because they cost the picture nothing and the guide asks for them. And a person has to listen
before the words are trusted: "only the sound of the sea" left one clip all but silent, which
is a plausible reading of the words and a poor soundtrack.

### What this sample does not settle

- One clip per template, one seed. A template that failed here might pass on another seed,
  or on another fill-in: one of the three that failed was re-sampled once, and the style
  template, which shipped, three times.
- One length and one shape, both the model's defaults. Nothing here says what these words do
  at 2 seconds or at 640 x 384.
- The reference strength control was not sampled. Both keyframe clips used 1.0.
- The camera move template originally ended "Locked off on a tripod", which contradicts a
  moving camera, and the model drew a tripod standing in the sand. The shipped text drops it.

### The vendor's own example prompts, run once each, 2026-10-20

Ten prompts, one from the 2.5 prompt guide and nine from the vendor's published samples, were
sent to `/api/v1/videos/generate` with no template and no words of this studio's own. Every
clip ran at 384 x 384, 121 frames and seed 7 on the M5 Pro, 115 to 207 seconds each.
Each clip was judged on a contact sheet at 1:1, and the cuts and the audio were measured;
"change" is a spike in the frame difference that the sheet confirms is a cut, not a re-render.

| Prompt | What the clip did |
| --- | --- |
| Multishot (guide) | Cuts at frames 46 and 82: the wide of the yellow raincoat, the close-up under the hood, the man. The guide's example reproduces |
| Car race | One shot, no cut, and the sound follows the action at r 0.89 |
| Riad perfume | Three shot changes at frames 29, 64 and 82, in the order the words ask: courtyard, bottle, bronze silk, back to the wide |
| Carnival | One shot, dense saturated crowd, motion-audio r 0.87 |
| Vienna 1974 | Continuous; the man looks up on the beat. Audio rms 0.057, 0.33 of the energy in the speech band |
| Decanter pour | Locked off. One change at frame 67, the ice drop, not a cut |
| Ballroom | The transformation runs; one change at frame 94 when the dancers arrive, no camera cut |
| Flamenco | The scene and the light read; the dance is generic, not flamenco heelwork. Audio rms 0.40, a guitar-like peak at 221 Hz |
| Courtroom | The scene is right and the audio is silent, rms 0.0009. A quoted line in a video prompt made no speech in this run |
| Motorcycle | The turntable rotates through four angles, but the frame difference reads 0.34 because the set is black. The sheet decides, not the metric |

Two things this sample says about words. A multi-shot prompt can name its cuts and get them,
and a quoted line alone does not make the video pass speak: text to audio does, and the track
then drives the sound rather than the mouth.

## The seven LTX-2.5 effects on the q8 packs (2026-10-20)

The port's `ic-lora` task runs these weights on its single-stage path with the distilled
transformer. That path applies the reference at full resolution throughout, which is the
topology each card names. The default two-stage path applies the reference at half resolution
and drops it in stage 2, so it erases the change and tiles the frame.

An effect renders at the size and length its card trained at. Clean plate at 384 x 384 kept
the crowd; at 1024 x 576 and 49 frames it emptied the street. Each adapter carries its own
`width`, `height` and `num_frames`, and the controller and the form use them.

| Effect | Measured output | Verdict |
| --- | --- | --- |
| Day to night | 768 x 448, 97 | A daylight room becomes night: blue moonlight, lit windows, the dancer and the room held. 273.3 s through the API |
| Water simulation | 1280 x 704, 97 | A dry room floods: water across the floor and a splash at the feet. 958.8 s through the API. At 960 x 544 the same prompt added no water |
| Clean plate | 1024 x 576, 49 | Pedestrians gone, street rebuilt, light held |
| Deblur | 960 x 544, 121 | A soft clip comes back sharp, faces and flame detail hold |
| Decompression | 960 x 544, 121 | Edges clean from a crushed clip; colour unchanged |
| Restore | 960 x 544, 97 | Colour and detail return on damaged footage, with a warm cast |
| Upscale 2x | twice the clip | 384 to 768, faces, hands and the floor planks at 1:1. 399.1 s through the API |

The times are the studio's own run on the M5 Pro, with no other GPU job on the
machine: one clip, seed 7, one effect per request through `/api/v1/videos/edit`.

Water's card asks for 1920 x 1088. On the M5 Pro with 64 GB, that single-stage edit fails with insufficient Metal memory during reference encoding. The `--upsample-only` alternative writes a clip, but its frames contain dense noise and tiles. Neither run validates water at that size. Water stays at the measured 1280 x 704 pair.

The form offers 1920 x 1088 for generation. That does not validate edits at the same size. Deblur and decompression were trained at 960 x 544. Their cards name 1920 x 1088 for production, but only the trained pair has a valid measured result here.

With `fetch_loras = true`, the current runner fetched Deblur into an empty directory through `/api/v1/videos/edit`. The downloaded file matches the existing verified adapter byte for byte. Cancel returned 204, the edit returned `{"cancelled": true}`, and the engine child exited in 0.163 seconds. A separate server check confirms that Cancel stops a stalled download and releases the shared run lock.

Portrait checks use `/api/v1/videos/edit` on the M5 Pro with 64 GB, seed 7. Each check compares its first, middle and last frames with the input.

| Effect | Portrait output | Seconds | Visual result |
| --- | --- | --- | --- |
| Day to night | 448 x 768, 97 frames | 338.0 | Blue window light and darker walls replace daylight; the dancer and framing remain |
| Deblur | 544 x 960, 121 frames | 850.9 | The softened face, clothing edges and floor regain detail; the shot remains |
| Clean plate | 576 x 1024, 49 frames | 324.5 | The dancer disappears; the room, window light and floor remain |
| Decompression | 544 x 960, 121 frames | 544.0 | Blocks disappear from the damaged input; the face, hands and floor regain detail |
| Restore | 544 x 960, 97 frames | 633.1 | Noise falls and edges sharpen, but colour restoration is weak: the shot stays mostly grey, with pink hands |
| Upscale 2x | 768 x 1280, 121 frames | 986.1 | A 384 x 640 input gains sharper edges and floor detail at twice its width and height |
| Water simulation | 704 x 1280, 97 frames | 1376.9 | The dry floor floods, with standing water and splashes around the dancer's feet |

The day-to-night card asks 768 x 448 and 97 frames, which is what ships. Its first MLX run
looked like a failure because the test clip was already a torch-lit night street. On a
daylight clip the adapter relights.

The port's README still says 2.5 IC-LoRA is unsupported. That line predates Lightricks
publishing these adapters. The pipeline runs the topology the cards specify, and the runs
above are the evidence.

**Dub-It.** The 2.3 Dub-It LoRA works on the PyTorch 2.3 engine: the user judged the
2026-10-20 output perfect. The same LoRA on 2.5 weights loads but copies the reference's mouth
timing rather than retiming it. The MLX port has no Dub-It task; its LipDub entry is
experimental and re-syncs to source audio. Removing the PyTorch engine removed the only Dub-It
path, so Dub is deferred and would need that engine restored.


### LTX-2.5 speech and camera probes (2026-10-20)

Six sequential asynchronous API operations use seed 7, 384 x 384, 121 frames, and 24 fps.
The M5 Pro runs one GPU job at a time. Source digests match before and after every run.

| Probe | Seconds | Verdict |
| --- | --- | --- |
| Generated speech | 52.5 | Speech recognition returns the exact quoted sentence; mouth movement broadly follows the voice |
| Supplied speech | 396.9 | The supplied voice and timing remain; mouth movement broadly follows the voice |
| Fixed composition | 66.6 | Mostly stable, with small background drift |
| Slow push-in | 66.3 | Clear enlargement and foreground parallax |
| Sideways move | 66.9 | Partial: forward movement appears too, and the subject leaves the center |
| Clockwise orbit | 66.5 | Unproven: no clear new side of the object appears |

Only Speak to camera, Fixed composition, and Slow push-in become new LTX-2.5 templates.
LTX-2.3 keeps its existing templates. Tests reproduce the exact measured prompts from the new template fields.
The supplied audio correlates at 0.999686 with the padded input, with zero sample lag at 16 kHz mono.
This proves audio preservation, not exact lip alignment. No phoneme alignment score was measured.
Each prompt has one seed, so these results do not establish reliability across seeds.
