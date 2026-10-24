# Shot design: composition, viewpoint, optics, and light

Read the sections needed for the brief. These are independent directing dimensions;
they can be combined with photography, painting, anime, or other visual languages.
The recipes are prompt vocabulary, not new UI options or Image API parameters.

## Build a shot, not a camera-specification list

Start with what the audience should notice and how the image will be used. Establish
subject placement, frame size, viewpoint and depth relationships. Add a compatible focus
strategy and light setup. Use camera shorthand only when it strengthens those instructions.
Select a few purposeful choices; combining every technique makes contradictory prompts.

Keep these records distinct:

| Record | Examples | How it is enforced |
|---|---|---|
| Deliverable | Square product card, vertical portrait, wide banner with copy space | Choose an offered output size/ratio and inspect the saved image. |
| Visual direction | Camera above the table, entire rim visible, hands in frame, background out of focus | Describe in the prompt; judge the pixels. |
| Camera shorthand | Full-frame-equivalent 85mm look, f/2, short exposure | Prompt cues; no guarantee of physical simulation or real EXIF. |
| Engine settings | Backend, steps, guidance, seed, references, resolution | Submit only fields supported by live discovery/schema. |

Do not send invented `aperture`, `iso`, `focal_length` or `camera_angle` JSON fields unless
a future backend explicitly declares them. Describe their desired effect in `prompt`.
An API accepting unknown fields does not prove the engine used them. Preserve a user's
explicit settings, but flag incompatible visual goals rather than silently promising both.

## Composition and visual hierarchy

| Choice | Make the instruction concrete | Inspect for |
|---|---|---|
| Centered symmetry | Subject on the vertical centerline; matching visual weight on both sides. | Alignment, unintended asymmetry. |
| Thirds placement | Subject on the right third; horizon near the lower third. | Actual placement, not a decorative grid. |
| Asymmetric balance | A large subject on one side balanced by a smaller contrasting element. | Both anchors readable, one clear priority. |
| Copy space | Product on the right; left half is plain, low-detail background for later typography. | Clear usable area, no invented lettering. |
| Leading lines | Table edges or a path converge toward the focal subject. | Lines lead toward rather than past it. |
| Diagonal arrangement | Place the main forms along a rising diagonal, with deliberate supporting angles. | Direction across the frame, not merely a tilted camera. |
| Triangular grouping | Three distinct forms establish a stable triangular arrangement. | Separate silhouettes and a clear hierarchy. |
| Curved visual path | A winding path or sequence of forms guides the eye through the scene. | Readable curve without distracting clutter. |
| Frame within frame | Use a doorway, arch or branches around the subject. | Framing elements do not obscure key features. |
| Foreground/middle/background | Near foliage, subject in the middle plane, distant architecture. | Distinct planes, plausible occlusion and scale. |
| Repetition with an exception | Repeat a controlled row of forms; one contrasting subject breaks the rhythm. | Correct count and a visible exception. |
| Scale contrast | A small figure against a large environment, with recognizable scale cues. | Subject remains legible at delivery size. |

These are options, not rules every good image must satisfy. Describe left/right from the
viewer's perspective. For headroom and gaze room, say which edge needs breathing space.
Check silhouettes and avoid accidental tangencies, such as a handle merging with an arm.
If exact placement is essential, a supplied layout/reference is stronger evidence than a
named composition rule, though an Edit can still rearrange it.

## Framing and crop

| Frame | Prompt cue |
|---|---|
| Establishing/environmental | Show the setting prominently; subject occupies a small but readable part of the frame. |
| Full figure | Entire person, including feet and head, inside the image with a deliberate margin. |
| Three-quarter figure | Frame from approximately the knees upward; keep the hands when they matter. |
| Medium | Waist-up or another explicit boundary; show the interaction and relevant props. |
| Head and shoulders | Face and shoulders fill the composition; specify eye line and headroom. |
| Tight detail | Isolate a named feature, material or mechanism; state what must remain identifiable. |
| Macro-like detail | Very close view of a small subject with visible fine texture and a chosen focus plane. |
| Product hero | Complete silhouette, all defining features visible, deliberate angle and room around the object. |

