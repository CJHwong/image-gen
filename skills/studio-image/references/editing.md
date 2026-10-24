# Editing with references

Use this file for any Edit: background swaps, removing or adding objects, restoring or colorizing
old photos, season and time-of-day changes, restyling, sketch to render, text replacement and
translation, expression changes, composites, try-on, and new scenes for a known character.

## Write the instruction

1. Say the one change, concretely: what changes, where, and how it looks.
2. Then say what stays: "Keep the pouch, its label, shape and color exactly as they are."
3. Name the place for an addition in terms of the image: "on the left seat cushion, against the
   left armrest nearest the window", not "on the left".
4. For text, quote the old and the new strings, and ask for the same font, size and color.
5. Edit one thing per run. Chain edits when you need several changes, and check each result.

An edit is not a mask. Pixels outside the change can move a little. Compare the result with its
source before you call it done.

## Several references

Give each reference a role in the prompt: "the coffee pouch from Image 1", "the room in Image 2".
"Image 2" and `<image2>` worked the same. Numbers follow the submitted order, from 1, and a
region mark is the last image.

The output takes its frame from the **last** reference when `resolution` is "match". Put the
image whose frame you want to keep last, the room in a composite and the person in a try-on, or
set `resolution` yourself.

## Mark a region

When the mode's `region_marking` (under `modes[]` in the backend's capabilities) is true, a mark can say where a change goes. Send the
picture first and the mark last, with `mask: true`. The mark is an opaque PNG at the picture's size:
black everywhere, and the area filled with one of the page's named colors (orange `#e2761e`, red
`#e2381f`, green `#2f9e4f`, blue `#2f6fe0`), hard edged. Name the area by its color and the mark's
image number: "Add one black cat curled up asleep in the orange area of <image2>. Keep the
background and everything else unchanged." See [the API notes](studio-api.md).

The mark is a reading aid, not a hard mask. A marked addition landed exactly in the area. A marked
removal of "the potted plant in the orange area" also stripped a second potted plant outside it. So:

- Use a mark to place an addition or a change precisely.
- For a removal, also name the object by its place, and compare the whole frame with the source.
- Paint the mark a little larger than the object: the brush width is the only precision.
- Keep the mark compact, over a small share of the frame. A cross-shaped mark through a whole
  cobblestone texture came back with the entire texture tinted orange. Compact marks over one
  object did not leak their color.

## Limits

- Edit has no canvas size, so "zoom out" cannot add space around the frame. Generate a new image
  for a wider view.
- Rare CJK characters in an edit come out malformed at any size. Check every character.

## Findings: edits

Qwen-Image-2.1-Turbo Edit, 8 steps, CFG 1, seed 7, resolution "match". 16 edits, one seed each.

| Observation | Practical implication |
|---|---|
| Background swap, object removal, photo restoration, colorization, season change, watercolor restyle, sketch to product render and an expression change all passed while keeping identity and layout. | These are dependable single edits. |
| Replacing "NORTHERN LIGHT" with "SOUTHERN SEA" kept the font, size and every other element. | Text replacement is dependable for a quoted Latin string. |
| A translation to Traditional Chinese got the title exact, but malformed 外, 縮 and 環 in the step labels. Asking for large bold text gave the same errors. | Check each character. Set rare CJK words in an editor afterwards. |
| "Add a cat on the left end of the sofa" put the cat in the middle. "On the left seat cushion, against the left armrest" moved it to the left cushion, not to the armrest. | Naming nearby objects helps only partly. Use a region mark for exact placement. |
| "Zoom out" shrank the figure only a little. | Use a new generation for a wider frame. |
| A pouch-into-room composite and a jacket try-on came back square when the 1:1 product was the last reference. With the room or the person last, each kept its own frame (1152x864, 864x1152) and the product details. | Put the frame you want to keep last. |
| An ad localized by Edit into German kept every line exact. Into Japanese, Korean and Arabic the large headline was exact, but the small line and the button had wrong characters or letters. | Localize headlines by Edit. Set small non-Latin lines in a layout tool; have a native speaker check. |
| A logo (Image 1) printed onto a plain mug (Image 2, last) kept every letter of "Ember & Oak" and the mug's frame; it sat almost flat on the curve. | Logo placement works; check the curve and the letters. |
| A mug colorway, a hair color change, emptying a furnished room, a pet photo to a chibi sticker, a street photo to line art and a back view of a jacket flat all kept what was asked and changed only the target. | Dependable single edits. Chain them from one master for a set. |
| A couple photo restyled to watercolor kept both faces, but the faces stayed close to photographic while the background went fully watercolor. | Ask for the style on the faces as well, and check likeness. |
| A visual-novel sprite took a happy expression, then an angry one with hands on hips, with the outfit and proportions kept each time. | Build an expression set by editing the one neutral master. |
| A cutout to white kept the mug and its logo, but the border came back near-white (245 to 252), with no pixel at 255, and a soft contact shadow. | Clip near-white to 255 before you cut out or place the image on white. |
| A relight to evening, with a floor lamp named as the light source, kept the room's layout and every object. | Relight is a dependable single edit. Name the light source. |
