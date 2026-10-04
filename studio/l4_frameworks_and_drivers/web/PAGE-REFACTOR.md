# The page refactor

The page is one file of 4,002 lines: 673 of CSS, about 3,085 of JavaScript, and
the markup and the htmx attributes between them. Nothing tests it except the e2e
scripts, because the repo has no JavaScript test setup at all. This document is
the design for taking it apart.

The goal is structure, not appearance. The page must behave exactly as it does
now, because the e2e checks pin that behaviour and they cannot see a style change
in either direction. Read `tests/e2e/verify_ui.py` as the executable version of
the contract in this document.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Components | Lit for a tree, a plain module for behaviour | Light DOM either way, so htmx's `hx-target` resolution and the browser checks that read the DOM keep working. The criterion follows below |
| Modules | Served by the studio | The server answers GET only for `/` and `/progress`, so there is nowhere else to serve them from |
| CSS | Moves out to `page.css` | 673 lines is a third of a file, and it makes the cascade readable in one place |
| State | One store, explicit redraws | Thirteen sections each hold their own variables and call `renderX()` by hand, and the order matters |
| Lit source | A CDN, as an ES module | No bundler and no npm. htmx already loads from a CDN, so this is the existing pattern |
| `verify_page.py` | Its bindings move to roles and ids first | It is the only check that proves the region tool against a real model, and it binds to today's markup |

A check binds to an id, an attribute, a role or an accessible name, and never to
a tag. Slice 5 is why: the containers of the size chips, the tiers, the
resolution buttons, the caption and the panel's readouts became custom elements,
and the suite did not move, because none of them is reached by its tag. A
container may become a component for free. A check that named the tag would have
made every one of those a behaviour change.

### Which of the two a component is

A component is a tree drawn from state, and Lit is the choice for that. Behaviour
that opens, closes, moves focus and routes keys is a plain light-DOM module
instead. The test is not taste: behaviour has to finish in the task that asked for
it, and Lit's render is asynchronous.

`popup-menu.js` is the precedent, and its case was measured, not argued. The
count menu focuses its checked item in the same task it opens. The measurement:
one function clicks the toggle and then reads the DOM. In that one task the menu
is open and the focused element is the item marked checked. The theme menu
behaves the same way. An asynchronous render would move the open and the focus a
tick later, which is a change in behaviour bought for nothing.

The boundary case is slice 6's in-place scroll, and it is the precedent for the
two sides meeting. A pick from a Look row's own chips scrolls the sidebar so the
row stays under the pointer, and the correction needs the row's top on both sides
of the redraw. That is behaviour by the first paragraph and a tree's job by the
same paragraph: the correction exists only because the component redraws the row,
and the page cannot sequence a render it does not own. So it stays in the
component, which waits for its own trees to draw and then reads the geometry. The
line is therefore not "behaviour against tree", it is who owns the redraw: a
correction that only exists because a component redrew belongs to that component.

Slice 7 is the second case, and it is the same reasoning at full size.
`region-mark.js` draws the brush, the overlay, the magnifier, the mask, the tools
and the region rows, and it is a plain module rather than a Lit tree. The state
there is a drawing. A stroke has to paint in the task that asked for it, because
the magnifier follows the pointer, and a row has to keep the text a person is
typing in it. So the render sequence is the behaviour, and the module that owns
the state owns the redraw.

This is not a licence to drop Lit elsewhere. The size chips, the Look rows and the
strip draw trees from state, so they stay Lit. A worker who thinks a later
component is behaviour rather than a tree brings the case the way this one came.

## Shape

    studio/l4_frameworks_and_drivers/web/
      page.html            the markup, the imports and the htmx attributes
      page.css             the CSS, moved out whole
      lib/
        state.js           the store, its fields, and the redraw it triggers
        form.js            the form's model: mode, params, Look, size and cost
        htmx.js            the progress poll and the run post
        theme.js           the theme's menu and pick, after the first paint
        store.js           IndexedDB: keep, clear, download, and the failures
      components/
        reference-list.js  References
        region-mark.js     Marking a region
        size-chips.js      Size and resolution
        advanced-panel.js  Count, steps, seed
        run-button.js      The run button's four labels, one of them shown
        look-rows.js       Look
        image-strip.js     Gallery, selection and compare
        kept-images.js     Kept images
        popup-menu.js      Backend, theme, count and more, one component
        toast-host.js      Toasts
        progress-card.js   The shell around the progress htmx owns
        stage.js           Full screen and the stage

