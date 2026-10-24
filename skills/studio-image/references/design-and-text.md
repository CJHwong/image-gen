# Design and text

Use this file for an image whose job is to carry words or a layout: posters, covers, invitations,
thumbnails, logos, lettering, signs, menus, app screens, infographics, diagrams, maps, packaging,
merchandise and memes. Read [prompt craft](prompt-craft.md) first.

## Get the words right

1. Quote every legible string, exactly as it must appear. Case, spelling and line breaks follow
   the quote.
2. Every visible slot needs real copy. An unquoted label, menu, UI row or packaging panel renders
   as gibberish. Write the copy yourself, or use Rewrite to invent it and then check it.
3. Say where each string goes and how large it is: "a large bold title across the top", "a small
   line under it", "the date in the lower left".
4. End with "No other text." when the layout must not grow extra words.
5. For Chinese, Japanese or Korean, write the prompt in English and quote the strings in their own
   script. Common words render well; rare or technical characters fail at any size. Check every
   character at full size.
6. Inspect the text at full size, letter by letter, and compare it with the brief. A green
   operation status says nothing about spelling. Proper names need the closest look: a quoted
   "Sheryl" came back "Sherly" on three seeds out of three, so a new seed does not fix a misspelled
   name. Fix it with an Edit text replacement or in a layout tool.
7. For vertical Chinese text, say "running top to bottom". For a horizontal line of Chinese, the
   model picks the reading direction itself. Asked "from right to left", one banner in three came
   back scrambled. With no direction, all three were correct, one written left to right and two
   right to left. Give no direction, then check which way the result reads. An Edit that names the
   characters and the direction ("so they read "吉祥如意" from left to right") fixed a scrambled banner.

## Set up the layout

- Name the artifact and its format in the first sentence: "A vertical A3 gallery poster", "A
  phone screen of a banking app", "A flat vector infographic".
- Give the hierarchy: what is largest, what is secondary, what is small print.
- Give the grid when one exists: "four steps top to bottom", "a 3 by 3 grid of icons".
- Choose the size from the format: 3:4 or 2:3 for posters, covers and invitations, 16:9 for
  thumbnails and slides, 9:16 for phone screens, 1:1 for logos, icons and stickers.
- For a logo or an icon on white, ask for "pure white background, no shadow" and cut it out
  afterwards. The model writes no alpha channel. See [delivery](delivery.md).
- For copy space, name the empty area and what fills it: "the left half is a plain, empty, very
  light gray area". A top band stays empty reliably. A bottom band filled with the subject on four
  images of five, so pad or crop the bottom afterwards.

## Findings: design and text

Qwen-Image-2.1-Turbo, 8 steps, guidance 1, seed 7, no Looks. 36 of 38 quoted strings in 30 briefs
rendered exactly. One seed per case.