A close-up is a framing choice, not automatically a macro photograph. A wide shot does
not automatically mean a wide-angle lens. “Full body” and “tight headshot” conflict for
one person in one frame. Avoid cropping at awkward joints unless the brief intends it.
Request one continuous image unless a panel layout or contact sheet is wanted.

## Viewpoint, height, and orientation

| Choice | Concrete direction |
|---|---|
| Eye level | Camera at the subject's eyes; level horizon. |
| Object level | Camera at the product's midpoint; define which faces of it are visible. |
| Slightly high angle | Camera above eye level, looking gently downward; some top surfaces visible. |
| Low angle | Camera below the subject, looking upward; specify how much underside is visible. |
| Ground level | Camera just above the ground, near objects enlarged against the distant scene. |
| Direct overhead | Camera points straight down; top surfaces dominate, not an eye-level side view. |
| Oblique overhead | Camera above and to one side, looking down; both top and side faces visible. |
| Front-on | Camera faces the subject's front; distinguish this from the direction the person looks. |
| Three-quarter view | Camera sees front and one side; specify the visible side or defining feature. |
| Profile/rear view | Camera at the subject's side or behind it; preserve the intended face visibility. |
| Over the shoulder | Foreground shoulder frames a second subject or task; specify whose viewpoint. |
| Canted horizon | Deliberately tilted horizon, with a clear intended degree of unease or energy. |

Camera position, subject pose and gaze are separate. A person can face camera-left while
looking back at an eye-level camera. A Dutch angle rotates the horizon; it does not mean
a low-angle shot. An overhead edit needs newly visible surfaces that a source photo may
not establish. If it repeatedly preserves the original viewpoint, reassess the reference
constraint instead of calling a crop a new camera position.

## Lens perspective and distance

The following numbers are full-frame-equivalent photographic cues, not a simulated
calibration. Perspective depends on camera position; changing focal length alone from a
fixed position changes field of view, not near/far proportions. For the familiar wide
versus telephoto comparison, specify both distance and the framing you intend to keep.

| Lens family | Pair with a visible spatial instruction |
|---|---|
| Ultra-wide, roughly 14–20mm | Close viewpoint, extensive surroundings, strongly enlarged near forms; request straight lines if rectilinear geometry matters. |
| Wide, roughly 24–35mm | Environmental framing, camera near enough for foreground/background separation and depth. |
| Normal, roughly 40–60mm | Moderate field of view and distance; avoid exaggerated near-object size. |
| Portrait telephoto, roughly 75–105mm | Step back while keeping a similar subject size; calmer facial proportions and a narrower background view. |
| Long telephoto, roughly 135–300mm | Distant camera, tight framing, distant background appearing large relative to the subject. |
| Fisheye | Intentionally curved straight lines and a strongly expanded field; distinguish from a rectilinear wide lens. |
| Orthographic/isometric illustration | Parallel or systematically angled axes, little/no perspective convergence; an illustration projection rather than a camera-lens promise. |

Do not require extreme wide-angle proximity and compressed distant-camera perspective at
once. Corrected architectural verticals are a different request from a miniature tilt-shift
look. State “vertical edges remain parallel” for the former; specify a narrow band of
sharpness and miniature-scale appearance for the latter. Neither wording proves real
tilt/shift optics were simulated. For a true lens comparison, distinguish a fixed camera
position from repositioning the camera to match subject size.

## Focus and depth of field

