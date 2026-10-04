// Marking a region: the brush, the overlay on the print, the magnifier, the mask
// the model gets, the rows that say what changes in each area, and the tools.
//
// A plain module and not a Lit tree, and the reason is the one slice 6 settled:
// who owns the redraw. The state here is a drawing. A stroke has to paint in the
// task that asked for it, because the magnifier follows the pointer while the
// stroke is drawn, and the rows have to keep the text a person is typing in them.
// The module redraws its own trees, in its own order, and the page never
// sequences a render it does not own.
//
// The state is the module's own. Nothing is published on `window`: the page asks
// real questions through the handle it takes on `region-mark-ready`, and every
// answer is one of the questions in that handle. The reference list stays the
// page's, because a run posts it, so the guard asks the page for it rather than
// keeping a second copy that could drift.
//
// The canvas belongs to the print, which the stage draws, so the module asks the
// page to draw the stage again when arming the brush changes what is on it.

// The page's helpers, on `region-mark-ready`.
let page = null;

// ---- State ------------------------------------------------------------------
const MARK_TOKEN = '[the region you marked]';
const MASK_ALPHA = 128;         // an alpha at or over this is solid in the mask
// One named colour per region. The prompt has to name the area, so the palette
// holds only colours a prompt can say, and the mask carries them on black.
// Measured 2026-09-26: two regions, both changes landed, no mark in the result.
const MARK_COLOURS = [
  ['#e2761e', 'orange'], ['#e2381f', 'red'], ['#2f9e4f', 'green'], ['#2f6fe0', 'blue'],
];
// The model repaints the area the mark covers, so the brush's width is the only
// precision the user has. Measured 2026-09-26: a mask of the same shape spills 21.4%
// past the object at 22.0% coverage against 14.0% at 18.9%, and the roughness of the
// edge changes nothing. A twentieth is the middle, and anything small wants the thin
// end of this, which a track pad cannot reach by drawing carefully alone.
const MARK_WIDTHS = [
  { divisor: 60, label: 'thin' }, { divisor: 20, label: 'medium' }, { divisor: 8, label: 'broad' },
];
// What the user types for each marked colour. Each row becomes a clause the page
// writes, so the examples below show the shape of an instruction, nothing else.
const REGION_EXAMPLES = [
  'change the background to blue',
  'make this part darker',
  'remove the object here',
  'turn it into a wooden texture',
  'add a small red apple here',
  'replace this with a woven pattern',
  'change this part, and keep the rest of it exactly as it is',
];

let markColour = MARK_COLOURS[0][0];
let markWidth = 1;              // an index into MARK_WIDTHS
let marks = null;               // { strokes, width, height } of the image marked
let marking = false;            // the brush is armed
let drawing = null;             // the stroke in progress
let regionText = {};            // the instruction written for each colour

function editing() {
  return page.editing();
}

function markable() {
  // One reference, and only while it is the frame on the stage, so a stroke
  // always lands on the picture it marks. With more than one reference the
  // prompt would name the mask but not the picture whose region it is, and
  // which one the model picks is untested, so the tool stays away.
  if (!editing() || !page.regionMarking()) return null;
  const list = page.references();
  const first = list[0];
  if (list.length !== 1 || !first || first.source === null || first.source !== page.view()) return null;
  // A reference's pixel size is read asynchronously. Marking before it arrives
  // sized the canvas from a fallback while the mask took the real size, and the
  // strokes were recorded in one space and clipped in the other.
  if (!first.width || !first.height) return null;
  return first;
}

// A brush as wide as a twentieth of the image by default: the same stroke at any
// size. The mark's width travels with the stroke, so a change of width leaves what
// is already drawn alone.
function brushWidth() {
  const reference = marks || { width: 1024, height: 1024 };
  const divisor = MARK_WIDTHS[markWidth].divisor;
  return Math.max(3, Math.round(Math.min(reference.width, reference.height) / divisor));
}

function markCanvas() {
  return document.querySelector('.shot .region-mark');
}

function drawnColours() {
  const seen = [];
  (marks ? marks.strokes : []).forEach(function (stroke) {
    if (stroke.colour && seen.indexOf(stroke.colour) < 0) seen.push(stroke.colour);
  });
  return MARK_COLOURS.map(function (pair) { return pair[0]; }).filter(function (colour) {
    return seen.indexOf(colour) >= 0;
  });
}

// The region a colour names, for the prompt and for the per region inputs.
function markName(colour) {
  const found = MARK_COLOURS.filter(function (pair) { return pair[0] === colour; })[0];
  return found ? found[1] : '';
}