| Observation | Practical implication |
|---|---|
| Quoted titles, dates, names and short taglines rendered exactly on posters, covers, invitations, thumbnails, mugs and lettering. Six short lines on one card were all exact. | Short quoted text is reliable. Spelling it letter by letter is not needed. |
| Unquoted copy became gibberish: the app UI rows, the packaging small print, a diagram label and menu items. | Quote or remove every slot. Rewrite filled a UI with 21 real strings. |
| A fantasy map misspelled one place name ("Aashford" for "Ashford"). | Check proper nouns letter by letter. |
| A Chinese street sign rendered 阿嬤的滷肉飯 exactly, but the framing lost the street. | State the scene around the text as well as the text. |
| An all-Chinese prompt rendered the simplified 费 in 免費 on three seeds of three. An English prompt with the same quoted strings kept the traditional 費 on all three. | Use an English carrier with quoted CJK strings. |
| A Traditional Chinese infographic about a heat pump malformed 泵 and 作 in the large title, and four of the smaller characters. Shop-sign and poster words (阿嬤的滷肉飯, 山中茶話) were exact. | Expect errors with rare or technical characters. Keep CJK copy short and common, or set it afterwards in an editor. |
| An infographic kept its four labels, but the icons only loosely matched the steps. A tech diagram drew a generic cell, not stacked layers. | Describe each icon or part concretely. Do not trust the model for technical accuracy. |
| Lowercase "daily specials" with the words "in capital letters" rendered lowercase. | The quoted string's case wins over an instruction. |
| A floor plan of a two-bedroom flat had four rooms, not five: "KITCHEN 1" was invented and "BEDROOM 1" missing. A heart cross-section spelled all six labels right, but three leader lines pointed to the wrong parts. | Floor plans and teaching anatomy are on the exact tier: draw them with a tool. |
| An orthographic house elevation came back flat, symmetric and as described. A foxglove botanical plate spelled "Digitalis purpurea" right and looked plausible. | Elevations and botanical plates are usable as illustrations; an expert checks them before teaching or building use. |
| A 20-word quote with its attribution was exact. A title card, a 福 hongbao, 中秋快樂 over mooncakes, ありがとう and 감사합니다 signs and a vertical 夜市 neon sign were all exact. | Short common CJK in large type, and long Latin quotes, are dependable. |
| An illustrated Kyoto map misspelled two of five place names ("Kinkako-Ji", "Fushimi Intari") and invented the layout. | Check foreign place names letter by letter; the map is decoration, not geography. |
| A 3 x 3 alphabet poster kept A to I in order and eight animals, but drew a rabbit-lamb for "C cat". Two flashcards kept the same style and exact words; the fish came out smaller than the apple. | Check each cell against its word. Name the subject's size for an even deck. |
| A website hero kept its left half as an empty out-of-focus wall. | Side copy space holds. |
| A menu, a certificate and a social ad kept every quoted line and price. The certificate drew "Instructor" twice, once as a signature. | Short quoted copy is dependable. Check for a duplicated label. |
| A business card kept a name, a title, a phone number, an email and a city exactly, in a flat front view. | Short contact lines are dependable on a card mockup. Set the print file in a layout tool. |
| A quote card kept the quote, but the quoted attribution "Sheryl Sandberg" came out "Sherly Sandberg" on seeds 7, 11 and 23. | Check every proper name letter by letter. A reroll does not fix it. |
| 春聯: both vertical scrolls were exact and top to bottom (年年有餘, 歲歲平安). The banner, asked to read right to left, was scrambled on one seed of three. With no direction it read correctly on all three, in either direction. A vertical sign (老街茶館) with an English plate was exact. | Vertical CJK works for short common words. Give a horizontal CJK line no direction, and check which way it reads. Fix a scrambled line with an Edit. |
| A 長輩圖 greeting kept 早安 in big yellow with a red outline and 平安喜樂 in white with a black outline, over a saturated lotus. | Name the kitsch look and the outline colors; it does not need a reference. |
| A 9:16 story kept its headline and an empty top seventh on three seeds, but the "empty" bottom fifth filled with the croissant and marble on all three. Moving the croissant "to the upper middle" cleared the bottom on one seed of two, and that seed put the headline below the croissant. A slide background kept its left half empty. | Empty top bands and side halves hold. A bottom band does not: pad or crop it afterwards. |
| A LINE-style sheet of 8 stickers kept all 8 Chinese captions and the same cat, but put each caption under its sticker, outside the die-cut border, also when asked for the border around the caption. One sticker per image, with the caption "inside the white border, overlapping the bottom of the cat", kept it inside on both seeds. | Make cut-out stickers one per image. |
| An Edit replaced the misspelled "Sherly Sandberg" with "Sheryl Sandberg" on two cards and changed nothing else. | Fix a misspelled name with an Edit text replacement. |
| A bar chart got every label and value right, but the bars were not proportional: the 95 and 80 bars were about 12% short. | Treat chart values as decoration. Draw a data chart with code. |

## Seamless patterns

The words "seamless tileable" do not make a repeat. A ginkgo pattern written that way had motifs
cut by the edges, and its mean edge difference was 10.7 (left to right) and 14.5 (top to bottom),
against 1.5 for two interior columns. Asking for every motif fully inside the frame, with an even
margin to the edges, brought the differences down to 1.4 and 3.6, and the 2 x 2 tile read as
continuous. It did not follow the requested 4 x 4 grid.

1. Ask for small motifs, each fully inside the frame, with an even margin to every edge.
2. Tile the result 2 x 2 and look at the seams before you deliver it.
3. If a seam still shows, fix it in an editor or offer the image as a non-repeating background.