Fifteen files for 3,085 lines. The cost is not spread evenly: the region canvas
is about 515 lines and the gallery about 630, so more than a third of the
JavaScript sits in two components. Plan the effort there.

`kept-images.js` was folded into `lib/store.js` in slice 9: the database and the
channel are one concern, so they are one file. `lib/form.js` was added in slice
10: the form's model is not a tree any one component draws, and it is what every
component the form is drawn from reads.

`theme.js` is not the early script. An inline script runs before the first paint, and an ES module is deferred, so the read of the saved theme stays inline in `page.html` and `theme.js` holds the menu. Moving that read out brings the flash back, and no check in this repo can see it.

## The door between a component and the classic script

The page's own script is still a classic script, and a classic script runs while
the markup is parsed. An ES module is deferred. So the page cannot import a
component, and it cannot call one during parsing either.

Rule: a component that the classic script drives announces itself on an event, and
the page mounts its sections in that handler. The page registers the listener while
the markup is parsed, so it is always in place first. The event fires while the
module is evaluated, which is after the markup is parsed and before any
interaction, so the sections are built in the slot they always took.

`popup-menu.js` is the first, on `popup-menus-ready`. Every component the classic
script drives needs the same door, and slice 10 closes them all at once.

Slice 5 closed three more. `state-ready` is the store's, and it hands the page
`get`, `set` and `subscribe`, because a classic script cannot import a module and
has no other way to put a field in. `size-chips-ready` hands the size controls
the option lists, the two form selects they drive, and the four derivations the
size field shares with the run estimate. `advanced-panel-ready` hands the panel
the one thing it needs beyond the store: which of the two scale names the mode in
force declares.

Slice 6 closed one more. `look-rows-ready` hands the Look trees the rows for the
mode in force, the picks themselves, the three derivations they share with the
page, and the pick, because the pick is also what mirrors the picks and refreshes
the form. Which row is open is the module's own: no consumer outside it reads
that, so it is not a store field.

Slice 7 closed one more, for the reference list. `reference-list-ready` hands the
tree the two things it cannot read for itself: how many images the mode takes,
and what a remove does. The remove is the page's because the page owns the array
a run posts. The tree carries no box of its own (`display: contents`), so the
empty state, the thumbnails and the note sit in `#refs` as they did, and the zone
stays the page's.

Slice 8 closed one more, for the strip. `image-strip-ready` hands the module the
gallery array, which the page holds and the module mutates in place; the shown
frame, which the page holds as a global the checks read; the waiting frame's
number and shape, which are the run's; the two name builders; and the page's own
draws, its toast, its store calls and its keeping flag. The strip draws the
frames from the store. The wipe and the three ways out of the gallery are
behaviour, so they are functions on the same handle rather than a tree.

The run button's labels take no door. Their verb comes from the store's `mode`
and their run state from a `data-state` attribute the page mirrors onto them,
because `stopping` is a class on the body and not a field.

Three rules came out of that slice.

1. **The page mirrors, and the store redraws.** `refreshForm` is still the one
   place a change is noticed. It now ends by writing the fields it just read into
   the store. The page goes on reading the DOM for its own work; the store is the
   components' copy of it, and `pushReferences` is separate because an array the
   page mutates in place has to reach the store as a copy.
2. **A component draws no element the page holds.** The page takes a reference to
   `#go`, `#go-sub`, `#prompt`, `#count`, `#size` and `#resolution` while the
   markup is parsed, and it hangs listeners on `#clear-seed` and the toggles. A
   Lit render replaces what is under it, so a component that owned one of those
   would leave the page writing to a detached node. That is why the run button's
   labels are a component and the estimate line beside them is not, and why Clear
   is still a `button` in the page's markup: a custom element is not a button to
   a screen reader and the keyboard does not reach it.
3. **A derivation moves with its inputs.** The run button's estimate and its
   disabled state stay in the page, because `blocker()` reads the region rows and
   the marks, and neither is a store field yet. They move in slice 7, with the
   region canvas, and slice 9.
4. **A control that a person presses stays a `button`.** Clear is a `button` in
   the page's markup, and no component draws it. A custom element is not a button
   to a screen reader and the keyboard does not reach it, so a component may draw
   what a button says but never the button itself. The same rule keeps the run
   button's labels a component and the button they sit inside the page's.

Slice 6 added two more, both about a tree that carries behaviour of its own.