function markInk() {
  return markColour;
}

// ---- Arming the brush --------------------------------------------------------
// An edit starts with the brush in hand: pressing Edit this is enough, and the
// picture on the stage is the one being marked.
function syncMarkTools() {
  const first = markable();
  if (!first) {
    marks = null;
    stopMarking();
    return;
  }
  if (!marking) {
    marking = true;
    marks = { strokes: [], width: first.width, height: first.height };
    page.redraw();  // the brush and its controls are mounted with the print
  }
  syncMarkToggle();
}

function stopMarking() {
  marking = false;
  drawing = null;
  syncMarkToggle();
  const canvas = markCanvas();
  if (canvas) canvas.remove();
  const tools = document.querySelector('.region-tools');
  if (tools) tools.remove();
}

// A mark that no longer belongs to the picture in front of the user goes, and its
// row text goes with it: a region drawn again in the same colour would otherwise
// come back carrying an instruction for a picture it was never about.
function dropMarks(reason) {
  const dropped = drawnColours();
  marks = null;
  marking = false;
  dropped.forEach(function (colour) { delete regionText[colour]; });
  if (reason) page.notify('info', reason);
  syncMarkToggle();
}

function clearMarks() {
  if (!marks) return;
  marks.strokes = [];
  drawing = null;
  paintMarks();
  // The rows, the field and both disabled flags all read the stroke list, so
  // they are recomputed here. Clearing without this left them showing a region
  // that was no longer there, until an Undo happened to recompute them.
  syncMarkToggle();
  page.refresh();
}

// ---- The tools, and the rows -------------------------------------------------
// The brush's own states, on the bar over the print.
function syncMarkToggle() {
  // The rows say what changes in each area; the prompt field stays, for an
  // instruction about the whole picture.
  document.getElementById('region-field').hidden = !drawnColours().length;
  renderRegionRows();
  const undo = document.getElementById('mark-undo');
  const clear = document.getElementById('mark-clear');
  if (!undo || !clear) return;
  const empty = !marks || !marks.strokes.length;
  undo.disabled = empty;
  clear.disabled = empty;
  const size = document.getElementById('mark-size');
  if (size) {
    const label = MARK_WIDTHS[markWidth].label;
    size.setAttribute('aria-label', 'Brush width: ' + label);
    size.title = 'Brush width: ' + label + ', about ' + brushWidth() + ' px. '
      + 'The whole marked area is repainted, so a thin brush marks less of the picture.';
  }
}

// The controls under the print, each with its state. There is no button to put
// the brush down: nothing else wants the print, and a dead end has no way back.
function regionTools(host) {
  const bar = document.createElement('div');
  bar.className = 'region-tools';
  const undo = page.iconButton('undo', 'Take back the last mark', function () {
    if (!marks) return;
    marks.strokes.pop();
    paintMarks();
    syncMarkToggle();
    page.refresh();
  });
  undo.id = 'mark-undo';
  undo.title = 'Take back the last mark.';
  const clear = page.iconButton('trash', 'Clear every mark', clearMarks);
  clear.id = 'mark-clear';
  clear.title = 'Remove every mark.';
  // One button cycling the three widths, so the bar keeps its shape. The next stroke
  // takes the new width and the strokes already drawn keep theirs.
  const size = page.iconButton('brush', 'Brush width', function () {
    markWidth = (markWidth + 1) % MARK_WIDTHS.length;
    syncMarkToggle();
  });
  size.id = 'mark-size';
  bar.append(undo, clear, size);
  MARK_COLOURS.forEach(function (pair) {
    const swatch = document.createElement('button');
    swatch.type = 'button';
    swatch.className = 'swatch';
    swatch.style.background = pair[0] || 'var(--marker)';
    swatch.setAttribute('aria-label', 'Mark in ' + pair[1]);
    swatch.setAttribute('aria-pressed', String(markColour === pair[0]));
    swatch.title = 'Mark in ' + pair[1] + '. A region per colour: the prompt names the ' + pair[1] + ' area.';
    swatch.addEventListener('click', function () {
      markColour = pair[0];
      bar.querySelectorAll('.swatch').forEach(function (other) {
        other.setAttribute('aria-pressed', String(other === swatch));
      });
    });
    bar.append(swatch);
  });
  host.append(bar);
  syncMarkToggle();
}

function renderRegionPreview() {
  const preview = document.getElementById('region-preview');
  const colours = drawnColours();
  preview.hidden = !colours.length;
  preview.textContent = colours.length ? composedPrompt() : '';
}

