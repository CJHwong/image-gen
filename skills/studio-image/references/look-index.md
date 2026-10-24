# Look index

Pick a look here by what the user wants to see, then put its prompt sentence in front of the
subject sentence. For an Edit of the user's own photo, put it in the instruction instead ("Repaint
this photo as ..."); the style rows were tested in Generate, so scout the Edit first. These rows
are prompt text, not the API's `looks` setting. Every row was generated and inspected on Qwen-Image-2.1-Turbo, with one fixed
subject per section so the looks compare. On another backend, treat a row as a lead and scout it.

- **works**: the look read at a glance and the subject held.
- **partial**: the look read in part, or it changed the subject; the "Watch for" column says how.
- **fails**: the look did not show. Do not offer it.

Rules that hold across sections:

1. Describe the look; do not rely on a name. A painter's or director's name alone gave a country
   and a period, nothing more, and one painter's name replaced the subject with the painter's own
   face. Traits (medium, marks, palette, light, camera position) carry the look.
2. Put the subject first when a strong motif could replace it, and give the count of people:
   staging and period styles add figures.
3. Restate the subject's clothes after a style that has its own period, or the style dresses
   them for its period.
4. Signs without quotes come out as fake lettering. Quote the words, or ask for none.
5. Describe what shows on screen, not how it was made. A process ("photographed under glass",
   "step-printed") did not read.
6. Styles that break the form apart stay figurative: Cubism, Futurism, drip painting and Dada
   collage came back as ordinary paintings or photos. Styles defined by a medium, a flat graphic
   system or a palette (woodcut, mosaic, poster, pointillism) read well.
7. A style tied to an object renders the object: a vase, a carved relief or a pot comes back as a
   photograph of that object with the scene on it.
8. Lens and angle sentences carry into a painting or anime when added after the subject: fisheye,
   a close 14 mm, macro, tilt-shift and anamorphic flares showed in both oil and anime, and a Dutch
   angle tilted further in oil than in a photo. A 300 mm lens and a view from the ground stayed
   plain. With a lens, anime drifted toward painted realism, and macro added fake lettering.
9. A row's main trait held at three seeds (a fisheye bend, an instant-photo frame, a paper-cut
   palette). Its secondary traits did not: a light leak or a wide bottom border showed at one
   seed in three. Promise the main trait and let the scout show the rest.

For why a row behaves as it does, see [style directions](style-directions.md), [shot
design](shot-design.md) and [photography genres](photography-genres.md). The beginner path that
uses this index is the [guided flow](guided-flow.md).

## Adjustments (regenerate)

| Look | Prompt sentence | Verdict | Watch for |
|---|---|---|---|
| Closer | Framed close: the dog's head and shoulders fill the frame. | works |  |
| Wider, show more of the place | A wide view: the dog small in the frame, the whole park, the path and the trees around the bench visible. | works |  |
| From lower, looking up | Seen from low near the ground, looking up at the dog against the sky. | works | Recomposes: the subject may leave its seat or prop. |
| From above | Seen from above, looking down on the dog and the bench. | works | Recomposes: the subject may leave its seat or prop. |
| Warmer light | Warm golden late-afternoon sunlight. | works | Edit keeps the composition; prefer it. |
| Colder light | Cool blue overcast light. | works | Edit keeps the composition, but can bleach a warm-colored subject. |
| More dramatic light | Dramatic light: one low hard sun from the side, deep shadows, the background dark. | works | Edit keeps the composition; prefer it. |
| A different moment | A moment later: the dog leaps off the bench, mid-jump, ears flying. | works | Name the action and its peak (mid-jump). |
| More stylized | As a flat vector illustration with simple shapes and solid colors. | works | Edit keeps the composition; prefer it. |

## Adjustments (Edit, keeps the composition)

| Look | Prompt sentence | Verdict | Watch for |
|---|---|---|---|
| Warmer light | Change only the light to warm golden late-afternoon sunlight. Keep the dog, the bench, the framing and everything else the same. | works |  |
| Colder light | Change only the light to cool blue overcast light. Keep the dog, the bench, the framing and everything else the same. | works | Turned a golden dog gray-white; say the subject keeps its colors. |
| More dramatic light | Change only the light to dramatic light: one low hard sun from the side, deep shadows, a darker background. Keep the dog, the bench and the framing the same. | works |  |
| More stylized | Redraw this as a flat vector illustration with simple shapes and solid colors. Keep the same dog, bench, composition and colors. | works |  |

## Lenses and focus