1. **A name the cascade composes is contract, not style.** A Look row reads
   "Light none" with the stylesheet and "Lightnone" without it: the space is
   `display: flex` on the toggle making the pick a block of its own, so the
   markup carries no text node between the two spans. The loaded stylesheet
   cannot see the difference, which is why `verify_ui.py` reads the name a
   second time with `page.css` refused.
2. **A correction that reads geometry across a redraw waits for the redraw.** A
   pick from a row's own chips scrolls the sidebar so the row stays under the
   pointer, and that needs the row's top on both sides. Lit redraws after the
   click returns, so the correction waits for the module's trees to draw, and it
   lives in the component that draws them: the page does not sequence a render
   it does not own.

### The first paint, measured

A component is drawn by a deferred module, so the controls it draws appear a
moment after the page does. Slice 3 measured the theme's flash the same way:
the page's own modules held back 900 ms each on the server, and the CPU
throttled six times.

| Case | First paint | Controls drawn | What was painted without them |
|---|---|---|---|
| modules held 900 ms, CPU x6 | 1020 ms | 0.83 s later | no chips, no caption, no panel sentence and no run labels, and an empty 6 px pill where the tiers go |
| modules served locally, no throttle | first frame 194 ms | 6 ms later | the same empty state, for under one frame |

The unfetched state is what the markup alone paints. On a cold cache or a slow
device a reader sees it for up to a second, and locally for under a frame. This
is a known limitation of the slices so far rather than a defect of one component:
the fix is the theme's own pattern, the initial state in the markup with the
component taking over on upgrade. It is one job for every component at once, so
it belongs in slice 10, where the last of the inline script goes.

## State

One store. A component declares the fields it draws from, and a change redraws
only those components.

| Group | Fields |
|---|---|
| Form | `mode`, `prompt`, `typed`, `size`, `resolution`, `steps`, `guidance`, `cfg`, `seed`, `negative`, `count`, `looks` |
| References | `references`, and `marks` and `marking` as the region module's own (below) |
| Results | `gallery`, `view`, `busy`, `progress` |
| Kept | `keeping`, `theme`, `fullscreen` |
| Run | `cleared`, `cancelRestore`, `runLook` |

The rule that replaces today's hand-ordered calls: a mutation names the groups it
touched, and nothing draws itself because something else happened to run first.

`marks` and `marking` are `components/region-mark.js`'s own fields, and no
consumer outside that module reads them. The store carries the redraw signal
between consumers, so a field with no other reader is a copy that can disagree
with the thing it copies, which is the failure this refactor keeps circling. The
module does not mirror them. A slice that gives them a reader outside the module
adds the field then, and not the mirror now.

## The one region htmx keeps

The progress card is htmx's. It polls `hx-get="/progress"` and swaps `#progress`.
If Lit renders that subtree the two fight and the poll loses. So `progress-card.js`
renders the shell and **htmx owns the children**.

The run stays an htmx post. The region composition depends on the
`event.detail.parameters` hook, and moving it to `fetch` would move the mask
contract as well. That is a separate change, with its own risk.

## The static route

    GET /page/<name>  ->  studio/l4_frameworks_and_drivers/web/<name>

Two rules, both unit-testable, and the statement and branch gate covers them:

1. A resolved path must stay inside `web/`, so `..` cannot escape it.
2. Only `.js` and `.css` are served. The route must not hand out this document.

## What must not move

These are the contract the e2e checks pin. A slice that changes one of them has
changed behaviour, not structure.

1. The GET routes and the POST routes, and the shape of each posted form.
2. The form field names.
3. These ids: `#prompt`, `#go`, `#size`, `#resolution`, `#steps`, `#guidance`,
   `#cfg`, `#seed`, `#negative`, `#count`, `#reference`, `#thumbs`, `#strip-note`,
   `#edit-sizes`, `#size-chips`, `#clear-seed`, `#clear-reference`,
   `#rewrite-toggle`, `#templates-toggle`, `#count-toggle`, `#theme-toggle`,
   `#guide-toggle`, `#advanced`, `#look-rows`, `#region-rows`, `#guide-sheet`,
   `#templates`, `#backend-menu`, `#theme-menu`, `#count-menu`, `#more-menu`.