| Choice | Visible outcome to request |
|---|---|
| Shallow focus | Named near eye or product feature sharp; background strongly defocused. |
| Moderate depth | Face and held object both readable; background softened enough to separate them. |
| Deep focus | Named foreground and background elements sharp; do not simultaneously request heavy background bokeh. |
| Foreground veil | Out-of-focus near foliage or glass partially frames a sharp subject without hiding it. |
| Selective detail | Focus on a specific texture or contact point; other parts fall away gradually. |
| Tilted focus-plane look | An intentionally angled band of sharpness through the scene; inspect whether it follows the stated plane. |
| Focus-stack appearance | Entire small product sharp, from near edge to far edge, despite close framing. |

For photography, f/1.4–f/2.8 can support a shallow-focus request and f/8–f/16 a deeper-focus
request, but aperture alone does not determine depth of field: distance, magnification,
focal length and format also matter. Lead with the parts that must be sharp. Do not claim
that a generated image was focus-stacked or that a numeric aperture was physically applied.

## Shutter, exposure, ISO, and motion appearance

| Cue | Pair with the intended appearance |
|---|---|
| Fast-shutter look, e.g. 1/1000 s | Moving droplets or limbs sharply frozen; no directional smear. |
| Slow-shutter look, e.g. 1/15 s | A stationary setting stays stable while a moving hand or fabric blurs along a stated path. |
| Panning look | Moving subject comparatively sharp; background stretches into streaks along its travel direction. |
| Long-exposure look | Water appears silky or vehicle lights form continuous trails; static structures remain sharp. |
| Low-ISO look | Clean tonal gradients, controlled shadows and little visible sensor-like noise. |
| High-ISO look | Coarser luminance/color noise and limited shadow cleanliness; state amount rather than assuming the number sets it. |
| High key | Predominantly light tones with retained highlight detail; not accidental blown-out white areas. |
| Low key | Predominantly dark tones with a readable focal subject; not an unreadably black frame. |
| Highlight-priority appearance | Preserve bright fabric/window detail and accept darker shadows when the scene calls for it. |

Shutter, aperture and ISO are related in a real exposure; a generation prompt does not
solve that exposure triangle. Brightness does not prove a requested ISO or shutter value.
Grain/noise is not motion blur. For an action still, describe a single instant and what
moves; do not ask the image API for a pan trajectory or rack-focus animation.
In stylized drawing, use the equivalent line, tone, edge and motion-mark language instead
of appending an irrelevant list of camera settings.

## Lighting and surface rendering

| Setup | Direct the visible evidence |
|---|---|
| Soft window light | Broad side light, gentle shadow edges and a plausible window catchlight. |
| Hard directional light | Small defined source, crisp cast shadows and clear light/shadow boundaries. |
| Overcast daylight | Diffuse sky illumination, subdued cast shadows and controlled surface contrast. |
| Golden-hour backlight | Low warm source behind the subject, rim separation and softer foreground fill. |
| Split portrait light | One side of the face lit, the opposite side in shadow; specify how much fill remains. |
| Rembrandt-like portrait light | High side key with a small illuminated triangle on the shadow-side cheek. |
| Butterfly light | Key above the camera axis, a small nose shadow beneath it and symmetrical facial modeling. |
| Clamshell light | Soft upper key and lower fill, open eye sockets and restrained shadows beneath the chin. |
| Rim/edge light | A distinct lit contour separates the subject from the background; retain enough frontal information if identity matters. |
| Motivated practical light | A visible lamp or screen explains the illumination direction and color. |
| Cross-polarized appearance | Reduced glare on nonmetallic surfaces; inspect label readability rather than claiming actual polarizer use. |
| Controlled product reflections | Large clean reflection strips describe curved glossy surfaces; preserve printed detail and the object's silhouette. |

State where the source is relative to camera and subject. “Soft” is about shadow transition,
not just dimness. Keep cast shadows, catchlights and reflections consistent with the setup.
Glossy metal, glass, matte ceramic and skin need different surface cues. Avoid making every
surface equally shiny. Do not equate a reduced-glare prompt with measured color accuracy.

## Subject staging and set design

