# Illustration, characters and assets

Use this file for stickers, icon sets, avatars, character sheets, comics, picture-book spreads,
coloring pages, tattoo flash, isometric scenes, 3D toy renders, game sprites and concept art. Read
[prompt craft](prompt-craft.md) first, and [style directions](style-directions.md) to choose the
visual language.

## Name the rendering method

The category word alone is too weak. Describe how the image is made:

- **Flat graphic:** "flat design, clean vector shapes, solid colors, no gradients, no texture".
- **Line art:** "clean black outlines of even weight on pure white, no shading, no fill" for a
  coloring page.
- **Tattoo flash:** "bold thick black outlines, flat solid fills of red, mustard and green".
- **Toy or 3D:** "glossy vinyl toy figure", "matte clay", "soft studio render", plus the whole
  figure in frame if the brief needs it.
- **Pixel art:** the grid size, the palette size and "crisp square pixels".

Keep realism words out of a stylized brief. Quality boosters pull the image toward a photo.

## Keep a character the same

A name does not hold a character. Write one fixed paragraph: age, build, hair, face, each piece of
clothing with its color, and props. Send that exact paragraph in every prompt of the set. For more
images of one character, make a character sheet first, then use it as an Edit reference for each
new scene.

## Panels, sheets and frames

Number the parts and give each one its own sentence: "Panel 1, left: ...". Describe an action in
the middle of the motion ("the mug is in mid-air, tipping"), not as a verb alone. For a sheet of
views, name each view: "front, side and back views, standing on one baseline".

## Craft, print and cut work

The model draws reference art, not a pattern. A countable grid, a closed cut path, a thread or bead
palette, stitch counts and measurements come from a script or a craft tool afterwards. Say so
before you start.

- Ask for flat fills, a named color count, no gradient, no shading and no texture.
- For print-on-demand, put the design on one flat color absent from the art, then key it out (see
  [delivery](delivery.md)). Check the design on the shirt color as well: dark text on a dark shirt
  disappears.
- For a stencil or a cut file, the model does not keep its islands connected. Threshold it, find the
  enclosed islands with a flood fill, and add bridges by hand.
- Radial symmetry is close, not exact. When it must be exact, mirror one wedge with a script.
- A technical flat is good for communicating a style. Count its details against the brief: the
  model adds plausible extras, such as pockets.

## Findings: illustration and assets

Qwen-Image-2.1-Turbo, 8 steps, guidance 1, seed 7, no Looks. One seed per case.

| Observation | Practical implication |
|---|---|
| A die-cut sticker, a 3 x 3 line icon set, a coloring page, a picture-book spread, an isometric diorama, a vinyl toy render and a three-view character sheet all followed their briefs. | These formats work from a plain, specific brief. |
| A three-view character sheet kept the same face, hair, armor and shield across front, side and back. | A sheet is a good first image for a character set. |
| An edit placed that character at a campfire with the same hair, armor, tabard and shield. | Use the sheet as an Edit reference for each new scene. |
| A pixel sprite sheet of eight walk frames gave eight identical clones in a 2 x 4 grid. Naming the pose of each frame gave varied strides in one row, but 6 frames instead of 8. | Name each frame's pose for variety. Do not promise a frame count or a clean cycle; treat the sheet as concept art. |
| A three-panel comic lost the panel 3 action when it was a bare verb ("the cat pushes a coffee mug off the desk"). Written mid-motion ("the mug is in mid-air, tipping, coffee splashing, his hand reaching too late"), the panel showed it, and the detective kept his fedora in all panels. | Describe each action mid-motion, and name the recurring outfit. |
| A 3D toy avatar lost the requested curly hair texture. | Inspect each named feature; a style can override one. |
| Rewrite pulled stylized briefs toward realism: tattoo flash, the toy avatar, the vinyl figure. A style sentence in front of the rewrite did not bring the style back. | Skip Rewrite for a stylized brief. |
| A 4 x 2 sheet of 8 game items came back as a 3 x 3 grid of 9: "gold coin pouch" split into a pouch and a coin. A tileset gave plausible tiles whose edges do not connect. | Name each item as one object. Treat item sheets and tilesets as concept art. |
| A 3 x 3 emoji set and a six-panel storyboard kept every member in order, and the storyboard kept the same character in each panel. | These sets are dependable. Check each member against its name. |
| Card art with "no card frame, no border and no text" came back as art only. | Ask for the art alone and add the frame and text in a layout tool. |
| A tarot card kept "XVII" and "THE STAR", a symmetric border and the right symbolism. Its star had about 12 points, not 8. | A title and numeral on a card are dependable. Count any symbol that matters. |
| A top-down battle map with "no grid lines, no perspective" came back as a true overhead view with every asked feature. | Generate battle maps gridless and add the grid in the tabletop software. |
| A token "seen from directly above" came back as a front bust portrait in its ring, at about 40% of the frame. | Ask for the token to fill most of the frame; expect a portrait token. |
| A tileable cobblestone texture had even light and uniform stones, but the 2 x 2 tile showed a cut at both seams. | Tile every texture 2 x 2 before you use it. Heal the seam in an image editor: offset by half, then clone or fill the cross. A marked Edit of that cross tinted the whole texture orange. |
| A visual-novel sprite came back full-body on pure white with room above the head. | A good base for an expression set by Edit. |
| A t-shirt graphic on green kept "SALT & SUN" and flat colors; keyed on its sampled green it cut out clean. | The chroma-key recipe works for print-on-demand art. |
| A spray-paint stencil "with every island bridged" had five floating white islands (the eye and the inner ears), and three and ten on two more seeds. | Check islands with a flood fill; bridges are a manual step. |
| A 12-fold mandala had real 12-fold structure: a 30 degree turn differed half as much as an off angle. | Usable for coloring; mirror a wedge for exact symmetry. |
| A denim jacket flat was symmetric with dashed stitching, chest pockets with flaps and button cuffs, plus two hand pockets nobody asked for. | Count the details of a flat against the brief. |
| A tavern battle map held exactly four tables. Six spell icons kept identical badges but came out 2-3-1, not 3 x 2, and the poison drop was red. | Small counts hold; grid layouts drift. Name each icon's color. |
| A ditsy fabric print "with every flower inside the frame" still cut flowers at its seams, though its seam difference (8) was far below the cobblestone texture's (19 to 24). | Small tossed motifs tile better; still tile 2 x 2 and heal the seam in an image editor. |
| A pixel-art corgi for cross-stitch had 548 colors at 48 x 48 before quantizing and a coarser grid than asked. | Quantize to the thread palette and set the grid in a script. |
| A fine-line tattoo kept thin even lines and "carpe diem" in script. A planner sticker sheet kept six separate die-cut stickers. | Both dependable. |
| An "equirectangular 360 panorama" came back 16:9 with the horizon centered; its left and right edges nearly met. | Usable as a wrap-around backdrop strip, not as a 360 sky. |