function regionRow(colour) {
  const row = document.createElement('div');
  row.className = 'region-row';
  const swatch = document.createElement('span');
  swatch.className = 'swatch';
  swatch.style.background = colour;
  swatch.setAttribute('aria-hidden', 'true');
  const input = document.createElement('input');
  input.type = 'text';
  input.value = regionText[colour] || '';
  // A whole instruction, because the page writes a sentence around the row, and
  // a generic one drawn at random, so the example never describes the picture the
  // person is working on.
  input.placeholder = 'For example: ' + REGION_EXAMPLES[Math.floor(Math.random() * REGION_EXAMPLES.length)];
  input.setAttribute('aria-label', 'What changes in the ' + markName(colour) + ' area?');
  input.addEventListener('input', function () {
    regionText[colour] = input.value;
    page.refresh();
  });
  row.append(swatch, input);
  return row;
}

function renderRegionRows() {
  const rows = document.getElementById('region-rows');
  const colours = marking ? drawnColours() : [];
  const wanted = colours.join(',');
  if (rows.dataset.wanted === wanted) return;   // do not rebuild while typing
  rows.dataset.wanted = wanted;
  rows.replaceChildren.apply(rows, colours.map(regionRow));
  renderRegionPreview();
}

// ---- The print, the magnifier, and the mask ----------------------------------
// The overlay is the print's own box, in the print's own pixels, so a stroke
// needs no scaling to reach the mask.
function mountMarkCanvas(pic, reference) {
  const canvas = document.createElement('canvas');
  canvas.className = 'region-mark';
  canvas.width = reference.width || 1024;
  canvas.height = reference.height || 1024;
  canvas.setAttribute('aria-label', 'Mark the area to change');
  canvas.addEventListener('pointerdown', markDown);
  canvas.addEventListener('pointermove', markMove);
  canvas.addEventListener('pointerup', markUp);
  canvas.addEventListener('pointercancel', markUp);
  pic.append(canvas);
  mountLoupe(pic);
  // A hand-drawn mark becomes the extent of the change, so what sits under the brush
  // matters more than it did. See `paintLoupe`.
  paintMarks();
}

function pointOf(canvas, event) {
  const box = canvas.getBoundingClientRect();
  return {
    x: (event.clientX - box.left) * (canvas.width / box.width),
    y: (event.clientY - box.top) * (canvas.height / box.height),
  };
}

// The loupe: the print at three times the size, beside the pointer, so a small
// feature can be traced without zooming the whole print and without the cursor
// covering what is being marked. It has no pointer events, so it never takes a
// stroke, and it appears only while one is being drawn.
const LOUPE_SIZE = 108;      // its own pixels, on screen
const LOUPE_ZOOM = 3;
const LOUPE_GAP = 22;        // clear of the pointer, so the mark stays in view

function mountLoupe(pic) {
  const loupe = document.createElement('canvas');
  loupe.className = 'region-loupe';
  loupe.width = LOUPE_SIZE;
  loupe.height = LOUPE_SIZE;
  loupe.hidden = true;
  loupe.setAttribute('aria-hidden', 'true');
  pic.append(loupe);
}

function loupeCanvas() {
  return document.querySelector('.shot .region-loupe');
}

function hideLoupe() {
  const loupe = loupeCanvas();
  if (loupe) loupe.hidden = true;
}

function screenPointOf(canvas, event) {
  const box = canvas.getBoundingClientRect();
  return { x: event.clientX - box.left, y: event.clientY - box.top };
}

// `point` is in the marked image's own pixels.
function paintLoupe(point, screen) {
  const loupe = loupeCanvas();
  if (!loupe || !marks || !drawing) {
    hideLoupe();
    return;
  }
  loupe.hidden = false;
  const context = loupe.getContext('2d');
  const half = LOUPE_SIZE / (2 * LOUPE_ZOOM);
  context.fillStyle = '#000';
  context.fillRect(0, 0, LOUPE_SIZE, LOUPE_SIZE);
  const print = document.querySelector('.shot .pic img');
  if (print) {
    context.drawImage(print, point.x - half, point.y - half, half * 2, half * 2,
                      0, 0, LOUPE_SIZE, LOUPE_SIZE);
  }
  context.save();
  context.translate(-(point.x - half) * LOUPE_ZOOM, -(point.y - half) * LOUPE_ZOOM);
  context.scale(LOUPE_ZOOM, LOUPE_ZOOM);
  paintStrokes(context, marks.strokes.concat([drawing]), 1, markInk(), 0.85);
  context.restore();
  // A crosshair, because a thin stroke cannot show where its centre is.
  context.strokeStyle = 'rgba(255, 255, 255, .9)';
  context.lineWidth = 1;
  context.beginPath();
  context.moveTo(LOUPE_SIZE / 2 - 7, LOUPE_SIZE / 2);
  context.lineTo(LOUPE_SIZE / 2 + 7, LOUPE_SIZE / 2);
  context.moveTo(LOUPE_SIZE / 2, LOUPE_SIZE / 2 - 7);
  context.lineTo(LOUPE_SIZE / 2, LOUPE_SIZE / 2 + 7);
  context.stroke();
  const pic = loupe.parentElement;
  loupe.style.left = Math.min(Math.max(screen.x + LOUPE_GAP, 0),
                              Math.max(pic.clientWidth - LOUPE_SIZE, 0)) + 'px';
  loupe.style.top = Math.min(Math.max(screen.y + LOUPE_GAP, 0),
                             Math.max(pic.clientHeight - LOUPE_SIZE, 0)) + 'px';
}