For people, separate pose, gaze, expression and action: a relaxed seated posture, eyes on
the task, a restrained smile, one hand supporting the teapot. Name important contact points
and keep the action simple enough to inspect. For groups, define count, positions and who
interacts with whom. Avoid asking for simultaneously incompatible hand positions.

For products, choose a hero view, functional-use view, scale/context view or material detail.
Keep defining features visible; make support surfaces and contact shadows plausible.
Specify prop roles and count, background texture, foreground clearance, palette and how
much environmental context is needed. A reflection or prop should support the product,
not accidentally become a duplicate item. Stage a reference-backed campaign around the
same product or subject before varying independent shot dimensions.

## Complex objects and multi-object scenes

Translate a dense brief into an inspectable inventory and a few essential relationships.
For example: two red mugs at upper left, one blue kettle at upper right, three separate keys
along the lower edge. Distinguish count, color/material, position, containment and contact;
getting one does not establish the others. Establish left/right from the viewer's perspective.
For repeated groups, state the members of each group and the total when useful, such as
three place settings, each with one plate, one fork and one glass. Leave visible gaps when
separate silhouettes matter. These directions improve inspectability, not guaranteed counting.

For interactions, describe the connected parts: fingers around a handle, liquid leaving a
spout and landing inside a filter, a dripper supported by the server's mouth, a chain around
the chainring and rear sprocket. Naming every component can still leave impossible joins.
Inspect those joins individually. In glass or mirror scenes, identify what is inside versus
outside and what is a physical object versus a reflected image before counting duplicates.

Record the visible inventory and failed relationships when a result misses. A polished
overall composition can still omit a glass, add chairs or move a bowl to the wrong depth.
Use a concise targeted revision, a reference-backed Edit, or a prepared layout when the brief
and budget support it. An unmasked Edit may change other details, so compare the whole result.
For exact grids or technical assemblies, inspect the actual grid/connection structure; do
not certify coordinate placement or mechanical function from a convincing thumbnail.
For a board, check divisions and alternating colors, then locate each piece by its base/contact
square rather than the top of its silhouette. State which side establishes the coordinate frame.

## Assemble and evaluate

Examples to adapt with the backend's actual output sizes:

- **Shop hero:** Complete ceramic teapot, three-quarter object-level view, on the right third;
  plain ivory left half for copy; distant-camera 85mm-equivalent look, whole product sharp,
  large soft source at camera-left, a grounded shadow and no lettering.
- **Environmental portrait:** Medium waist-up frame, eye-level camera, near 35mm-equivalent
  viewpoint; subject on left, workshop receding behind, eyes sharp and tools recognizable;
  available window light, restrained natural skin texture.
- **Architectural interior:** Wide view from a room corner, level camera and parallel verticals;
  furniture establishes foreground depth, far wall readable, deep focus and controlled window highlights.
- **Anime suspense:** Low viewpoint, diagonal staging, a large near foreground shape, character
  isolated in the distance; hard cel-shadow shapes and a strong backlit silhouette. Describe
  these drawn forms rather than requiring a physically calibrated lens or shutter.
- **Action still:** Side view of a cyclist moving left to right, gaze room on the right;
  comparatively sharp rider, laterally streaked background and visibly rotating wheels;
  specify the action appearance instead of promising a real camera exposure.

When testing, hold the subject and other directions constant and change one dimension.
Compare eye-level versus overhead, a near/wide versus distant/tight viewpoint, or shallow
versus deep focus. A changed focal-length number alone is a weak test of spatial control.
For a composition test, inspect occupied areas and crop boundaries; for an angle test,
inspect visible surfaces and horizon; for optics, inspect near/far scale and sharpness;
for light, inspect shadow direction, edge quality and reflections. Record adherence and
subject fidelity separately. The study below samples these controls; it does not validate
every combination in this reference.

## Findings from real-engine photo tests

Qwen-Image-2.1-Turbo was tested through the public Image API with 20 generated photos in
ten pairs at 768×768, followed by four revised prompts at 1024×1024. All used eight steps,
guidance 1 and seed 7, without Looks or Rewrite. Every output was inspected at full size,
with independent visual review. All operations succeeded, but several directions were
only partly followed. These are single-seed observations, not optical calibration.