| Look | Prompt sentence | Verdict | Watch for |
|---|---|---|---|
| 14 mm ultra-wide, close | A photograph taken with a 14 mm ultra-wide lens from close: strong perspective, the near wheel huge, buildings leaning inward at the edges. | works |  |
| Circular fisheye | A circular fisheye photograph: the whole scene inside a round image circle with black corners, extreme barrel distortion, the horizon bent into a curve. | works |  |
| Full-frame fisheye | A full-frame diagonal fisheye photograph: the frame filled edge to edge, straight lines bowed outward, a bulging center. | works | Held at three seeds. |
| 24 mm wide | A photograph with a 24 mm wide lens: the cyclist in the context of the street, mild perspective stretch at the edges. | works | Close to 35 mm; the difference is mild. |
| 35 mm documentary | A documentary photograph with a 35 mm lens at eye level: natural perspective, the cyclist mid-frame, the street readable around him. | works |  |
| 50 mm normal | A photograph with a 50 mm normal lens: the perspective of the human eye, moderate background blur. | works |  |
| 85 mm portrait, creamy background | A portrait with an 85 mm lens at f/1.8: a flattering compressed face, eyes sharp, the background a smooth creamy blur. | works | Held at three seeds: soft background, face sharp. |
| 135 mm head-and-shoulders | A head-and-shoulders portrait with a 135 mm lens: strong compression, the background melted into soft color. | works | Barely differs from 85 mm. |
| 300 mm telephoto compression | A photograph with a 300 mm telephoto lens from far down the street: the buildings and lamps stacked and compressed close together, the cyclist small but sharp. | partial | Little compression; reads as a normal lens. |
| 600 mm super-telephoto | A photograph with a 600 mm super-telephoto lens: an extremely flattened perspective, the café looming right behind the cyclist, heat shimmer. | partial | No stronger than 50 mm; no heat shimmer. |
| Macro raindrops | A 1:1 macro photograph: raindrops on the red paint of the phone box filling the frame, each drop reflecting the cyclist, a wafer-thin focus plane. | partial | Drops on glass in front of the scene, not a frame filled by the drops. |
| Tilt-shift miniature | A tilt-shift photograph from a high window: a thin band of focus across the cyclist, the top and bottom strongly blurred, the street looking like a miniature model. | works | The blur bands held at three seeds; the toy look was weaker at two. |
| Tilt-shift, everything in focus | A tilt-shift photograph with the focus plane tilted along the street: everything from the near curb to the far café sharp, a large-format look. | partial | Looks like an ordinary deep-focus photo. |
| Anamorphic flares | A cinema frame shot on an anamorphic lens: horizontal blue streak flares from the lamps, oval bokeh, slight edge distortion, a widescreen feel. | partial | A row of blue dots, not streak flares; no oval bokeh. |
| Petzval swirl bokeh | A portrait with a Petzval lens: a sharp center and a swirling, spinning bokeh around the edges. | works |  |
| Soft-focus glow | A soft-focus portrait lens: a sharp core wrapped in a glowing halo, highlights blooming. | partial | Very little glow. |
| Pinhole camera | A pinhole camera photograph: soft overall focus with infinite depth, strong vignetting, slight motion smear from a long exposure. | works |  |
| Mirror lens donut bokeh | A photograph with a 500 mm mirror lens: ring-shaped donut bokeh from the street lights, low contrast, a compressed view. | fails | No ring bokeh. |
| Split diopter, near and far both sharp | A frame with a split diopter: the red phone box in the near left foreground and the café door far right both sharp, a blurred seam between them. | works |  |
| Probe lens at street level | A probe lens shot from ground level between the puddles: the tiny lens very close to the wet cobbles, the cyclist towering, deep focus. | works |  |
| f/1.2, razor-thin focus | A portrait at f/1.2: only the near eye sharp, the ear and beard already soft, the background dissolved. | partial | The whole face stays sharp; only the background blurs. |
| f/16 deep focus | A photograph at f/16 with deep focus: the near puddle, the cyclist and the far café all sharp. | works |  |

## Film, cameras and formats

| Look | Prompt sentence | Verdict | Watch for |
|---|---|---|---|
| IMAX 70 mm | An IMAX 70 mm film frame: immense resolution and clarity, fine grain-free detail, a vast tall frame, deep rich color. | partial | A clean cinema frame; the format itself does not show. |
| 65 mm epic film frame | A 65 mm epic film frame: wide majestic composition, rich saturated color, very fine grain, classic large-format cinema. | partial | Looks like any cinematic frame; no visible difference from 35 mm or 16 mm. |
| 35 mm motion picture frame | A 35 mm motion picture frame: organic film grain, a gentle highlight rolloff, a 1.85 cinematic grade. | partial | Clean cinematic grade, almost no grain. Ask for grain by name if you want it. |
| 16 mm indie documentary frame | A 16 mm film frame: coarse visible grain, softer detail, slight gate weave, an indie documentary feel. | partial | Fine grain shows at full size only; the frame looks like the 35 mm one. |
| Super 8 home movie | A Super 8 home movie frame: heavy grain, warm faded color, soft focus, light leaks at the edges, a rounded frame. | works | Rounded dark frame at three seeds; the light leak showed at one. |
| VHS camcorder frame | A VHS camcorder frame: low resolution, chroma bleed, tracking lines at the bottom, a timestamp-like overlay without readable text, washed color. | partial | Adds a fake caption bar of unreadable text at the bottom. Ask for no text. |
| Hi8 camcorder video | A Hi8 camcorder frame: soft interlaced video, oversaturated reds, a slight smear on bright lights. | partial | Reads as a plain soft photo. |
| Warm portrait negative film (Kodak Portra) | A photograph on Kodak Portra 400 film: soft warm skin tones, muted pastel greens, fine grain, gentle contrast. | partial | Muted and smooth, but close to a plain photo; no visible grain. |
| 1960s-90s slide film, cool blues (Ektachrome) | A photograph on Ektachrome slide film: crisp cool blues, high saturation, deep shadows. | works | Strong blue cast over the whole frame. |
| Kodachrome slide film | A photograph on Kodachrome: rich reds, deep contrast, the vintage color of the 1960s. | partial | Came out dark, not rich red. |
| Night tungsten film, teal shadows (CineStill 800T) | A photograph on CineStill 800T: tungsten-balanced teal shadows, red halation glowing around every light. | partial | Teal cast shows; the red glow around lights is faint. |
| Gritty black and white, pushed film (Tri-X) | A black and white photograph on Tri-X pushed two stops: gritty heavy grain, crushed blacks, high contrast. | works | Turns the scene black and white; a red object keeps its color. |
| Polaroid instant photo, dreamy | A Polaroid SX-70 instant photograph: soft dreamy color, a milky shadow tone, the white instant frame with a wide bottom border. | works | White frame at three seeds; the wide bottom border at one. |
| Small instant photo with flash | An Instax Mini instant photo: bright flash-lit subject, saturated color, the small white frame. | works | White frame; flash-lit subject. |
| Large-format view camera | An 8 x 10 large-format view camera photograph: extraordinary detail and tonality, shallow focus despite the wide view. | partial | Reads as a plain sharp photo. |
| Daguerreotype, 1840s silver plate | A daguerreotype: a mirror-like silver plate, a ghostly sharp image, a brass mat with rounded corners, tarnish around the edges. | works | Brass mat and tarnish; monochrome. |
| Wet-plate tintype | A wet-plate tintype portrait: silver on black iron, shallow focus, streaks and pour marks of collodion at the edges, a stern expression. | works | Dark plate with pour marks at the edges. |
| Cyanotype blue print | A cyanotype print: the whole image in Prussian blue and white on textured paper, brushed chemical edges. | works | Whole image Prussian blue with brushed edges. |
| Toy camera with dark vignette (Holga) | A Holga toy camera photograph: a heavy dark vignette, soft blurry corners, a light leak streak, square 6 x 6 frame. | works | Heavy vignette; the frame stays the requested ratio, not square. |
| Cross-processed film, yellow-green and cyan | A Lomo LC-A cross-processed photograph: shifted yellow-green highlights, saturated cyan shadows, a dark vignette. | works | Strong color shift; dark corners. |
| Disposable camera with flash | A disposable camera flash photograph: a harsh direct flash, red-eye-like reflections, the background falling to black, a date stamp look without readable digits. | works | Harsh flash, the background falls dark. |
| Half-frame diptych, two frames side by side | A half-frame film diptych: two vertical frames side by side on one strip, the cyclist approaching in the left and passing in the right. | works | Two frames of two moments on one strip. |
| Panoramic film frame in black borders (XPan) | An XPan panoramic film photograph: a very wide 65:24 frame inside black borders, the street stretched across. | works | Black borders crop the frame to a wide strip. |
| Square medium-format film with black edges | A medium-format 6 x 6 square film photograph: centered composition, smooth tonality, black film rebate edges. | works | Black film edges show, but the frame keeps the requested ratio; ask for 1:1 for a square. |
| Action camera on the chest, handlebars in view | An action camera frame from the cyclist's chest mount: ultra-wide distortion, the handlebars in the foreground, motion blur at the edges. | works | Puts the viewer on the bike; the cyclist disappears. |
| Early 2000s compact digital camera | A photo from an early 2000s compact digital camera: a small CCD sensor, harsh on-camera flash, blown highlights, JPEG artifacts, a slightly cool cast. | partial | Reads as a plain night photo; no harsh flash. |
| Security camera from high on a wall | A CCTV security camera frame from high on a wall: wide distorted view, low-resolution gray-green image, a timestamp-like overlay without readable text. | partial | Wide and bent, but in color, from eye level, with no timestamp. |
| Drone shot straight down | A drone photograph straight down from 30 meters: the street as a graphic pattern, the cyclist a small figure, the phone box a red square. | works | A true top-down view; the subject turns small. |
| Night vision, green with a round mask | A night vision image: grainy monochrome green, bright points blooming, a scope-like round mask. | works | Monochrome green inside a round scope mask. |
| Thermal camera heat map | A thermal camera image: false-color heat map, the cyclist glowing yellow and white, the wet street dark purple. | works | Only the person glows; the rest stays a normal photo in purple. |

