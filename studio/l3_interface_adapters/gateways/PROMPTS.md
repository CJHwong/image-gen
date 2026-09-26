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

Each option names what to show, never what to leave out. The exception is Real person: its avoid part goes to the negative prompt, which raises guidance to 2.5 and doubles the time of each image. Realism fights Watercolor, Ink drawing, 3D render and Skeleton, because its avoid part names CGI and 3D render. Real person is for people. For an animal, Documentary is enough: see "The avoid-part test". Edit mode has no Look, because the edit model already keeps the rest of the image.

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