Some of those ids are drawn by a component rather than written in the markup, and the list
must not be read as an inventory of `page.html`. `#thumbs` is one: the reference list draws
it, so the id is pinned on what the component renders, not on a line in the file. It was
listed here as though the markup carried it, which sends a reader looking in the wrong
place. `#counter` is the one entry that must keep NOT existing.

   Fifteen more are pinned by the same checks and were missing from this list.
   `verify_ui.py` and `verify_page.py` reach every one of them, so a slice that
   renames or drops one takes a check with it. None of the fifteen carries an
   `aria-label`, and only `#backend-toggle` is a role a query can ask for by
   name. How each one is reached:

   | Id | How a check reaches it |
   |---|---|
   | `#go-sub` | By id. The run button's sub-line: a `span` with no role, no label and no `aria-live`. Its text is part of `#go`'s accessible name, so a role query gives the sub-line only with the verb in front of it, which is a different claim. |
   | `#status` | By id, and by role while a run shows it. A `span` with `role="status"` and `aria-live="polite"`, and it is hidden until there is something to say. `aria-live` alone gives an element no role a query can ask for: the explicit `role="status"` is what `get_by_role("status")` reaches. `verify_ui.py` reads it by role mid-run, and `verify_page.py` reads its `aria-live` by id. |
   | `#region-preview` | By id. A `paragraph` with no name of its own. It holds the sentence the page will send, so binding it by that sentence would make the assertion vacuous. |
   | `#region-note` | By id. A `paragraph` with no name. |
   | `#region-field` | By id. The `div` around the region rows, and the rows inside it are the `textbox` role. |
   | `#stage-bar` | By id. A `div` with no role. Everything inside it is reached by role: the print's caption as a `paragraph`, and the drawing tools by their names. |
   | `#toasts` | By id, and by role. The host is a `div` with `role="status"` and `aria-live="polite"`, so a role query reaches it without the id. A toast inside it carries `role="status"` as well, or `role="alert"` when it reports a failure. |
   | `#incoming` | By id. The `div` the run posts into and htmx appends to. A batch holds its placeholders in it, which is how a check reads whether a request went out. |
   | `#tier-sizes` | By id, then the `button` role inside it. The buttons name their megapixels, and those names follow the chosen ratio, so the first one is found by its position and not by its name. |
   | `#look` | By id. The `details` that holds the Look rows, and its `summary` is what opens it. It reads as a `group` in the browser's tree, and that group carries no name a role query can ask for. |
   | `#look-values` | By id. The `span` in the Look summary that reads the pick back, and it says `none` when nothing is picked. |
   | `#strip` | By id. The `div` that holds the kept frames. Each frame inside it is a `button` named `"<mode>, seed <n>"`, so the frames are reached by role and only the container needs the id. A check also clones the strip's children, at a wide thumbnail's width, to measure whether a full strip widens the column. |
   | `#canvas` | By id, reached as `getElementById('canvas')` and not as a selector. The `div` that holds the print and the progress card. `#stage-bar` and `#toasts` are its siblings, not its children. The two reduced-motion checks append their own probe into it and read animation names off real markup there. |
   | `#counter` | This one must stay ABSENT. "the top plate has no frame counter" asserts that no element carries this id, so a slice that adds one breaks a check. |
   | `#backend-toggle` | By role, as a `button` named for the model in force. It also carries `aria-haspopup`, `aria-expanded` and `aria-controls`. The `.name` span inside it, which the truncation check measures, has no handle of its own. |

   The custom property names are pinned the same way, and for the same reason:
   `getComputedStyle` reads the cascade, so it survives the modules, and what
   breaks it is a renamed property. Which check reads each one:

   | Property | Read by |
   |---|---|
   | `--text` | the contrast check, as the foreground of each of its pairs |
   | `--text-2` | the contrast check, as a foreground |
   | `--text-3` | the contrast check, as a foreground, against both `--chrome` and `--chrome-2` |
   | `--chrome` | the contrast check, as a background, and the check that a theme changes the chrome |
   | `--chrome-2` | the contrast check, as a background |
   | `--chrome-3` | the contrast check, as the background a hovered control sits on |
   | `--on-accent` | the contrast check, as the run button's label |
   | `--accent-fill` | the contrast check, as the run button's fill |
   | `--box` | the contrast check, as the background of the stage |
   | `--split` | the two checks that read where the divider sits, and the sampler that records its sweep |
   | `--exposed` | the check that the photograph is made by a sweep, a drop, a rise or a develop. `verify_page.py` sets it to 40% on a probe plate and reads back which shape the plate takes, so the CSS must keep consuming it |

4. The mode radios keep their label association, so `for="mode-generate"` and
   `for="mode-edit"` still point at the inputs.