## Exposure and light

| Look | Prompt sentence | Verdict | Watch for |
|---|---|---|---|
| Long exposure, car light trails | A long exposure at night: car headlights and taillights drawn into red and white light trails, the cyclist a ghostly streak, the buildings sharp. | works | The cyclist turns into a blur inside the trails. |
| Long exposure, silky rain | A long exposure of the rain: falling rain smoothed into a silky haze, the puddles mirror-still. | partial | The rain shows as drops on the puddles, not as a smooth haze. |
| Star trails over the scene | A night photograph with star trails: concentric circular streaks of stars above the rooftops, the street lit softly below. | works | Moved the scene to a quiet village street to show the sky. |
| Camera swept during the exposure, painterly streaks | An intentional camera movement photograph: vertical brushed streaks of color, an abstract painterly blur of the street. | partial | Only a light motion blur; no abstract streaks. |
| Panning, sharp subject on a streaked background | A panning photograph: the cyclist sharp and the background streaked horizontally with motion blur. | works |  |
| Zoom burst, radial streaks | A zoom burst photograph: radial streaks exploding outward from the cyclist at the center. | works | The subject in the center stays sharp. |
| Flash freeze with a motion trail | A rear-curtain flash photograph: the cyclist frozen sharp by the flash with a motion trail of ambient light behind him. | partial | The trail is faint; reads as a sharp photo. |
| Double exposure, a silhouette filled with a second scene | A double exposure: the cyclist's silhouette filled with the image of the café windows, blended on a light background. | works | Pale background; the scene fills the figure. |
| Stroboscopic, the subject repeated across the frame | A stroboscopic multiple exposure: the cyclist repeated five times across the frame in sequence against a dark street. | works | Five copies, evenly spaced. |
| High-speed freeze of a splash | A high-speed photograph at 1/8000 s: the water splash from the front wheel frozen into crisp droplets in midair. | works | Adds a big crown splash as the subject of the picture. |
| Night lights turned into round bokeh | A night photograph wide open: the café lights and the street lamps turned into large round bokeh balls behind the cyclist. | works |  |
| Into the low sun, rim-lit silhouette (contre-jour) | A contre-jour photograph: shooting into the low sun, the cyclist a rim-lit silhouette, flare and haze. | works | Flare and haze; the face goes dark. |
| Overprocessed HDR | An HDR photograph: every shadow and highlight detailed, glowing halos, an overprocessed tone-mapped look. | partial | Only a bright, evenly lit photo; no halos. |
| High-key, bright white and airy | A high-key photograph: bright white tones, very few shadows, airy and soft. | works | Repaints the dark buildings white. |
| Low-key, mostly black, one hard light | A low-key photograph: mostly deep black, the cyclist lit by one hard light, details lost in shadow. | works | The subject can sink into the dark; name what the light hits. |
| Rembrandt portrait light, a triangle on the cheek | A portrait with Rembrandt lighting: one key light high and to the side, a small triangle of light on the shadowed cheek, a dark background. | works | Dark ground, light from one side. |
| Film noir, light through venetian blinds | A film noir frame: hard light through venetian blinds casting striped shadows across the café window and the cyclist, black and white. | partial | Black and white, but the stripes fall on the wall above, not across the scene. |
| Bleach bypass, desaturated and gritty | A bleach bypass film look: desaturated color, high contrast, silvery gritty shadows. | works | Muted color, silvery shadows; a red object keeps some color. |
| Day for night, deep blue and dark | A day-for-night shot: filmed in daylight and graded deep blue and underexposed to look like night, hard shadows still visible. | works | Very dark; the subject can disappear. |
| Three-strip Technicolor color | A three-strip Technicolor film frame: lush saturated primary colors, deep reds, glowing skin tones, 1950s Hollywood. | partial | Reads as a plain night photo; no lush primaries. |
| Infrared film, pink and red trees | An Aerochrome infrared photograph: green trees turned vivid pink and red, the sky deep, surreal false color. | works | Adds big trees to show the effect; the subject turns small. |
| Redscale film, all red and orange | A redscale film photograph: the film exposed through its back, everything in red, orange and yellow tones. | works |  |