function markDown(event) {
  if (!marks) return;
  const canvas = event.currentTarget;
  const point = pointOf(canvas, event);
  canvas.setPointerCapture(event.pointerId);
  // The colour belongs to the stroke, so a later pick does not repaint what is
  // already on the print.
  drawing = { kind: 'line', width: brushWidth(), points: [point], colour: markInk() };
  paintLoupe(point, screenPointOf(canvas, event));
  event.preventDefault();
}

function markMove(event) {
  if (!drawing || !marks) return;
  const point = pointOf(event.currentTarget, event);
  drawing.points.push(point);
  paintLoupe(point, screenPointOf(event.currentTarget, event));
  paintMarks();
}

function markUp(event) {
  if (!drawing || !marks) return;
  marks.strokes.push(drawing);
  drawing = null;
  hideLoupe();
  paintMarks();
  syncMarkToggle();
  page.refresh();
}

// White strokes on the print, which is what the mask will be.
function paintStrokes(context, strokes, scale, colour, alpha) {
  context.globalAlpha = alpha;
  context.lineCap = 'round';
  context.lineJoin = 'round';
  strokes.forEach(function (stroke) {
    context.fillStyle = stroke.colour || colour;
    context.strokeStyle = stroke.colour || colour;
    const points = stroke.points;
    if (points.length === 1) {
      context.beginPath();
      context.arc(points[0].x * scale, points[0].y * scale, (stroke.width * scale) / 2, 0, Math.PI * 2);
      context.fill();
      return;
    }
    context.lineWidth = stroke.width * scale;
    context.beginPath();
    context.moveTo(points[0].x * scale, points[0].y * scale);
    points.slice(1).forEach(function (point) { context.lineTo(point.x * scale, point.y * scale); });
    context.stroke();
  });
}

function paintMarks() {
  const canvas = markCanvas();
  if (!canvas || !marks) return;
  const context = canvas.getContext('2d');
  context.clearRect(0, 0, canvas.width, canvas.height);
  paintStrokes(context, drawing ? marks.strokes.concat([drawing]) : marks.strokes, 1, markInk(), 0.85);
}

function hexChannels(hex) {
  return [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)];
}

function closestColour(palette, red, green, blue) {
  let best = palette[0];
  let distance = Infinity;
  palette.forEach(function (colour) {
    const gap = Math.pow(colour[0] - red, 2) + Math.pow(colour[1] - green, 2) + Math.pow(colour[2] - blue, 2);
    if (gap < distance) {
      distance = gap;
      best = colour;
    }
  });
  return best;
}

// The mask itself: the palette colours on black, hard edged, at the reference's
// own size. The antialiased edge of a stroke is thresholded, so the mask keeps
// the palette colours and black and nothing in between.
function maskDataUrl() {
  const reference = markable();
  if (!reference || !marks || !marks.strokes.length) return null;
  const wide = reference.width || marks.width;
  const tall = reference.height || marks.height;
  const ink = document.createElement('canvas');
  ink.width = wide;
  ink.height = tall;
  const context = ink.getContext('2d');
  paintStrokes(context, marks.strokes, wide / (marks.width || wide), '#fff', 1);
  const drawn = context.getImageData(0, 0, wide, tall).data;
  const flat = document.createElement('canvas');
  flat.width = wide;
  flat.height = tall;
  const mask = flat.getContext('2d').createImageData(wide, tall);
  // The palette colours, as channels, so a region's pixels can be snapped to the
  // exact colour that names it. A canvas hands back its antialiased edge pixels
  // premultiplied, which is a near miss of the colour and a second tone in the mask.
  const palette = MARK_COLOURS.map(function (pair) { return hexChannels(pair[0]); });
  for (let index = 0; index < drawn.length; index += 4) {
    const solid = drawn[index + 3] >= MASK_ALPHA;
    const nearest = solid ? closestColour(palette, drawn[index], drawn[index + 1], drawn[index + 2]) : [0, 0, 0];
    mask.data[index] = nearest[0];
    mask.data[index + 1] = nearest[1];
    mask.data[index + 2] = nearest[2];
    mask.data[index + 3] = 255;
  }
  flat.getContext('2d').putImageData(mask, 0, 0);
  return flat.toDataURL('image/png');
}