5. A Look chip and a size chip keep `aria-pressed`.
6. A strip frame keeps its `aria-label` of `"<mode>, seed <n>"`.
7. A Look row button keeps `aria-expanded` and names its chosen chip. The space
   between the two is the cascade's, so the name reads `Light none` with the
   stylesheet and `Lightnone` without it, and the markup carries no text node
   between them. `verify_ui.py` reads the name both ways, the second with
   `page.css` refused.
8. The backend badge keeps its `title`.
9. `#strip-note` keeps its wording, including "N images" and "in this tab".
10. `#go` keeps its `data-state`, one of `idle`, `busy` and `stopping`, set
    wherever the body's `busy` and `stopping` classes change, and `verify_ui.py`
    waits on that attribute rather than on the button's name.

    The DOM composes that name, and the name is always exactly one verb. The
    button carries four labels, `Generate`, `Edit`, `Cancel` and `Stopping…`,
    and the page sets `hidden` on the three it is not using: `syncRunLabels`,
    called on every run-state change and on every mode switch, hides the two
    run-state labels and picks between the two verbs. No rule in `page.css` sets
    `display` on those labels, so a stylesheet that never loads leaves one verb
    in the name, the same one the loaded stylesheet shows. A slice that puts the
    choice back in the cascade makes a refused stylesheet read
    "GenerateEdit Cancel Stopping…" to a screen reader, and no verb can be
    matched in it. `verify_ui.py` asserts the name is `Cancel` mid-run with the
    stylesheet loaded, and again with `page.css` refused.
11. The region canvas keeps a box big enough for the stroke offsets the checks
    compute. `pointOf` scales a client offset by `canvas.width / box.width`, so
    the mapping is proportional: any size works while the offset stays inside
    the box. The largest offset in `verify_ui.py` is +300 across and +290 down.
    The natural box is 503 by 503, a 480 by 360 box still registers a stroke,
    and a 240 by 160 box does not at those offsets, so the margin is about
    200px. Two changes break it: shrink the stage below roughly 300 by 290, or
    make `bounding_box()` return a wrapper that also holds a toolbar instead of
    the drawing surface itself. These five checks measure geometry and not only
    behaviour, so a restructure that moves those dimensions moves them: four of
    them fail outright, and the fifth cannot run because the row it waits for is
    never drawn.

## Slices

Each slice lands with every UI check green. Do not start the next one while a
check is red.

1. Move `verify_page.py` off its 108 CSS locators and 79 `evaluate` calls, onto
   roles, labels and the ids above. Confirm with one real run on the GPU. The
   real-run net is intact before anything else moves.
2. Add the static route, with unit tests for both rules, and serve one module
   through it.
3. Add `state.js` and move `theme.js` out, as the smallest example of the pattern.
4. Add `popup-menu.js` and use it for the four menus.
5. Move the size and resolution chips, the advanced panel and the run button.
6. Move the Look rows, the summary's read-back and the tail under the prompt.
7. Move the reference list, then the region canvas. This is the hard one.
8. Move the gallery, the strip and the compare.
9. Move the kept images, the toasts, the progress shell and the run wiring.
10. Move the stage and full screen, and delete what is left of the inline script.

### Slice 7: the reference list and the region canvas

The reference list moved to `components/reference-list.js`, and the region canvas
to `components/region-mark.js`. Both keep every id and class a check reaches.

`region-mark.js` is a plain module and not a Lit tree, on slice 6's own rule: who
owns the redraw. Its state is a drawing. A stroke has to paint in the task that
asked for it, because the magnifier follows the pointer, and a row has to keep
the text a person is typing in it. The module redraws its own trees in its own
order, and the page never sequences a render it does not own.

The state is the module's own and nothing is published on `window`. The page asks
real questions through the handle it takes on `region-mark-ready`, and the module
asks the page for the four things it owns and the module cannot see: the reference
list (a run posts it), the shown frame, the mode in force, and the page's own
draws, toasts and buttons. The State table's `marks` and `marking` are the
module's own fields and no consumer outside it reads them, so the module does not
mirror them into the store.

The module is deferred, so the page's own draws ask the region five questions
before its handle arrives. The page answers those five with the empty region,
which is the true answer until the module is loaded.

`verify_page.py` now reads the region as DOM facts instead of as page globals:
the brush's width is the brush button's own label, the width a stroke kept is the
area the mask painted, a swatch's colour is the rows and their order, and the
rows gone say the instruction went with them. One claim traded down: the set a
row's placeholder is drawn from is no longer published, so the check reads the
placeholder's presence and shape and not its membership of that set.