## Angles and camera moves

| Look | Prompt sentence | Verdict | Watch for |
|---|---|---|---|
| Dutch angle, the camera tilted | A Dutch angle: the camera tilted 30 degrees, the street and buildings running diagonally, a tense mood. | partial | Only a slight tilt. |
| From the ground, looking up | A worm's-eye view from the wet street surface: the cyclist towering overhead against the sky. | works | The subject towers overhead. |
| From a high window, looking down | A bird's-eye view from a high window looking down at an angle onto the street and the cyclist. | works | Shows the window frame at the edges. |
| Over the shoulder of someone watching | An over-the-shoulder shot: the dark blurred shoulder of a person at the café window in the foreground, the cyclist outside in focus. | works | Adds a dark figure in the foreground. |
| Through a rain-streaked window | Shot through the rain-streaked café window: reflections of the interior lights overlapping the cyclist outside. | works | Raindrops on the glass in front of the scene. |
| Prism at the lens, rainbow flare | A photograph with a prism held at the lens edge: rainbow flare and a mirrored ghost of the street along one side. | works | A dark blurred band from the prism crosses the frame. |
| Freelensing, a slanted strip of focus | A freelensing photograph: the lens detached and tilted by hand, a slanted strip of focus, light leaks. | fails | A plain sharp photo. |
| Mid rack focus, from near to far | A frame in the middle of a rack focus: focus shifting from the raindrops on the phone box glass to the cyclist, both half soft. | partial | The near object turns huge, but both planes stay sharp. |
| Dolly zoom, stretched background | A dolly zoom frame: the cyclist the same size while the street behind stretches and warps away, a vertigo effect. | fails | A plain street photo. |
| Whip pan, smeared sideways | A frame from a whip pan: the whole image smeared in fast horizontal motion blur, only shapes of color. | works | The subject stays mostly sharp, like a panning shot. |
| Camera rigged to the body, face fixed in frame | A snorricam frame: the camera rigged to the cyclist's body, his face fixed and sharp in the frame while the street swings and blurs behind. | works | Turns the shot into a close portrait of a man. |
| Crash zoom on the face | A crash zoom frame: a sudden zoom in on the cyclist's face, radial blur at the edges. | works | A close face with blurred edges. |
| Handheld documentary frame | A handheld documentary frame: slightly tilted, a little motion blur, imperfect framing, an urgent feel. | partial | Reads as a plain photo. |
| Following behind at hip height | A Steadicam frame following behind the cyclist at hip height: smooth, centered, the street receding ahead. | works | Seen from behind, centered. |
| Crane shot high above the street | A crane shot rising high above the street at the end of its move: the cyclist small, the whole block revealed. | fails | Stays at eye level. |
| Split screen, two scenes side by side | A split-screen frame: the left half the cyclist, the right half a woman waiting inside the café, a thin black line between. | works | Adds the second person you name in the other half. |

## Art across history

