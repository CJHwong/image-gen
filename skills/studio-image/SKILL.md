---
name: studio-image
description: Create and refine still images with Open Imagine's Image API. Direct composition, camera angle, framing, lens and lighting effects across photography, historical art, fantasy, anime, and illustration. Also covers images that carry text or layout (posters, covers, logos, app screens, infographics, packaging, signs, memes), characters and game assets, and reference edits such as restoration, composites and try-on. Use for shoots, coherent image sets, visual exploration, and reference-based edits with visual review.
---

# Studio Image

Turn a brief into still images that work together, then inspect and refine the actual images.
Operate the user's Open Imagine server through its public API. Keep this workflow usable with
different Image models; discover their capabilities rather than assuming a particular checkpoint.
Requires a reachable server and tools for HTTP, saving images, and visual inspection.

## Choose the path

If the request is short or vague ("a nice photo of my dog"), or the user says they do not know where
to start, follow the [guided flow](references/guided-flow.md). It asks at most three plain
questions, scouts four looks from the [look index](references/look-index.md), and makes the final
from the scout the user picks. A user with a full brief (subject, use, style) continues below.

## Establish the shoot

Use the user's server URL; otherwise try `http://127.0.0.1:8765`. Read [the API operating
notes](references/studio-api.md) before submitting work. If the server is unavailable, report the
connection problem; starting or installing a server is a separate task unless already authorized.

Extract the subject, intended use, deliverable count, aspect ratios, and visual direction from the
brief. Identify what must remain exact: a face, product silhouette, label, material, garment, or
supplied composition. Use sensible defaults for missing creative details; ask only when an unknown
changes the requested result materially. Respect the user's generation/time budget. A request for
one finished image does not imply permission for an extensive scouting batch (the guided flow's four
small scouts are its normal start, not an extra batch).

Give each reference a role: subject identity, product geometry, wardrobe, lighting, pose, or layout.
Refer to images in their submitted order using the selected model's supported wording. Distinguish a
reference's required content from incidental background details. If a supplied product or person
must remain recognizable, prefer reference-based Edit over reinventing it from text. Do not claim
exact brand or identity fidelity without inspecting the result.

Before you write the prompt, check the request against [boundaries](references/boundaries.md) if it
involves a real person, a document, someone else's work, a brand or a mark, health, or news. Check
it before Rewrite, because Rewrite carries the request into a longer prompt.

Ask for the end use (screen, print, sticker, platform, vector, cutout) when the brief does not imply
it, and otherwise state the end use you assume, because it sets the background, the margins and the
size; [delivery](references/delivery.md) has the recipes. Split the job: the model makes the
picture, and a layout tool or script adds what must be exact (long copy, exact colors, QR codes,
grids, counts, cut lines, the final pixel size, transparency).

Place each request on one accuracy tier, and tell the user which:

- **Decorative.** Mood, style and composition. The model is fine.
- **Plausible.** History, botany, products, architecture: it looks right and needs a human check
  before anyone relies on it.
- **Exact.** Data charts, maps with real geography, anatomy for teaching, floor plans, math and
  chemistry figures, sewing patterns. Draw these with code or CAD, not this model.

## Direct and generate

Find the brief's kind of image in [use cases](references/use-cases.md). It names the file to read, a
default ratio, and whether Rewrite helped on the tested model. Before you write a custom prompt or
use Rewrite, read [prompt craft](references/prompt-craft.md). For an image that carries words or a
layout, read [design and text](references/design-and-text.md). For stickers, icons, characters,
comics, sprites or other drawn assets, read [illustration and
assets](references/illustration-and-assets.md). For any Edit, read [editing](references/editing.md).

For composition, viewpoint, framing, focus, camera effects, lighting, or subject staging, read [shot
design](references/shot-design.md). Treat these as independent decisions from style. Choose the
visible outcome first, then use compatible camera shorthand to support it. Camera numbers in prompt
text are creative cues, not calibrated API controls or proof of an actual capture setup. Keep them
separate from discovered engine settings.

For a real-camera brief, direct a credible setting, material condition, motivated light and degree
of processing. Inspect skin, hands, object joins, reflections and fine texture at full size.
Photographic appearance and obeying the requested shot are separate checks; a convincing portrait
can still miss its crop or lighting pattern.

For photography beyond portraits, a named camera brand, or an in-camera processing look, read
[photography genres and camera cues](references/photography-genres.md). Use the genre's actual
subject and capture constraints to direct the image; a camera name alone does not establish its
optics, sensor response, or proprietary color processing.