### Slice 8: the gallery, the strip and the compare

The strip and the wipe moved to `components/image-strip.js`, and the gallery's
three ways out (a removal, a clear, a download) moved with them. Every id, role
and label a check reaches stayed: `#strip` is the element itself, each frame is
still a `button` named `"<mode>, seed <n>"`, and `#strip-note`,
`#download-gallery` and `#clear-gallery` never left the page's markup, because
the page holds them and hangs their listeners there.

The strip is a Lit element and its render root is the element itself, so the
markup changed in one place: `#strip` is now an `<image-strip>` carrying the same
class, and the class is what makes it the flex row the frames sit in. The wipe
and the ways out are plain functions, because they are behaviour: the wipe is an
input, an animation over `--split`, and two tags, and a removal or a clear
splices the array and redraws. The stage still draws the print, so the page asks
the module to draw the wipe into it.

Three rules came out of it.

1. **A tree that must not rebuild its nodes keys them.** A frame holds an image
   and an entrance, and a rebuilt frame reloads the image and restarts the
   animation. The page used to keep a map of frames and move them by hand; the
   element does it with `repeat`, keyed by the image's own id. So this file
   imports a directive as well as `LitElement` and `html`.
2. **A one-shot the page clears before the render is handed over, not asked
   for.** The arrival is set by `harvest`, read by the stage for the print's own
   fade, and cleared on the same task. Lit renders a microtask later, so a
   question would be asked after the answer had gone. The page hands the arrival
   over while it still holds it, and the element keeps the frames that arrived.
3. **A correction that reads geometry across the redraw waits inside the
   component.** This is slice 6's rule again. The arrow keys walk the strip, and
   the selected frame's box and focus are read after the redraw, which lands after
   the key returns. The step is the module's, and the page's key listener only
   asks for it.

`verify_ui.py` gained two checks with the slice. One is the focus the step leaves
on the frame it shows, which nothing read before. The other is that a frame the
strip moves along keeps its own image: the claim is the image the browser already
held, so the check holds the node and reads its `src` and its load count across a
removal. `verify_page.py` already made that claim on a real run; the suite now
makes it on the stub too.

`verify_page.py` reads the strip's own frames for its reduced-motion claim as
well: the entrance a frame arrived with, and the loop a pick draws. The loop's
markup moved into the module with this slice, so the check reads it from the
frame and not from the page global that the probe before it used.

The gallery array and the shown frame stayed the page's. A run's answer, a kept
image and another tab's message all write the array, and the last two are slice
9's; the page mirrors it into the store, as it does the references. The progress
card's internals, `.plate` and `.exposure`, are htmx's and slice 9's, and this
slice only kept them where they were.

### Slice 9: the kept images, the toasts, the progress shell and the run wiring

The kept images moved to `lib/store.js` and the toasts to
`components/toast-host.js`. The progress shell moved to
`components/progress-card.js`.

The store owns the database and the channel. Two things stayed in the page, and
both are read before a deferred module can be fetched: the keep setting, which
the strip note and the leave warning read while the page is still parsing, and
the gallery array, which a run's answer lands in. The module rebuilds an entry
from a record and the page files it, because the array is the page's.

`#toasts` is the `<toast-host>` element itself, with the id and the `role` a
query reaches it by. A toast is a tree drawn from a list of messages, and the
list is the element's own: no consumer outside it reads the list, so it is not a
store field.

The progress card is behaviour and not a tree. `paint` reads the plate's offset
back between clearing its rewind class and putting it on, and the card is fitted
from its own box in the same task that builds it. Lit renders a microtask later,
so a Lit card would show the drop instead of the sweep, and `fitStage` would
measure a plate that is not there yet.

htmx keeps `#progress`. The poll swaps the children of that element, and those
children carry the next `hx-get`. A render root over that subtree would take the
loop with it and a run would stop reporting. The card is drawn in `#canvas`,
beside it, and the module never touches `#progress`.

The run wiring stayed in the page, and `lib/htmx.js` was not written. Nine of
the ten names `verify_page.py` reads out of the page's global scope are the
run's own: `runStartedAt`, `progressState`, `renderProgress`, `learnedCost`,
`costKey`, `stepSeconds`, `view`, `gallery` and `renderStrip`. That check drives
them directly and it is frozen for this refactor, so a piece of the wiring that
writes one of them cannot move without leaving a setter behind for it. The
estimate, the form snapshot and the harvest each write one. They move in slice
10, or after the check converts. The ten were ruled on straight after this
slice, and seven have converted: see "The ten reads `verify_page.py` makes out
of the page" below.