| Look | Prompt sentence | Verdict | Watch for |
|---|---|---|---|
| Prehistoric cave painting | A prehistoric cave painting on rough limestone: red ochre and charcoal figures, simple outlined animals and stick-like people, cracks and mineral stains in the rock. | works |  |
| Egyptian tomb painting | An ancient Egyptian tomb painting on plaster: figures in strict profile with the eye and shoulders shown frontally, flat ochre, blue and green, a register line, hieroglyph-like border bands without real text. | works | Adds a procession of extra figures; count the people. The hieroglyph band is decoration, not text. |
| Greek black-figure vase | An ancient Greek black-figure vase painting: black silhouettes with incised lines on orange clay, a meander border, the curve of the vase. | works | Renders a photo of the whole vase, not a flat picture. |
| Han dynasty brick relief | A Han dynasty Chinese tomb brick relief rubbing: flat gray stamped figures, energetic outlines, the texture of molded clay. | works | Renders a photo of a gray carved slab. |
| Maya mural | A Maya mural on lime plaster: bold black outlines, Maya blue and red ochre, figures in profile with elaborate headdresses, glyph-like panels without real text. | works | The person becomes a noble in a headdress. |
| Assyrian stone relief | An Assyrian low relief carved in gray alabaster: stylized figures in profile, patterned beards and water, shallow carved layers, no color. | works | Adds a second figure. |
| Minoan fresco | A Minoan fresco from Bronze Age Crete: lively curving figures, flat areas of blue, red and yellow, wavy bands, flaking plaster edges. | works | Adds a second figure. |
| Moche fine-line pottery | A Moche fine-line painting on a cream ceramic vessel: thin red-brown lines, lively narrative figures, no shading. | works | Renders the pot itself; adds a child. |
| Roman wall fresco (Pompeii) | A Roman wall fresco as in Pompeii: soft painted figures, deep Pompeian red panels, illusionistic architecture, faded and cracked plaster. | works |  |
| Roman floor mosaic | A Roman floor mosaic made of small stone tesserae: visible grout lines, limited earth colors and blue, a geometric guilloche border. | works |  |
| Aztec codex page | A pre-Columbian Aztec codex page on deerskin: flat colors framed with black lines, stylized figures in profile, symbolic water signs. | partial | Comes out as a modern flat illustration; little codex character. |
| Byzantine icon | A Byzantine icon: egg tempera on a wooden panel, a gold leaf background, elongated solemn figures, flat inverse perspective, a craquelure surface. | works | Turns the person into a haloed saint and adds a second figure. |
| Ethiopian church painting | An Ethiopian Orthodox church painting: large almond eyes, bold black outlines, flat red, yellow and green, figures facing forward. | works | A frontal close portrait; the boat becomes small. |
| Chinese gongbi on silk | A Chinese gongbi painting on silk: precise fine outlines, layered mineral colors, delicate detail, an aged silk tone. | partial | Muted and semi-real; the fine outlines are weak. |
| Insular illuminated manuscript | An Insular illuminated manuscript page: interlaced knotwork borders, spirals, flat bright pigments on vellum, stylized figures. | works | The figure inside the border is plain. |
| Blue-and-white glazed tile panel | An Islamic glazed tile panel: the scene drawn in cobalt blue, turquoise and white, framed by an interlacing geometric star border. | works |  |
| Romanesque church fresco | A Romanesque church fresco: stiff frontal figures with big hands, strong outlines, earth colors, flat bands of color behind them. | works | Adds two stiff frontal figures. |
| Gothic stained glass | A Gothic stained glass window: pieces of jewel-colored glass held by thick black lead lines, light shining through, a pointed arch. | partial | The lead lines frame a painted figure; the figure is not built from glass pieces. |
| Persian miniature | A Persian miniature painting: a high viewpoint with no single perspective, jewel-like colors, delicate patterned water and rocks, a gold sky, fine brushwork. | partial | Gold sky and frame, but plain; no jewel-like detail or patterned rocks. |
| Mughal miniature | A Mughal miniature painting: fine detailed brushwork, a naturalistic face in profile, soft green landscape, a decorated border with flowers and gold. | partial | A flower border on a plain flat scene; little fine detail. |
| Ottoman miniature | An Ottoman miniature painting: flat bright colors, simple figures, a patterned tiled harbor, no cast shadows. | works |  |
| Song dynasty ink landscape | A Northern Song monumental landscape in ink on silk: towering mountains, mist between layers, tiny figures, texture strokes on the rocks, almost monochrome. | works | The person becomes tiny, as the style wants. |
| Japanese yamato-e scroll | A Japanese yamato-e handscroll painting: a blown-off roof view from above, drifting gold clouds, flat mineral colors, simple faces. | works | Gold clouds and flat color; no roofless view. |
| Korean minhwa folk painting | A Korean minhwa folk painting: bold flat colors, playful naive figures, decorative pine and waves, a mulberry paper texture. | works |  |
| Tibetan thangka | A Tibetan thangka painting style: mineral pigments, crisp gold outlines, layered stylized clouds and mountains, a framed silk border. | works | Border and clouds read; the figure is generic. |
| Javanese wayang shadow puppet | A Javanese wayang shadow puppet style: an intricately perforated leather figure in profile with long thin arms, gold and red paint, against a glowing screen. | works |  |
| Early Netherlandish oil | An Early Netherlandish oil painting: meticulous detail, luminous glazes, crisp textures of rope and wood, a clear northern light. | works |  |
| Italian Renaissance fresco | An Italian Renaissance fresco: calm balanced composition, linear perspective, soft blue and earth colors, solid modeled figures. | partial | Reads as an oil painting, not fresco. |
| Renaissance sfumato | A High Renaissance oil painting with sfumato: smoky soft transitions, no hard outlines, a hazy blue distance. | works | Gives the man long hair and a religious look. |
| Mannerism | A Mannerist painting: elongated twisting figures, acidic colors, crowded unstable space. | partial | Not elongated; adds figures. |
| Baroque chiaroscuro | A Baroque oil painting with dramatic chiaroscuro: a strong single light from the side, deep black shadows, rich warm color. | works | Held at three seeds: dark ground, one light from the side. |
| Dutch Golden Age genre painting | A Dutch Golden Age genre painting: quiet daylight from a window, precise textures, a calm domestic mood, muted blue and yellow. | works |  |
| Vanitas still life | A Dutch vanitas still life style: a dark background, a skull, an hourglass and fish laid on a table near the net, glossy oil detail. | partial | Fuses the skull with the person: the fisherman has a skull for a head. |
| Rococo | A Rococo painting: pastel pinks and blues, feathery brushwork, playful curving forms, a soft dreamy light. | works | Turns the man into a child. |
| Neoclassicism | A Neoclassical history painting: clear outlines, sculptural figures, a frieze-like stage, cool restrained color. | partial | An ordinary oil painting; no frieze staging. |
| Copperplate engraving | A 17th century copperplate engraving: fine parallel and cross-hatched lines in black ink on cream paper, no color. | works |  |
| Rinpa gold folding screen | A Japanese rinpa folding screen: a gold leaf ground, bold stylized waves, flat green and blue mineral pigments, the vertical seams of the panels. | works | The waves quote a famous print. |
| Chinese literati ink | A Chinese literati ink painting: loose expressive brushwork, much empty paper, a brief poem column and a red seal without legible text. | works | The poem column is fake characters with a seal. |
| Romanticism, stormy and sublime | A Romantic painting: a stormy dramatic sky, tiny figures against vast nature, turbulent brushwork, sublime light. | works |  |
| Luminism, glassy golden calm | A Hudson River School luminist painting: glassy calm water, golden haze, hidden brushstrokes, a vast quiet sky. | works |  |
| 19th century Realism | A 19th century Realist painting: an ordinary working man painted at life size, earthy palette, honest unidealized detail. | works |  |
| Pre-Raphaelite | A Pre-Raphaelite painting: intense jewel-like color, sharp detail everywhere, flowers and botanical precision, flowing hair. | works | Turned the fisherman into a woman with flowing hair. |
| Impressionism | An Impressionist painting: visible broken brushstrokes, flickering light on the water, pure unmixed colors, painted outdoors. | partial | A smooth realistic oil; the broken brushwork is weak. |
| Pointillism | A Pointillist painting made entirely of small dots of pure color that blend at a distance, calm geometric figures. | works |  |
| Post-Impressionist impasto | A Post-Impressionist painting with thick impasto: swirling directional brushstrokes, vivid yellow and blue, outlined forms. | works | Held at three seeds: swirling yellow sky, blue figure. |
| Symbolism | A Symbolist painting: dreamlike mood, muted mysterious color, flat decorative patterning, a still enigmatic figure. | partial | A plain quiet painting; little dream or pattern. |
| Art Nouveau poster | An Art Nouveau poster: whiplash curving lines, a decorative halo shape, flat muted colors, flowing ornamental border, no text. | works | Adds a halo shape behind the head. |
| Arts and Crafts woodcut | An Arts and Crafts woodcut book illustration: bold black lines, dense leafy border, two flat colors on cream paper. | works |  |
| Academic salon painting | A French academic salon painting: smooth invisible brushwork, idealized anatomy, polished finish, warm soft light. | works |  |
| Shin-hanga woodblock print | A Japanese shin-hanga woodblock print: soft color gradients, atmospheric evening light, wood grain, a quiet poetic scene. | works |  |
| Kalighat painting | A Kalighat painting from Bengal: bold sweeping outlines, rounded figures, flat watercolor on paper, plain background. | works | The man becomes a deity-like figure. |
| Fauvism | A Fauvist painting: wild unnatural colors, red water and green faces, loose bold brushstrokes, flat areas. | works |  |
| Expressionist woodcut | A German Expressionist woodcut: jagged angular cuts, harsh black and white, distorted anxious forms. | works |  |
| Analytic Cubism | An Analytic Cubist painting: the scene broken into faceted planes seen from several viewpoints, brown and gray tones. | fails | An ordinary painting with faint facets. |
| Futurism | A Futurist painting: repeated overlapping forms showing motion, force lines, fragmented energy. | fails | An ordinary painting; no motion lines. |
| Suprematism | A Suprematist composition: floating flat geometric shapes in black, red and yellow on white, the scene reduced to rectangles and circles. | partial | A flat figure with a few color spots, not a composition of shapes. |
| Constructivist poster | A Constructivist poster: diagonal composition, red, black and cream, photomontage of the fisherman, bold geometric blocks, no text. | works |  |
| De Stijl | A De Stijl composition: only black horizontal and vertical lines and rectangles of red, yellow and blue on white. | partial | A line drawing with two color bars; not a grid of color blocks. |
| Bauhaus graphic | A Bauhaus graphic: primary colors, circles, squares and triangles, clean modern geometry, a simplified figure. | works |  |
| Dada collage | A Dada collage: cut-out photographs and printed scraps, absurd juxtapositions, torn paper edges, glued fragments, no readable words. | fails | A photograph with one small scrap. |
| Surrealism | A Surrealist painting: dreamlike impossible juxtapositions, a melting clock on the post, long shadows, a smooth realistic technique. | partial | Quotes a famous melting-clock painting and drops the fisherman. |
| Art Deco poster | An Art Deco poster: streamlined geometric forms, sunburst rays, metallic gold and black, elegant stylized figure, no text. | works |  |
| Mexican muralism | A Mexican muralist fresco: monumental rounded workers, earthy strong color, social realist heroism, a crowded composition. | works | Adds a crowd of workers; count the people. |
| Harlem Renaissance silhouettes and circles | A Harlem Renaissance painting: flat silhouetted figures in purple and blue tones, concentric circles of light, Art Deco geometry. | works |  |
| Socialist Realism | A Socialist Realism painting: a heroic idealized worker, bright optimistic light, polished academic technique. | works |  |
| Drip painting | An Abstract Expressionist drip painting: skeins of poured paint, layered splatters, no recognizable figures except a faint boat shape. | fails | A realistic painting with a few splatters. |
| Color Field | A Color Field painting: large soft-edged rectangles of luminous color, the harbor only as horizontal bands. | partial | Color bands only in the background; the scene stays realistic. |
| Pop Art print | A Pop Art print: Ben-Day dots, thick black outlines, flat bright primary colors, a comic-book look. | works |  |
| Op Art | An Op Art composition: black and white wavy lines creating an optical vibration, the boat outlined by distortion. | works |  |
| Minimalism | A Minimalist image: a few flat shapes, one figure and one boat as simple forms, lots of empty space, two colors. | works |  |
| Photorealism | A Photorealist painting: hyper-sharp detail and reflections, but the smooth even surface of acrylic paint. | works | Comes out as a photograph. |
| Stencil street art | A stencil street art piece sprayed on a concrete wall: two-tone black and red, crisp cut edges, overspray and drips. | partial | Two-tone and drips, but on a plain ground, not a wall. |
| Graffiti wildstyle mural | A graffiti mural on a brick wall in wildstyle: interlocking bright letters-like shapes around the fisherman, outlines and highlights, no readable words. | works |  |
| 1960s psychedelic poster | A 1960s psychedelic concert poster: melting flowing shapes, vibrating complementary colors, swirling patterns, no text. | works | Only the sky turns psychedelic. |
| Polish poster school | A Polish poster school design: painterly surreal metaphor, a bold simple idea, rough textured brushwork, no text. | fails | A plain photograph. |
| Memphis design | A Memphis design style graphic: squiggles, confetti shapes, terrazzo, clashing pastel and black-and-white patterns. | works | Confetti and terrazzo over a realistic scene. |
| Risograph print | A risograph print: two overlapping spot inks, pink and teal, grainy texture, slight misregistration. | works |  |
| Synthwave | A synthwave image: a neon magenta and cyan grid, a striped setting sun, chrome reflections, 1980s retro-future. | works |  |
| Vaporwave | A vaporwave collage: pastel pink and teal, a Greek bust, checkerboard floor, early computer window frames, palm trees. | works | The Greek bust takes the center; the fisherman shrinks. |
| Y2K chrome | A Y2K aesthetic graphic: glossy chrome blobs, bubbly translucent plastic, holographic gradients, futuristic early 2000s. | partial | Turns the person into a chrome statue. |
| Superflat, flat bright shapes with smiling flowers | A Superflat style image: flat bright anime-influenced shapes, smiling flowers, no depth, glossy uniform color. | works | Smiling flowers at all three seeds; draws the man as a cartoon child, one seed a young boy. Restate the age. |
| Glitch art | A glitch art image: pixel sorting, RGB channel shifts, corrupted data blocks across the scene. | partial | Only a red and blue channel shift; no pixel sorting or broken blocks. |
| Voxel art, built from small cubes | A voxel art scene: everything built from small 3D cubes, isometric view, soft ambient light. | works | The water and land go blocky; the figure stays smoother. |
| Afrofuturist collage | An Afrofuturist collage: cosmic backgrounds, geometric patterns, metallic accents, a regal figure, layered textures. | partial | Turns the fisherman into a robed, crowned figure under a cosmic sky. Restate his clothes. |
| Madhubani folk painting (India) | A Madhubani painting from Bihar: every space filled with patterns, double line outlines, fish and birds, bright natural colors. | partial | Flat folk drawing with outlines, but the space is not filled with pattern. |
| Warli white-figure wall painting (India) | A Warli painting: white stick-figure people made of triangles and circles on an earthy red-brown wall. | partial | White figure on red-brown, but drawn as a person, not triangles and sticks. |
| Gond dot-and-dash painting (India) | A Gond painting: figures filled with fine dots and dashes in bright colors, a black background, decorative patterns. | partial | The style held at three seeds, but two seeds changed the fisherman into a woman or a youth. Restate the subject. |
| Otomi embroidery (Mexico) | An Otomi embroidery from Mexico: flat stitched silhouettes of birds and animals in bright single colors on white cotton cloth. | partial | Reads as stitched cloth, but turned the fisherman into a woman. Restate the subject. |
| Huichol yarn painting (Mexico) | A Huichol yarn painting: brightly colored yarn pressed into wax in concentric lines, vivid symbolic forms. | works | Shown as a yarn panel with its edges. |
| Ndebele house painting (southern Africa) | An Ndebele house painting: bold geometric patterns with thick black outlines, bright flat colors on a white wall. | fails | Came back a photo of a painted wall with the man in front. |
| Haitian naive painting | A Haitian naive painting: bright saturated color, flat lush vegetation, many small figures, joyful patterns. | partial | Strong style, but turned the man into a boy and added figures in the trees. |
| Palekh lacquer miniature (Russia) | A Palekh lacquer miniature: tiny detailed figures in gold and bright tempera on a glossy black background. | partial | Renders a photo of an oval lacquer box with the scene on it. |
| Polish layered paper cut | A Polish wycinanki paper cut: symmetrical layered colored paper, roosters and flowers, crisp cut edges. | works | Adds roosters and flowers beside the scene. |
| Chinese red paper cut | A Chinese red paper cut: one sheet of red paper with intricate cut lace patterns, on white. | works | One red on white at all three seeds; adds a big fish at two of three. Inside a cut border. |
| Pennsylvania German fraktur | A Pennsylvania German fraktur: hand-painted birds, tulips and hearts in watercolor, ornamental symmetrical design on old paper, no text. | partial | The ornament takes the top; the scene shrinks to a small drawing. |
| Batik wax-resist textile | A batik textile: wax-resist dye with crackle lines, indigo and brown, repeating motifs around the scene. | partial | Reads as an indigo pen drawing; no crackle lines. |
| South Asian truck art | South Asian truck art: dense bright floral patterns, mirror work, painted panels, reflective decoration around the scene. | fails | Came back a photo of a painted truck at the harbor. |
| Peruvian retablo box | A Peruvian retablo: a small painted wooden box with tiny carved plaster figures inside, bright colors, folk craft. | partial | Renders a photo of a small box with carved figures inside. |