To pick a tested look (an art style, an animation school, a film stock, a lens, a director's way of
shooting, a light), use the [look index](references/look-index.md): each row gives the prompt
sentence that worked and what to watch for. For style exploration or a nonphotographic brief, read
[style directions](references/style-directions.md). Choose a specific visual language and describe
its marks, space, palette, and material. Do not append photographic realism to painting, anime, or
abstraction unless the user wants a hybrid. Separate a movement, a medium, a genre, and a production
technique rather than treating their names as synonyms.

Choose an offered template when it fits; fill its actual fields with the brief. Choose Looks
deliberately rather than filling every row. Avoid contradictory camera or lighting instructions. For
a custom prompt, describe subject and action, framing, setting, light direction and quality, surface
detail, and placement of any empty space or exact lettering. State preservation and change
instructions explicitly for edits. Use the selected model's official guidance linked from the live
API documentation when its prompting behavior matters.

For a coherent set, hold the subject or location, palette, light logic, and treatment steady while
varying the requested shot: hero, detail, contextual scene, or alternate crop. A repeated seed does
not guarantee the same identity. Once there is a good hero, use it as an Edit reference for
dependent variations. Generate those only after reviewing that hero. For architecture, preserve the
defining materials, openings and layout; a reference image does not establish the geometry hidden
behind its visible surfaces.

Tell the user before you start when the brief needs something the tested model did not do. On
Qwen-Image-2.1-Turbo (on another backend, treat this list and every Findings table as hypotheses to
check on a scout):

- No transparent background. Generate on pure white and cut it out afterwards.
- No guaranteed seamless repeat. Keep motifs inside the frame, then tile 2 x 2 and check.
- No usable animation frames. A sprite sheet is concept art.
- Edit cannot zoom out or extend the canvas.
- Rare or technical Chinese, Japanese or Korean characters come out malformed at any size.
- Technical diagrams look right but are not accurate. Do not use them as reference material.
- Chart bars are not proportional to their values. Draw a data chart with code.
- Grid counts drift. A sheet of 8 icons can come back with 9, and tiles do not connect.
- Quoted names can lose their letter order ("Sheryl" came back "Sherly"). Check names letter by
  letter.
- Small Japanese, Korean or Arabic lines come out with wrong characters, even when the headline
  above them is exact. Set small non-Latin copy in a layout tool.

Use a small scout when the brief and budget allow it. Compare one meaningful variable at a time when
testing a look. Keep known settings and seed fixed for a controlled comparison. A smaller scout
helps composition decisions but cannot prove fine text or final-resolution detail. If the user
declines a scout, tell them which looks in the brief the look index marks partial or does not list,
and what to watch for in the final. Changing dimensions can change composition; do not describe a
new render as a pixel upscale.

Batch independent shots with one backend when useful. Do not put an edit that needs an earlier
output into the same batch: the reference bytes do not exist yet. Save requests and operation IDs
before continuing, and download completed images promptly, including partial successes.

## Inspect, select, and refine

Inspect saved images, not just API status. A contact sheet helps choose a direction; inspect keepers
individually at full size for the details that matter. Check against the brief:

- Subject identity, product shape, proportions, label spelling, and material finish.
- Hands and contact points, plausible shadows/reflections, duplicated or merged objects.
- For complex scenes, exact inventories, containment and object-to-object relationships; separate
  physical objects from their reflections and occluded parts.
- Framing, edge cutoffs, intended aspect ratio, useful copy space, and readable exact text.
- Requested camera height and viewpoint, relative object scale, focus target, blur direction, and
  the light/shadow arrangement; do not infer adherence from a lens name in metadata.
- Consistency across the set without accidentally repeating every composition.

Adapt these checks to the intended language: flattened space or distorted anatomy may be deliberate.
Judge whether the image follows the chosen direction before calling those defects. For style
comparisons, assess the rendering method separately from subject retention.

Keep the chosen original. Make a targeted edit with a concrete change and explicit preservation
instructions; compare it with its source. A language instruction to change a region is not a mask.
Where the mode offers region marking, a mark places a change precisely (see
[editing](references/editing.md)), but it does not protect the rest of the frame either. Do not
promise that pixels outside any edit stay unchanged.

Stop when the requested set meets the brief or its budget is exhausted. Report remaining defects
instead of silently launching more attempts. Preserve successful items if a later item fails.

## Deliver

Save keepers with descriptive filenames and report their paths, dimensions, and useful selection
notes. For a multi-image shoot, keep a compact record linking each keeper to its request,
operation/item ID, seed, reference files, and edits; retain the original references. A simple
single-image task only needs enough provenance to reproduce or revise it. Separate requested finals
from scouts and rejected attempts. Mention unresolved fidelity or text issues. Use local links or
the user's requested destination; publishing is a separate action. Run the post-steps the end use
needs (cutout, trace, resize, upscale, alt text) from [delivery](references/delivery.md), and say
which ones you ran and which the user still has to.
