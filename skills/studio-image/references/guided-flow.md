# Guided flow

Use this flow when the user gives a short or vague request ("a nice photo of my dog", "something
cool for my phone") or says they do not know where to start. A user with a full brief (subject, use,
style) skips it and goes to "Direct and generate" in SKILL.md. On this path, the question in step 1
replaces the end-use question in SKILL.md.

The user is not expected to know any photography or art words. Ask in plain words, offer numbered
picks, and translate each pick into the prompt sentences in the [look index](look-index.md). Never
ask a question whose answer needs jargon ("which focal length?"). Ask at most three questions before
the first image.

## 1. What is it for?

Ask once, with picks. The answer sets the ratio, the size and the margins. Show the user only the
words before each colon; the rest is for you.

1. A phone wallpaper or a story: 9:16, the subject in the middle half; the clock covers the top
   quarter and the icons or captions the bottom, so keep both plain. Add "The top and bottom
   quarters are plain sky, wall or ground." to every prompt, and skip looks whose effect sits at the
   edges (a light leak, a vignette, a film frame).
2. A post or a profile picture: 1:1, or 3:4.
3. A print or a poster: 3:4 or 2:3, at the largest offered size.
4. A desktop wallpaper, a header or a slide: 16:9.
5. Just for fun: 3:2 for a photo, 1:1 otherwise.

If the request already says it ("for my phone"), do not ask; say what you assumed.

## 2. What is in it?

Take the user's words as they are. Ask one follow-up only when the subject is too open to draw
("something cool"), and offer three concrete ideas to choose from, built from what they said (or
from the use, if they said nothing). Do not ask about details the user has no opinion on; choose
them and say so.

If a person, a pet, a product or a place must look like the real one, ask for a photo of it. Then
every scout and the final are Edits of that photo (see [editing](editing.md)): put the look's
sentence in the instruction ("Repaint this photo as ...") and say what must stay. An Edit keeps the
photo's frame, so the ratio from step 1 does not apply; if the use needs another ratio, say so and
offer to crop the photo first. Check [boundaries](boundaries.md) when a real person, someone else's
work, a brand or a mark is involved.

## 3. How should it feel?

If the user already named a look ("like Van Gogh", "anime"), do not ask. Find its row in the [look
index](look-index.md); for a painter, use the row that describes their traits, never the name. Scout
that one look four ways instead (step 4), with four framings or moments; on an Edit of the user's
photo, which keeps its frame, scout the look beside its three nearest **works** rows.

Otherwise offer these six picks. Each one opens one or more sections of the look index; show the
user the bold label and its sentence, not the sections in brackets.

1. **A real photo, natural.** Like a good phone or camera picture. (Lenses and focus; Exposure and
   light; Angles and camera moves.)
2. **An old film photo.** Warm, grainy, nostalgic. (Film, cameras and formats.)
3. **A movie scene.** Cinematic light and framing. (Director looks; Exposure and light.)
4. **A painting or a drawing.** From cave paintings to pop art. (Art across history.)
5. **Anime or animation.** Japanese anime or animation from around the world. (Anime and animation.)
6. **Surprise me.** Four very different looks to choose from. (One row from each of four sections.)

For a real photo, a scout of four looks means four different lenses, lights or angles on the same
subject: for example a 35 mm documentary view, an 85 mm portrait with a soft background, a low-angle
view, and contre-jour rim light.

## 4. Scout four directions

Write the user's subject as one plain sentence ("A golden dog sits on a sofa by a window.") and use
it in every scout. A row was tested on one subject, so replace any subject and place its sentence
names (the woman, the street, the dog, the bench) with the user's, and put the subject first when
the row's "Watch for" says so.

Choose four entries from the index section the pick opened (for "Surprise me", one entry from each
of four sections), as different from each other as the section allows (for "an old film photo": a
Super 8 home movie, a cool slide film, a disposable camera with flash, an instant photo). Only use
entries marked **works**. Describe each direction in one plain sentence when you show the results.

1. Tell the user what you will make and how long it takes, from the mode's `estimate` (see [the API
   notes](studio-api.md)). Four scouts are one batch and the normal start of this flow, so they need
   no separate approval.
2. Generate the four at the smallest offered size of the chosen ratio, with one fixed seed and the
   same subject sentence, so only the look differs.
3. Inspect each scout before you show it (see "Inspect, select, and refine" in SKILL.md). Replace a
   scout that missed its direction with another **works** row of the same section, rather than
   showing a failure as an option.
4. Show the four, numbered, each with its plain sentence.

A scout decides the direction. It cannot prove fine text, hands or small details; the final run
checks those.

## 5. Pick and adjust

Ask: "Which one is closest? Or tell me what to change." Offer this menu. Each item changes one
thing, and its prompt sentence is in the two "Adjustments" sections of the [look
index](look-index.md): one for regenerating, one for Edit.

1. Closer
2. Wider, show more of the place
3. From lower, looking up
4. From above
5. Warmer light, or colder light
6. More dramatic light
7. A different moment, a little later
8. More stylized, like a painting or a drawing

Apply one or two changes per round, and pick the tool by what changes:

- **Light, color or style** (5, 6, 8): Edit the chosen scout, and show the result before the final.
  Edit kept the composition in every test, though small details can move. Say that the subject keeps
  its own colors: "colder light" by Edit also turned a golden dog gray-white.
- **Framing, angle or moment** (1 to 4, 7): generate again with the added sentence, at the scout
  size. A new generation recomposes the whole picture, even with the same seed: "from low" moved the
  dog off its bench. Show the new scout and confirm before the final.

After two rounds without progress, ask what the user sees as wrong, in their words.

## 6. Make the final

Do not just rerun the scout's prompt and seed at a larger size: that recomposes the picture (the dog
left its bench). Generate at the largest offered size of the ratio, with the chosen scout as the
reference and the same prompt, at a `strength` of about 0.5, if the mode offers a reference and
`strength`. On Qwen-Image-2.1-Turbo that kept the composition and added real detail, and took about
half the time of a plain full-size run (33 s against 60 s at 1536x1024, one seed). At 0.7 the result
was soft, like an enlarged scout; at 0.3 the subject moved. Where Generate takes no reference, Edit
the scout at the mode's largest `resolution` (1344 on the Qwen backends) with "keep everything
exactly the same", which kept the composition but took longer.

If the scouts were Edits of the user's photo, make the final the same Edit of that photo at the
largest `resolution`.

Compare the final with the scout before you show it. Then follow "Deliver" in SKILL.md and run the
post-steps the use needs from [delivery](delivery.md).

When you report, give the user the plain sentence of the look, not the prompt, and offer the prompt
if they want to reuse it.