Two rules came out of it.

1. **A module's door fires in the order the module tags are written, and a later
   module can toast what it finds.** The store's first job is to read the kept
   images back, and it says so through the page's own `showToast`. That is safe
   only because `toast-host.js` is declared before `store.js`. No message is
   sent before the host is here, and that is measured rather than assumed: with
   every module held back half a second, which is the worst a cold load does,
   the message still arrives and no page error is raised. Reordering those two
   tags breaks it.
2. **A check that pokes a page global becomes a check that breaks a browser
   fact.** `verify_ui.py` cleared the page's IndexedDB promise to reach the
   open failure. The store is opened once and held, so after the first moment
   that failure is unreachable anyway. The check now breaks the transaction on
   the handle the page already holds, which reaches the same message and needs
   no page global.

The suite grew three checks. Two make this tab the receiving side of the
channel, which every check before had as the acting side: the keep setting is
changed in the other tab and this one has to follow, once each way. The third
reads the progress card on the stub, because `verify_page.py` is the only check
that read it before and that one needs a real model: the plate, the exposure and
the percentage, with the exposure asserted against the percentage the card shows
rather than against a number.

### The ten reads `verify_page.py` makes out of the page

They were ruled on after slice 9, as a task of its own, because slice 10 cannot
move the run wiring while the net holds a name the page owns. Seven convert onto
a DOM fact the page already reads, and each one asserts the same or more:

| Read | The DOM fact that replaces it |
|---|---|
| `view` | the `aria-label` of the frame the strip marks selected, which the design pins |
| `setSelect` | the megapixel button under `#tier-sizes`, which is also the control a held panel blocks |
| `progressState`, `renderProgress` | the `.progress-state` element the poll writes and the page's observer reads |
| `runStartedAt` | `#go`'s `data-started`, published beside the run state the button already carries |
| `renderStrip` | a redraw from a DOM action: showing the frame already on the stage |
| `gallery` | the caption under the print, and what Reuse prompt hands back |

`renderProgress`, `runStartedAt` and `view` stop being names the check reads at
all, which is better than converting them.

Three stay: `learnedCost`, `costKey` and `stepSeconds`. The only DOM fact that
carries them is the estimate sentence under the run button, and in the state
those checks read it, the prompt is empty and the button shows a blocker
sentence instead. An exact rate traded for a rounded sentence that is not on
screen asserts less, so the three stay in the page.

The conversions were proved without a GPU: `verify_page.py` runs against the
stub at 179 of 180, and the one check it cannot make there is the mask's colour
at the reference's size, which needs real pixels. So a change to this net can be
checked in seconds before it costs a run, with the run left to prove the engine.

### Slice 10: the stage, the run and the form

The stage and full screen moved to `components/stage.js`, the run wiring and the
server's answers to `lib/htmx.js`, and the form's model to `lib/form.js`.
`page.html` is 921 lines: the markup, the htmx attributes, and a classic script
of 658 lines. The inline script fell from 2,213 lines to 658, and the functions
the coverage report counts in it from 263 to 114.

The form module is declared first of the modules, because every later door is
handed on to it: `size-chips-ready`, `advanced-panel-ready`, `look-rows-ready`
and `reference-list-ready` all reach the form, and a component the form is drawn
from reads the form's own values rather than a second copy of them. The stage
and the run take what they need from the form the same way, on their own doors.

What the classic script is now, and why each part cannot leave.

1. **The pre-paint theme read**, in its own `<script>` above the modules. An
   inline script runs before the first paint and a deferred module does not, so
   it stays where it is. That is the measurement in "The first paint, measured".
2. **`STUDIO` and what is derived from it**: `MODES`, `MAX_BATCH` and
   `EDGE_NAME`. The server substitutes `__STUDIO__` into `page.html`, and the
   static route serves a file's bytes verbatim, so no module can be handed it.
   Every module takes the derived values on its door instead.
3. **The page's element references**: `form`, `go`, `go-sub`, `prompt`,
   `count`, `size`, `resolution`, `progress`, `incoming`, `reference`, `refs`,
   `count-toggle`, `count-menu`, `templates-toggle`, `templates`, `canvas`,
   `stage-bar` and `status-text`. A Lit render replaces what is under it, so the
   page takes each one while the markup is parsed and hands it over; a component
   that owned one would leave the page writing to a detached node.
