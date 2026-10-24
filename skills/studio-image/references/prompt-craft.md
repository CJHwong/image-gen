# Prompt craft and Rewrite

These rules cover how to write a prompt for any kind of image. The findings tables come from
Qwen-Image-2.1-Turbo. For another backend, treat them as hypotheses and check them on a scout.

## Write the prompt as an observer

The official Qwen prompt enhancer (the PE-T2I system prompt) writes prompts in a fixed shape.
Prompts in that shape follow the model's training distribution, so use it for custom prompts:

1. The first sentence names the medium, the style, the subject and the background. For example:
   "A flat vector infographic on a white background shows four steps of a heat pump."
2. Then walk the frame with positional phrases: "at the top", "in the lower left", "behind her".
3. Put every legible string in straight double quotes, written exactly as it must appear, in its
   own script. Case, spelling and line breaks follow the quoted string.
4. Give one sentence to light, and close with one sentence on composition and framing.
5. Name colors with a modifier ("muted sage green", not "green"). Name each item of a set.
6. Name a brand only when the user named it.

Describe what you want, not what you want to avoid. Do not add quality boosters such as
"masterpiece", "8K" or "ultra detailed".

## Findings: prompt wording

One seed per pair. A difference is a lead, not a law.

| Observation | Practical implication |
|---|---|
| Quality boosters ("Ultra HD, 4K, cinematic, masterpiece") turned a flat vector bicycle into a photoreal 3D render. | Never append boosters, least of all to graphic work. |
| "No clutter, no props" grew an unrequested brand mark; a described plain background did not. | Phrase the background positively. |
| Bare "illustration" gave a painterly scene. "Flat design, clean vector shapes, solid colors, no gradients, no texture" gave a true flat graphic. | Name the rendering method, not the category. |
| Counts held up to seven, loose or in a row. "Four different fruits" gave two apples; naming banana, orange, pear, grapes gave exactly those, in order. | Give a count and name every member of a set. |
| A character name ("Mira the inventor") changed nothing across three prompts. One repeated full description (age, hair, goggles, jacket, overalls, shoes) held the same character in all three. | Re-send the identical character paragraph in every prompt. |
| "Transparent background" gave white with a floor shadow; "pure white background, no shadow" gave a cleaner white. Neither has an alpha channel. | Ask for pure white and cut it out afterwards. |
| "A die-cut sticker of ..." first gave a flatter, cleaner sticker than the same noun at the end. | Lead with the artifact noun. Small effect. |
| The same night-market scene written in Chinese and in English both gave a good photo of the right dish, steam, bulbs and crowd; the Chinese one framed a closer shot. | A Chinese prompt is fine for picture content. For text in the picture, use an English carrier with quoted strings (see [design and text](design-and-text.md)). |
| Asking for a hex color (#FF00FF, #00FF00) gave a flat background of a nearby color, not the hex. | Use a color name for the look; sample the real color before you key it out. |
| "No rounded corners" drew rounded corners on five images. A negative prompt for them at guidance 2.5 changed nothing against a neutral negative, on two seeds, and doubled the time. "Sharp square corners; the blue reaches all four corners" worked on both seeds. | Describe the wanted shape. Do not spend a negative prompt on it. |

## Rewrite

The studio's Rewrite runs the official prompt enhancer on the server. Submit
`{"kind": "rewrite", "backend": ..., "mode": "generate" | "edit", "prompt": ...}` to
`/api/v1/operations`, with the same fields as the image request; for an edit, also send the
`references`. It follows the same submit, poll and fetch flow as an image, and it counts as the one
running operation, so it can also get a `409`. The result holds `prompt` and a suggested `size`,
with no `images`. Rewrite only returns text; read it, fix it, then submit the generation yourself.

Rewrite is worth the time when the brief is short and the layout carries copy or a story. It
hurts when the brief already fixes a style or exact text. After a rewrite, check five things:

1. **Every quoted string survives, in its case.** The rewriter uppercased "Ember & Oak" and split
   "1 Absorb outdoor heat" into a number and a label, and the image then lost all four labels.
2. **Invented copy is acceptable.** It fills a UI, a label or a map with real words instead of
   gibberish. It also adds titles and signs nobody asked for. Remove what the user would not want.
3. **The style is still the user's style.** It drifts toward realism, and one style sentence put
   back in front of the rewrite did not steer it. Delete the realistic descriptions inside the
   rewritten text (skin, fur, feathers, lighting realism), or keep the brief.
4. **The text is a prompt.** The model sometimes writes a quote without its backslash, and the
   server repairs that. If the result still starts with `{"rewritten_prompt": "`, take the
   prompt text out of it and remove the backslashes before you use it.
5. **The size fits the format.** It defaults to 3:2 landscape, even for a poster or a book cover,
   and returns no size when the ratio has no offered size. For an edit it never returns a size.
   Choose the size, or the edit's `resolution`, yourself.

## Findings: Rewrite, 29 briefs against their rewrites

Same seed, the brief's own ratio, with each image inspected side by side.

| Observation | Practical implication |
|---|---|
| Rewrite was better on 12, the brief on 6, and 11 were ties. | Rewrite is not a default. Use it for the cases below. |
| Rewrite won where unquoted copy had become gibberish (app UI, packaging, tech diagram), where a scene or an action was lost (Chinese street sign, comic panel 3) and where items overlapped (flat lay). | Use Rewrite for dense layouts and for briefs with a story. |
| The brief won on stylized looks: tattoo flash went naturalistic, a 3D toy avatar became a semi-real person, a vinyl toy was cropped and went realistic. A style sentence put in front of the rewrite left the tattoo almost unchanged and the avatar unchanged. | For a stylized brief, skip Rewrite or edit the rewritten descriptions. |
| The brief won on text: the logo's case changed and the infographic lost its step labels. | Check every quoted string in the rewritten text before you generate. |
| A rewrite took 15 to 45 s on an M5 Pro with the 8-bit enhancer. | Batch the rewrites, and do not rewrite every scout. |
| Three Chinese briefs came back as English prompts with the quoted Chinese kept exactly. A Traditional Chinese poster brief got an invented subtitle in Simplified Chinese. | Chinese briefs are fine. Delete invented CJK copy, or quote the copy you want. |
| A brief naming two living animators, a celebrity endorsement, a national ID card and a watermark removal were all rewritten without objection. The names and the ID fields went into the longer prompt; only the watermark words were dropped. | Rewrite applies no boundary check. Run the [boundaries](boundaries.md) check before it. |
