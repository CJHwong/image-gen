# Delivery

The server returns an sRGB PNG with no alpha channel, at about 0.25 to 1.8 MP on Qwen-Image-2.1-Turbo. Anything else
(transparency, vector, print size, a platform's exact pixels) is a step after the model. Ask for
the end use before you generate, because it changes the background, the margins and the size.

| End use | Generate for it | Step afterwards |
|---|---|---|
| Transparent PNG, sticker, product cutout | One flat color far from the subject's colors, no shadow, wide margin, nothing touching the frame | Clip the background to its exact color, then matte (rembg, BiRefNet, macOS Lift Subject, Photoshop Select Subject) |
| Vector logo, print-on-demand | Flat fills, 2 to 6 colors, thick even strokes, no gradient or texture, no text | Trace (vtracer, Potrace for one color, Illustrator Image Trace), clean the paths, set the text in a real font. Bold shapes trace clean; thin strokes break into blobs of edge color |
| Print | The largest size of the shape | Check the print size below; upscale before you convert to CMYK |
| A platform post, banner or icon | The nearest offered ratio, with the subject inside the safe area | Resize or crop to the platform's pixels |
| Web | Any | JPEG or WebP for photos, PNG (quantized) for flat graphics; keep sRGB |

## Cutout recipe

1. Generate on pure white, or on pure magenta (#FF00FF) or green (#00FF00) when the subject is white
   or pale. Ask for "no shadow" and an even margin on all sides.
2. Sample the background before you key it. The model does not hit a hex: #FF00FF came back about
   (223, 7, 176) and #00FF00 about (28, 212, 0), both flat. A "pure white" cutout edit came back at
   245 to 252 with no pixel at 255. Key on the sampled color, or clip near-white to 255.
3. Key a flat color, or matte (rembg's default model is a 1 GB download), then look at the edge on a
   dark and a light backdrop for a fringe in the old background color. A keyed token and a keyed
   t-shirt graphic both came out clean, with a faint fringe on the token's rim.
4. Glass, smoke and fine hair lose their partial transparency in a matte. Say so.
5. For a person, matte the original photo. Do not swap the background to a key color first: a
   portrait edited onto magenta and keyed kept a magenta fringe all along the dark hair, while rembg
   on the original gray background gave a clean hair edge.

## Icons and avatars

- An app icon asked "full bleed, no rounded corners" drew its own rounded square with white
  corners on five images, also with that negative prompt at guidance 2.5. Described positively
  ("the blue reaches all four edges and all four corners; a plain full square with sharp square
  corners"), it came back full bleed on both seeds.
- An avatar asked for "a wide even margin for a circle crop" came back in profile and off center.
  With "facing the camera and looking straight at the viewer, her face exactly in the center", it
  came back frontal and centered on both seeds.

## Text and logos for real use

The model's lettering is a mockup. For a logo, a print product, or any copy longer than a headline,
generate the art without text and set the text in a layout tool with a real font. The same holds for
exact brand colors, QR codes, barcodes, grids, rulers and cut lines: add them with a tool.

## Print size

DPI is a label; the pixels decide. Print width in inches = pixels / ppi. Use 300 ppi for a print
held in the hand and 150 ppi for a poster seen from a distance.

| Pixels (largest offered) | At 300 ppi | At 150 ppi |
|---|---|---|
| 1328 x 1328 (1:1) | 4.4 x 4.4 in (11 cm) | 8.9 x 8.9 in (22 cm) |
| 1104 x 1472 (3:4) | 3.7 x 4.9 in | 7.4 x 9.8 in |
| 1664 x 928 (16:9) | 5.5 x 3.1 in | 11.1 x 6.2 in |
| 1536 x 1024 (3:2) | 5.1 x 3.4 in | 10.2 x 6.8 in |

An upscaler (Real-ESRGAN, Upscayl, Topaz) multiplies those by 2 or 4, but it invents detail and can
change letters and logos. Inspect text at 100% after an upscale. A printer that wants CMYK gets an
ICC conversion (for example FOGRA39 or Japan Color 2001) after the upscale; saturated cyan, green and
orange go duller. Many print-on-demand shops want sRGB and convert themselves, so ask the printer.

## Platform sizes

Generate at the nearest offered ratio with the subject inside the safe area, then resize. Sizes
change often. The values below come from each platform's own pages as of October 2026; the rows
marked "check" had no official page that could be read, so open the platform's help page first.

| Target | Pixels | Note | Source |
|---|---|---|---|
| Open Graph link preview (Facebook, LinkedIn, others) | 1200 x 630 (1.91:1), at least 600 x 315, under 8 MB | Keep text in the center | Meta developer docs |
| Pinterest pin | 2:3, for example 1000 x 1500 | | Pinterest help |
| Google Play icon | 512 x 512 PNG, under 1024 KB | | Play Console help |
| Android adaptive icon | 108 x 108 dp layers, 66 dp safe circle | Keep the subject inside the circle | Android developers |
| YouTube thumbnail | 3840 x 2160 recommended (16:9); 1280 x 720 still accepted | Under 2 MB from the phone app, 50 MB on desktop. The timestamp covers the lower right | YouTube help |
| YouTube channel banner | At least 2048 x 1152; safe area 1235 x 338 in the center | Only the center strip shows on every device | YouTube help |
| Instagram and Facebook Reels ad | 1440 x 2560 (9:16) | Keep text out of the top 14%, the bottom 35% and 6% on each side | Meta ads guide |
| LINE sticker | At most 370 x 320, even sides, about 10 px margin, PNG with transparency, under 1 MB; sets of 8, 16, 24, 32 or 40; main 240 x 240, tab 96 x 74 | Make one sticker per image: a single sticker kept its caption inside the border, an 8-sticker sheet put every caption below its sticker | LINE Creators Market |
| LINE emoji | 180 x 180 | | LINE Creators Market |
| Instagram feed post | check: 4:5 (1080 x 1350) and 1:1 are common; newer help text may allow up to 3:4 | | check |
| Stories, TikTok (organic) | check: 9:16, commonly 1080 x 1920 | Use the Reels ad safe zone above as a cautious default | check |
| X header, LinkedIn cover | check: commonly 1500 x 500 (X) and 1584 x 396 (LinkedIn) | Profile pictures cover the lower left | check |
| App Store icon | check: commonly 1024 x 1024 with no transparency | The system rounds the corners; do not draw them | check |

A target larger than the model's largest size of that shape (a 3840 x 2160 thumbnail, a 1440 x 2560
Reels ad) needs an upscale; see "Print size" above for its limits. A smaller target only needs a
resize.

## Sets

Use the same background, margin, cutout settings and export size for every member of a set. Make the
set from one approved master with Edit (see [editing](editing.md)), and check each member against it.

## Names, records and alt text

- Name files `subject-purpose-size-v01.png`, with no spaces.
- Keep the request, seed, model, references and edits next to each keeper. The studio's gallery
  keeps them for its own outputs.
- Alt text is one sentence about what is shown. Quote any text in the image word for word. Do not
  paste the prompt. A purely decorative image gets an empty alt.