## Painter names alone

| Look | Prompt sentence | Verdict | Watch for |
|---|---|---|---|
| "A painting by Vermeer" (name only) | A painting by Johannes Vermeer. | fails | A generic 19th-century oil; none of the painter's light or interior. |
| "A painting by Van Gogh" (name only) | A painting by Vincent van Gogh. | fails | A smooth realistic oil; no swirling strokes. Use the impasto row. |
| "A print by Hokusai" (name only) | A print by Katsushika Hokusai. | fails | A plain ink-and-wash drawing in Japanese dress; no woodblock print. |
| "A painting by Monet" (name only) | A painting by Claude Monet. | fails | A smooth realistic oil; no broken color. |
| "A painting by Klimt" (name only) | A painting by Gustav Klimt. | fails | Only a floral robe; no gold or ornament. |
| "A painting by Caravaggio" (name only) | A painting by Caravaggio. | fails | Even daylight; no dark ground or spotlight. |
| "A painting by Rembrandt" (name only) | A painting by Rembrandt. | fails | A brown period oil; no strong light from one side. |
| "A painting by Frida Kahlo" (name only) | A painting by Frida Kahlo. | fails | Replaced the fisherman with a likeness of the painter herself. A name can draw the named person. |

## Anime and animation

| Look | Prompt sentence | Verdict | Watch for |
|---|---|---|---|
| 1970s TV anime | A 1970s Japanese TV anime frame: limited animation, thick uneven outlines, flat poster colors, simple painted background, slight film dirt. | partial | Reads as 1980s; no film dirt. |
| 1980s OVA cel | A 1980s Japanese OVA cel frame: dense detailed linework, airbrushed highlights, rich saturated night colors, film grain. | partial | Airbrush and dense lines are weak; a genre scene can drift toward a famous film. |
| Hand-painted countryside film | A hand-painted Japanese animated film frame: soft watercolor backgrounds full of greenery, round-faced simple characters, a gentle muted natural palette, cumulus clouds. | works |  |
| Glowing sky, small figures | A Japanese animated film frame with a hyper-detailed glowing sky: dramatic gradient clouds, lens flare, light rays, sparkling reflections, photographic depth of field, characters small against the sky. | works |  |
| Ukiyo-e animation | An animation frame in the style of an ukiyo-e woodblock print: flat areas of color, bold black outlines, wood grain texture, stylized clouds, a limited palette of indigo, vermilion and ochre. | partial | Puts the person in Edo clothes; restate the clothes. |
| Modern glossy digital anime | A modern Japanese digital anime frame: crisp thin lines, glossy cel shading with soft gradients, glowing particle effects and bloom, cinematic color grading. | works | The particles are faint. |
| Ligne claire comic | A frame in the French-Belgian ligne claire style: clean lines of even weight, flat bright colors with no hatching or shading, detailed realistic backgrounds, simplified characters. | works | Signs come out as fake text; quote them or ask for none. |
| French grotesque caricature, sepia | A French animated film frame with grotesque caricature: exaggerated elongated and bulging characters, a sepia and olive watercolor palette, melancholic 1950s Paris details. | works |  |
| Painterly 3D animation | A French painterly 3D animation frame: 3D models covered in hand-painted brush-stroke textures, thick painterly lighting, a gritty steampunk city, hand-drawn effects. | works | Steampunk barely shows. |
| Black-and-white graphic memoir | A French animated graphic memoir frame: stark black and white only, flat black shapes and white negative space, no gray, simple expressive figures, woodcut-like. | works |  |
| Watercolor storybook | A French animated storybook frame: soft loose watercolor washes, pencil lines visible, lots of white paper, gentle pastel colors. | works |  |
| 2D characters lit like 3D | A Spanish 2D animated film frame with volumetric lighting: hand-drawn characters lit like 3D with soft shadows and rim light, rich textured snowy village, warm window light. | works |  |
| Slapstick comic (tebeo) | A Spanish tebeo comic animation frame: rubbery slapstick characters with big noses and bendy limbs, bold black outlines, flat bright colors, motion lines, comic chaos. | partial | Adds extra characters; count the people. |
| Centered stop-motion, felt puppets | A stop-motion animation frame with felt and fur puppets: perfectly centered symmetrical composition, flat frontal staging, a pastel dollhouse-like set, visible handmade textures, warm autumn palette. | works |  |
| Layered paper cut-outs in fog | A Soviet animated film frame made of layered paper cut-outs photographed under glass: soft fog between layers, muted earth colors, a hushed dreamlike forest edge. | partial | Comes out as a 3D scene, not paper. |
| Carved wooden puppets | A Czech puppet animation frame: carved wooden marionettes with painted faces and jointed limbs, a miniature handmade village set, theatrical lighting. | partial | Duplicates the person; count the people. |
| Flat medieval with Celtic borders | An Irish animated film frame in a flat medieval style: Celtic knotwork borders, flat shapes with decorative patterns, a strong graphic palette of greens and gold, illuminated manuscript look. | works |  |
| Clay animation | A clay animation frame: characters made of plasticine with visible thumbprints, wide mouths, glossy eyes, a small handmade miniature street set. | works | Fake sign text. |
| Chinese ink-wash animation | A 1960s Chinese ink-wash animation frame: soft black ink washes on rice paper, the characters painted in a few brush strokes, lots of empty paper, a pale touch of color. | works | Fake characters on signs. |
| 1920s silhouette cut-outs | A 1920s silhouette animation frame made of black paper cut-outs with fine lace-like detail against a colored tinted backdrop. | partial | Only the people become cut-outs. |
| 1930s rubber-hose cartoon | A 1930s rubber-hose cartoon frame: black and white, characters with bendy tube limbs and white gloves, pie-cut eyes, bouncing buildings, film scratches. | works | The person becomes a cartoon body. |
| 1950s mid-century flat cartoon | A 1950s mid-century modern animation frame: flat geometric shapes, limited animation, off-register blocks of color, sparse stylized backgrounds, textured paper. | works | Off-register color is weak. |
| Halftone comic book | An animated comic-book frame: halftone dots, offset misregistered printing, bold ink lines, flat color with chromatic aberration, comic caption boxes, dynamic angle. | partial | No caption boxes. |
| Korean webtoon | A Korean webtoon frame: clean digital line art, soft airbrushed cel shading, pastel glossy colors, a vertical-scroll comic look. | works |  |