// ---- The sentence the run sends ----------------------------------------------
// What the page will send, shown while it is being written, so a fragment that
// only makes sense to the user is visible before the run. `forReader` writes the
// same sentence without the number of the image carrying the mask, which the
// model needs and a reader does not: the mark's own colour already names the
// area. The card uses that form, because the region rows may be the only place
// the instruction was ever written down.
function composedPrompt(forReader) {
  const count = page.references().length;
  const suffix = forReader ? '' : ' of <image' + (count + 1) + '>';
  // A row with nothing in it writes nothing. The prompt may already carry the whole
  // instruction, from the template, and then the rows are a second way to say the same
  // thing rather than the only way. An empty clause used to leave " in the orange area
  // of <image2>" in the sentence.
  const clauses = drawnColours().filter(function (colour) {
    return (regionText[colour] || '').trim();
  }).map(function (colour) {
    return regionText[colour].trim() + ' in the ' + markName(colour) + ' area' + suffix;
  });
  // The template's [the region you marked] becomes the number of the image that
  // carries the mask. Sending the token itself told the model nothing about
  // where the change goes, and the template is the one that names the region.
  const lead = forReader ? ''
    : page.prompt().split(MARK_TOKEN).join('<image' + (count + 1) + '>').trim();
  const written = (lead ? lead + ' ' : '') + (clauses.length ? clauses.join('. ') + '. ' : '');
  return written + 'Keep the background and everything else unchanged.';
}

// ---- The handle the page takes ------------------------------------------------
const handle = {
  // Arm the brush for the reference in force, or put it down. Called wherever the
  // references, the mode or the shown frame change.
  sync: function () { syncMarkTools(); },

  // The rows, the preview and the tools, from the state in hand.
  preview: function () { renderRegionPreview(); },

  // The brush is on the print: the canvas is mounted and the print takes the drag.
  onPrint: function () { return Boolean(marking && markable()); },

  // The mark goes if it no longer belongs to the picture in front of the user.
  dropStale: function (reason) {
    if (marks && !markable()) dropMarks(reason);
  },

  mount: function (pic) {
    const reference = markable();
    if (marking && reference) mountMarkCanvas(pic, reference);
  },

  tools: function (host) {
    if (marking && markable()) regionTools(host);
  },

  // The questions `blocker` and the run ask of the region.
  markable: function () { return Boolean(markable()); },
  count: function () { return marks ? marks.strokes.length : 0; },
  colours: function () { return drawnColours(); },
  text: function (colour) { return regionText[colour] || ''; },
  name: markName,
  mentions: function (text) { return text.indexOf(MARK_TOKEN) >= 0; },
  withoutMarker: function (text) { return text.split(MARK_TOKEN).join(''); },

  // The mask, and the sentence that names it.
  mask: function () { return maskDataUrl(); },
  composed: function (forReader) { return composedPrompt(forReader); },

  // The Cancel copy: what Run emptied, and what it puts back.
  snapshot: function () {
    return {
      strokes: marks ? marks.strokes.slice() : null,
      text: JSON.parse(JSON.stringify(regionText)),
    };
  },
  setText: function (text) { regionText = text; },
  setStrokes: function (strokes) {
    if (!marks || !strokes) return;
    // The arming above started the stroke list empty, so the strokes go back now.
    marks.strokes = strokes.slice();
    syncMarkToggle();
  },
  clearText: function () { regionText = {}; },
  putDown: function () { marks = null; stopMarking(); },
};

// The door. The page registered its listener while the markup was parsed, and
// this fires while the module is evaluated: after the markup, before any
// interaction, so the handle is in place before the first click. The page hands
// over what it owns and the module cannot see, and takes the handle back.
document.dispatchEvent(new CustomEvent('region-mark-ready', {
  detail: {
    configure: function (helpers) {
      page = helpers;
      return handle;
    },
  },
}));