4. **The door registrations.** A classic script cannot import a module, and it
   cannot call one's exports while the markup is parsed either. So the page
   registers a listener per module here, and each module fires its own event
   while it is evaluated. Fourteen doors, each one forwarding to the module
   that owns the section.
5. **The references array**, because `verify_capabilities.py` reads it by
   name out of the page's global scope: `references.length`,
   `references[0].source` and `references[0].width`, beside `view`. The array is
   the page's and the form reassigns it through a setter on its door. A first cut
   moved it into the form module, which broke that check with a `ReferenceError`
   the UI suite cannot see. Real consumers decide, and this one reads the page.
6. **Three names `verify_page.py` reads out of the page's global scope**:
   `learnedCost`, `costKey` and `stepSeconds`. The check is frozen, and what it
   asserts is an exact step rate that the estimate sentence does not carry in
   the state it reads. So the three stay the page's own names: `learnedCost` is
   the page's object, which the form reads and the run writes, and the other two
   answer with the form's own numbers.
7. **The document's own keys**: `F` for full screen and the arrows for the
   strip, plus Cmd+Enter to run. Two modules share each key, so the key is the
   composition root's.
8. **htmx's own wiring**, in the markup as attributes: `hx-post`, `hx-target`,
   `hx-swap` and the `hx-vals` the chain placeholders carry.

The rest of the remaining script is the page's own state, which a run, the stage
and the strip all read: the gallery array, the shown frame, the arrival, the
frame counter and the shape in flight. Each is asked for through a getter on the
door of the module that needs it.

Four rules came out of this slice.

1. **The first draw runs inside a module's `configure`, so a page callback it
   uses must tolerate a null handle.** The form draws itself when its module is
   evaluated, which is before the page has assigned the handle that `configure`
   returns. The first draw reached a page function that went back through that
   handle and threw. The page's own callbacks on that path are guarded, and the
   store is seeded again on its own door.
2. **A helper the page has moved is passed as a call, not as a name.** A door's
   helper object is evaluated by the page, so a name the page no longer declares
   throws before `configure` is reached, and the module's handle never arrives.
   One such name cost the run, the stage and every door after them their wiring,
   and it raised no error of its own.
3. **A name a frozen check reads is a shim, not a copy of the code.** The three
   names above are the page's, and they answer with the module's numbers rather
   than with a second implementation that could drift.
4. **The other suites in `tests/e2e/` are consumers too.** `verify_ui.py` is not
   the only check that reaches into the page: `verify_capabilities.py` reads
   `references` and `view` out of the page's global scope, and it lives outside
   this design's contract. State a slice moves has to be checked against every
   script in that directory, not only the one this document is the contract for.
   `verify_capabilities.py`, `verify_storage.py` and `verify_page.py`'s own
   bindings are all worth a run before the move is called done.

`tests/e2e/js_coverage.py` reports the page's code in two lines, the inline
script and the modules. The inline line will never say "none left": the four
things above are code, and they stay. It reads 111 of 114 functions against the
stub suite, and the modules 518 of 522, which is what "the code has moved" looks
like for a page that has a composition root.

The suite grew no checks: this slice moves code and changes no behaviour, and
the 137 checks that pin that behaviour were the gate at every step. What was
proved instead is that the checks still bite on the moved code. Three mutations,
each served from a copy of the page directory, and one control with nothing
mutated:

| Mutation | Where | What the suite caught |
|---|---|---|
| the frame number loses its zero pad | `components/stage.js` | 3 checks, all of them read a frame number |
| the Look stops reaching the sent prompt | `lib/form.js` | 1 check: the posted prompt carries the Look |
| the double-click guard widens to 30 s | `lib/htmx.js` | 2 checks: Cancel stops the run, and puts back what Run emptied |

## Non-goals

1. No bundler, no npm, no build step.
2. No shadow DOM, because htmx and the browser checks reach into the DOM.
3. No new dependency except Lit from a CDN.
4. No change to the form field names or the posted shape, so `studio/` Python and
   its 100% gate are untouched.
5. No change to what htmx does for the progress poll.
6. No visual redesign. Appearance is out of scope, and no check here can see it.

## Acceptance

1. Every UI check green after every slice.
2. The unit suite still at 100% statements and branches.
3. `verify_page.py` green on a real run at the start and at the end.
4. One browser pass of generate, edit and cancel, with the cancel during a run.