## Director looks

| Look | Prompt sentence | Verdict | Watch for |
|---|---|---|---|
| Low, still, frontal home drama | A film still in the manner of Yasujiro Ozu: the camera low at the height of a person kneeling on tatami, perfectly still and frontal, a quiet Japanese home with sliding doors in layered rectangles, a small red teakettle as the only bright color, soft even light. | works | The story beat can drop out. |
| Telephoto, wind and weather, deep staging | A film still in the manner of Akira Kurosawa: a long telephoto lens compressing the depth, strong wind blowing rain and leaves across the frame, figures staged in deep layers, dramatic weather, high-contrast. | partial | Adds a crowd; count the people. |
| Dream and reality sliding together (anime) | An anime film still where reality and dream slide together: the woman's reflection in a mirror shows a different version of her, a crowded city outside the window bleeding into the room, sharp realistic animation with uncanny details. | works |  |
| Power lines, held shot, Mincho title | An anime film still: utility poles and tangled power lines against the sky outside the window, a long static held shot, stark composition, and a white title card text in a thin Mincho font reading "手紙" in the corner. | partial | The motif replaces the subject; put the subject first. |
| Rainy, still, teal-gray city (anime) | An anime film still: a melancholic rain-soaked city outside the window, still contemplative framing, water reflections, a flock of birds in gray sky, a cold teal and gray palette, a basset hound asleep on the floor. | works |  |
| Rubbery bending space, bold colors | An animated film still with rubbery stretched perspective: the room bends and bulges, flat bold saturated colors, wobbly hand-drawn lines, playful exaggerated poses. | partial | The person turns into a Western TV cartoon. |
| Overexposed pastel, light leak | A film still with dreamy overexposed pastel light: blown-out window glow, soft handheld framing, a light leak, gentle cyan and pink tones, intimate and nostalgic. | works |  |
| Neon green and red, smoky corridor | A film still with step-printed smeared motion: the woman sharp while the world around her blurs in streaks, saturated neon green and red light, a narrow smoky corridor apartment, cigarette smoke, a clock on the wall. | partial | The step-printed smear does not show. |
| Static wide frame, reflection over city lights | A film still in the manner of Edward Yang: a Taipei apartment at dusk seen in a wide static frame, the woman reflected in the window glass over the city lights outside, cool fluorescent interior light. | works |  |
| One long static shot, small figure in a doorway | A film still: one long wide static shot, natural light only, the woman a small distant figure in a deep doorway of an old Taiwanese house, much of the frame in shadow, patient and observational. | works |  |
| One-point corridor, stare into the lens | A film still in the manner of Stanley Kubrick: a perfect one-point perspective down a symmetrical corridor to the table at the far end, wide-angle lens, cold even light, the woman staring straight at the camera. | works |  |
| Tiny figure in a glass-and-steel grid | A film still in the manner of Jacques Tati: a modernist glass-and-steel apartment in gray and blue, many reflecting glass panes, the woman a tiny deadpan figure in a large geometric space. | works |  |
| Ruined room, dripping water, sepia | A film still in the manner of Andrei Tarkovsky: an old ruined room with water dripping from the ceiling into puddles on the floor, moss on the walls, long contemplative stillness, muted sepia colors with one area in color. | works | One area in color does not show. |
| Extreme close-up of the eyes | A film still in the manner of Sergio Leone: an extreme close-up of the woman's eyes filling the wide frame as she sees the letter, sweat and dust on her skin, harsh sunlight. | works |  |
| Saturated red melodrama | A film still: saturated primary red everywhere, a bold patterned wallpaper and a red kitchen, the woman in a red dress, melodramatic lighting, vivid green and yellow accents. | works |  |
| Centered symmetric pastel | A film still: a perfectly centered symmetrical composition, flat frontal staging, a pastel pink and mint dollhouse-like apartment, the woman standing exactly in the middle facing the camera, deadpan expression. | works |  |