| Tested direction | Observed behavior and useful response |
|---|---|
| Product placement and copy space | The first variant moved the product right but occupied part of the requested empty left half. Stronger wording at 1024 returned a centered product. Do not promise exact layout from text or assume longer prompts/resolution will fix it. |
| Cup-level versus overhead | Overhead was clear. The first side view remained elevated. A follow-up naming the hidden coffee surface and almost edge-on rim lowered the view, but still did not establish a precisely horizontal camera. Describe visible surfaces as well as the angle name. |
| Environmental versus tight portrait | Framing changed visibly, but the environmental figure stayed large and the tight portrait included too much torso. A follow-up with explicit frame boundaries was tighter, but still missed the strict upper-chest boundary. Inspect the crop rather than trusting its label. |
| Near/wide versus distant/telephoto | Background mountain scale and wall recession changed in the intended direction. Requested subject extent was not exact; this does not prove a calibrated focal length or controlled real-world camera position. |
| Shallow versus deep focus | Background sharpness changed, but the deep-focus background remained softer than the kettle. Check every named sharp plane; a nominal f/11 is not enough evidence. |
| Soft versus hard light | Shadow boundaries changed clearly. This was more reliable than the requested portrait lighting pattern. Inspect shadow edges rather than overall brightness. |
| Split versus butterfly portrait light | The initial split-light image lit both cheeks. A more explicit no-fill follow-up increased directional contrast but did not yield a clean half-lit split pattern. Named setups need visible validation. |
| Frozen versus slow water | Stream appearance changed, but slow water retained crisp ridges and the static background was soft. A finger entered one frame despite the no-hands instruction. Motion effects and exclusions need inspection. |
| Clean versus noisy night scene | Visible grain/noise increased while both retained a plausible warm-lamp/cool-window scene. This tests an appearance cue, not a particular sensor or ISO value. |
| Level versus low/upward architecture | Camera height and ceiling coverage changed, but vertical convergence was weak. Do not describe a lower viewpoint alone as successful upward perspective. |

The mechanic portraits and cafe interiors had credible skin, fabric and motivated light
in these samples. Some isolated product shots had a more polished catalog/render-like
appearance; photographic plausibility is a visual judgment, not proof of a real capture.
Realistic materials do not excuse a missed camera instruction. Increased resolution can
help inspect detail, but did not reliably correct composition. The follow-ups changed both
wording and size, so their differences cannot be attributed solely to either change.

Keep the original prompt, result and visible defect when refining. If exact layout or crop
remains essential after the allowed attempts, discuss a prepared composition reference or
an authorized finishing step rather than claiming that the failed text control worked.

## Learn from primary photography sources

- [Nikon: composition guidelines](https://www.nikonusa.com/learn-and-explore/c/tips-and-techniques/5-easy-composition-guidelines) and
  [Nikon School: negative space](https://nikonschool.co.uk/hints-and-tips/how-to-utilise-negative-space-in-your-photography).
- [Nikon: focal length](https://www.nikonusa.com/learn-and-explore/c/tips-and-techniques/understanding-focal-length) and
  [Nikon support: camera position and perspective](https://www.nikonimgsupport.com/na/NSG_article?articleNo=000047395&configured=1&lang=en_SG).
- [Nikon: aperture and selective focus](https://www.nikonusa.com/learn-and-explore/c/tips-and-techniques/understanding-maximum-aperture).
- [Canon: exposure triangle](https://www.canon.com.au/get-inspired/exposure-triangle-basics).
- [Elinchrom: portrait lighting setups](https://elinchrom.com/en/Home/Discover/Educational/Lighting_Guide).

These explain real photographic mechanisms. They are not evidence that a generative backend
implements those mechanisms. Discover its controls and inspect its actual output.
