// The form: what the sidebar holds, what it derives, and what it says on the
// run button.
//
// The controls the form is drawn from are components, and each one takes what it
// cannot read for itself on its own door. What is left is the model behind them:
// the mode in force, the references, the Look picks, the size derivations, the
// cost of a run, and the sentence the run button carries. That is this module.
//
// The page's own script is still a classic script, so it cannot import this
// module. The listener is registered while the markup is parsed and this fires
// while the module is evaluated: after the markup, before any interaction, so
// the form is drawn before the first click. This module is declared first of the
// modules for the same reason, and every later door is handed on to it.

const page = {};

function editing() {
  return document.getElementById('mode-edit').checked;
}

function currentMode() {
  return page.modes[editing() ? 'edit' : 'generate'];
}

function paramSpec(id) {
  return currentMode().params.find(function (param) { return param.id === id; });
}

function maxReferences() {
  return currentMode().max_references;
}

// A choice param fills its hidden select, so the request stays a plain form.
function fillSelect(select, id) {
  const spec = page.studio.modes.map(function (mode) {
    return mode.params.find(function (param) { return param.id === id; });
  }).find(Boolean);
  if (!spec) return;
  spec.choices.forEach(function (choice) { select.add(new Option(choice.label, choice.value)); });
  select.value = spec.default;
}

// A number param takes its range from the spec of the mode in use. The value
// carries over a mode switch when it still fits the new range. An input takes
// its default the first time a mode applies it, because a range input never
// starts empty: it reads as the middle of its range, and the new range clamps
// that to a value that fits, such as 10 for a guidance of 1 to 10. A
// choice param takes the mode's default on every switch, because a mode
// switch starts over: an edit keeps the image's shape, a generate is square.
function applyParams() {
  const form = page.el.form;
  form.querySelectorAll('[data-param]').forEach(function (node) {
    node.hidden = !paramSpec(node.dataset.param);
  });
  document.getElementById('size-field').hidden = !paramSpec('size') && !paramSpec('resolution');
  currentMode().params.filter(function (param) { return param.kind === 'number'; }).forEach(function (param) {
    const input = document.getElementById(param.id);
    if (!input) return;
    input.min = param.minimum === null ? '' : param.minimum;
    input.max = param.maximum === null ? '' : param.maximum;
    input.step = param.step === null ? 'any' : param.step;
    const value = Number(input.value);
    const fits = input.value !== '' && (param.minimum === null || value >= param.minimum)
      && (param.maximum === null || value <= param.maximum);
    if (!fits || !input.dataset.applied) input.value = param.default;
    input.dataset.applied = '1';
  });
  currentMode().params.filter(function (param) { return param.kind === 'choice'; }).forEach(function (param) {
    const select = document.getElementById(param.id);
    if (select) select.value = param.default;
  });
}

function spell(seconds) {
  if (seconds < 90) return Math.max(5, Math.round(seconds / 5) * 5) + 's';
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round((seconds % 60) / 15) * 15;
  if (rest && rest < 60) return minutes + ' min ' + rest + 's';
  return (minutes + (rest ? 1 : 0)) + ' min';
}

// ---- References -----------------------------------------------------------
// References live in one array, whatever put them there: the picker, a drop,
// a paste, or "Use as reference" on a result. Each mode sets how many it
// takes. When a mode takes one, a new one replaces the old. Files are read here
// and posted as base64 in a normal form field, which keeps the server off
// multipart parsing that the standard library no longer ships.
//
// The list is drawn by components/reference-list.js from the store, which this
// mirrors on every change. What stays here is the list itself, the zone that
// fills it, and the three things the page owns: the form's flag, the file
// input's `multiple`, and the Remove all button.
function referenceLimit() {
  return maxReferences();
}

function lastReference() {
  return page.references()[page.references().length - 1];
}

// The follow-ups a new list needs. The tree itself is the module's: this
// pushes the array into the store, which is what redraws it.
function renderReferences() {
  const count = page.references().length;
  const form = page.el.form;
  form.classList.toggle('has-ref', count > 0);
  page.el.referenceInput.multiple = editing();
  document.getElementById('clear-reference').hidden = count < 2;
  pushReferences();
  refreshForm();
  page.region().sync();
  // An empty stage says what to do next, and that depends on the references.
  if (page.view() === null) page.renderStage();
}

// The estimate, the "Match" size, the progress card's shape and the region
// canvas all need the pixel size, so it is read once here. Reading it is
// asynchronous, which is why the size is checked rather than assumed.
function probeSize(entry) {
  if (entry.width) return;
  const probe = new Image();
  probe.onload = function () {
    entry.width = probe.naturalWidth;
    entry.height = probe.naturalHeight;
    renderReferences();
  };
  probe.src = 'data:image/png;base64,' + entry.b64;
}

// `source` is the id of the frame the image came from; an upload has none.
function addReference(b64, name, source) {
  if (referenceLimit() === 1) page.setReferences([]);
  if (page.references().length >= referenceLimit()) {
    page.notify('info', 'Edit takes at most ' + maxReferences() + ' images.');
    return;
  }
  const entry = { b64: b64, name: name, width: 0, height: 0, source: source || null };
  page.references().push(entry);
  probeSize(entry);
  renderReferences();
}

function addFiles(files) {
  Array.from(files).filter(function (file) {
    return file.type.startsWith('image/');
  }).forEach(function (file) {
    const reader = new FileReader();
    reader.onload = function () {
      addReference(reader.result.split(',')[1], file.name);
    };
    reader.readAsDataURL(file);
  });
}

// ---- Size -----------------------------------------------------------------
// The hidden selects stay the form fields, filled by the server as before.
// The chips only drive them, so the request is exactly what it was.
let sizeOptions = [];
let ratios = [];

function readSizes() {
  sizeOptions = Array.from(page.el.sizeSelect.options).filter(function (option) {
    return option.value !== 'match';
  }).map(function (option) {
    const parts = option.value.split('x').map(Number);
    const named = option.textContent.match(/\((\d+:\d+)\)/);
    return { value: option.value, width: parts[0], height: parts[1],
             ratio: parts[0] === parts[1] ? '1:1' : (named ? named[1] : parts[0] + ':' + parts[1]) };
  });
  ratios = [];
  sizeOptions.forEach(function (option) {
    if (ratios.indexOf(option.ratio) < 0) ratios.push(option.ratio);
  });
}

function currentOption() {
  return sizeOptions.find(function (option) { return option.value === page.el.sizeSelect.value; });
}

function setSelect(select, value) {
  select.value = value;
  select.dispatchEvent(new Event('change', { bubbles: true }));
}

// A resolution param sets pixels only, and the shape follows the reference.
// A size param sets both. Which one a mode has decides the size, not the mode.
function followsReference() {
  return Boolean(paramSpec('resolution'));
}

function editResolution() {
  const chosen = page.el.resolutionSelect.value;
  if (chosen !== 'match') return Number(chosen);
  const reference = lastReference();
  if (!reference || !reference.width) return 1024;
  const side = Math.round(Math.sqrt(reference.width * reference.height));
  const cap = currentMode().estimate && currentMode().estimate.match_cap;
  return cap ? Math.min(side, cap) : side;
}

// The shape the next image will have, for the progress card and its frame.
function targetRatio() {
  const reference = lastReference();
  const referenceRatio = reference && reference.width ? reference.width / reference.height : 1;
  if (followsReference()) return referenceRatio;
  const current = currentOption();
  return current ? current.width / current.height : referenceRatio;
}

// ---- Count, steps, seed ------------------------------------------------------
function clampCount() {
  const countInput = page.el.countInput;
  const value = Math.min(page.maxBatch, Math.max(1, parseInt(countInput.value, 10) || 1));
  countInput.value = value;
  document.getElementById('count-shown').textContent = '×' + value;
  page.el.countToggle.setAttribute('aria-label', value + (value === 1 ? ' image' : ' images') + ', change the count');
  return value;
}

// The count is part of the run button, so it reads as "Generate ×2". The menu
// opens on the current count, marked with a check.
function openCount() {
  const menus = page.menus();
  const countMenu = page.el.countMenu;
  const current = clampCount();
  countMenu.replaceChildren();
  for (let count = 1; count <= page.maxBatch; count++) {
    const option = menus.menuItem('check', count + (count === 1 ? ' image' : ' images'), function () {
      page.el.countInput.value = count;
      clampCount();
      refreshForm();
      page.el.countToggle.focus();
    });
    option.setAttribute('role', 'menuitemradio');
    option.setAttribute('aria-checked', String(count === current));
    countMenu.append(option);
  }
  menus.toggleMenu(countMenu);
  if (!countMenu.hidden) countMenu.querySelector('[aria-checked=true]').focus();
}

// The advanced panel's own readouts belong to components/advanced-panel.js,
// which draws them from the store. Two things stay here. The reference
// strength is not part of that panel. And Clear is a real button, so it stays
// in the page's markup, where a screen reader and the keyboard reach it.
function renderStrength() {
  const steps = document.getElementById('steps').value;
  document.getElementById('strength-value').textContent =
    Number(document.getElementById('strength').value).toFixed(2);
  document.getElementById('strength-hint').textContent = 'Runs ' + stepsToRun() + ' of ' + steps +
    ' steps. Higher stays closer to the starting image.';
}

function renderClearSeed() {
  document.getElementById('clear-seed').hidden = !document.getElementById('seed').value.trim();
}

// mflux skips the start of the schedule for a starting image:
// init_time_step = max(1, int(steps * strength)). Only the rest runs.
function stepsToRun() {
  const steps = Number(document.getElementById('steps').value) || 0;
  const strength = Number(document.getElementById('strength').value) || 0;
  return steps - Math.max(1, Math.floor(steps * strength));
}

// ---- Estimate and the run button -----------------------------------------
// Cost, before you spend it. The backend gives seconds per step at one
// megapixel and how that grows with size; its adapter holds the measurements.
// A mode without an estimate shows no time.

// The mode's guidance scale, whichever of the two names it declares.
function scaleParam() {
  return paramSpec('cfg') ? 'cfg' : paramSpec('guidance') ? 'guidance' : '';
}

// A backend with a negative prompt runs the second pass only for a set
// negative: qwen21 at guidance 2.5 and a blank negative takes the time of
// guidance 1. A backend without one runs it for any guidance above 1.
function twoPass() {
  const id = scaleParam();
  if (!id || Number(document.getElementById(id).value) <= 1) return false;
  return !paramSpec('negative') || Boolean(negativeText());
}

function costKey() {
  return page.studio.backend.id + ' ' + currentMode().id + ' ' + sentReferences() + ' images'
    + (twoPass() ? ' two-pass' : '');
}

// The images a run will carry: the references, and the mask when one is drawn.
// Each one is encoded and attended to, so the count is part of the cost.
function sentReferences() {
  return page.references().length + (page.region().count() ? 1 : 0);
}

// One more image costs more per step, by the factor the backend measured. It
// scales the constants only: a rate this device has shown already has the shape
// it was shown for, because the key carries the count.
function referenceFactor(model) {
  if (!model.per_reference) return 1;
  return 1 + model.per_reference * Math.max(0, sentReferences() - 1);
}

function targetPixels() {
  if (followsReference()) return Math.pow(editResolution(), 2);
  const current = currentOption();
  return current ? current.width * current.height : 1024 * 1024;
}

// Seconds per step for the form as it stands, from what this device has
// shown so far or else from the backend's constants.
function stepSeconds() {
  const model = currentMode().estimate;
  if (!model) return 0;
  // The constant holds the passes it was measured with, so rescale it to the
  // passes the form asks for. A learned rate is already per pass count.
  const passes = (twoPass() ? 2 : 1) / (model.two_pass ? 2 : 1);
  const learned = page.learnedCost[costKey()];
  const cost = learned === undefined
    ? model.step_cost * passes * referenceFactor(model) : learned;
  return cost * Math.pow(targetPixels() / 1e6, model.exponent);
}

function estimate() {
  const count = clampCount();
  const images = count > 1 ? count + ' images' : '';
  const model = currentMode().estimate;
  if (!model || !paramSpec('steps')) return images;
  const steps = Number(document.getElementById('steps').value) || 0;
  const perStep = stepSeconds();
  const overhead = model.overhead_per_image ? count * model.overhead : model.overhead;
  const time = 'about ' + spell(count * steps * perStep + overhead);
  return images ? images + ', ' + time : time;
}

// What stops a run, said on the button itself rather than as an error after.
function blocker() {
  const region = page.region();
  if (editing() && !page.references().length) return 'Add an image to edit';
  // With a region marked, the per area rows are the prompt, so the field is not
  // asked for one.
  const regions = region.count();
  if (!regions && !page.el.promptInput.value.trim()) return editing() ? 'Describe the change' : 'Write a prompt';
  // The region token is not the user's to fill: the page replaces it with the
  // number of the image carrying the mask. Without a drawn region there is no
  // such image, so the run waits for one. With the tool off, the wait would never
  // end, so that case names the way out instead.
  if (region.mentions(page.el.promptInput.value) && !regions) {
    return region.markable() ? 'Draw the region this prompt names' : 'Remove all but one image, to draw a region';
  }
  const typed = region.withoutMarker(page.el.promptInput.value);
  if (PLACEHOLDER.test(typed)) return 'Fill in the [brackets]';
  if (regions) {
    // The prompt may name the region itself, from the template, and then a row is a
    // second way to say the same thing rather than the only way. The page writes
    // whichever the user filled, and asks for a row only when nothing else says what
    // changes.
    const named = region.mentions(page.el.promptInput.value);
    const silent = region.colours().filter(function (colour) { return !region.text(colour).trim(); });
    if (!named && silent.length) return 'Say what changes in the ' + region.name(silent[0]) + ' area';
    // The page writes a sentence around the row, so a bare phrase is a fragment:
    // "to green" would read as "to green in the orange area of <image2>". A comma
    // means the row carries its own clause, and an instruction may open with a
    // preposition: "in the corner, add a lamp" is a whole one.
    const fragment = region.colours().filter(function (colour) {
      const typed = region.text(colour).trim();
      return /^(to|for|in|with|as)\b/i.test(typed) && typed.indexOf(',') < 0;
    });
    if (fragment.length) {
      return 'Write a whole instruction for the ' + region.name(fragment[0])
        + ' area, for example: change the cloth to green';
    }
  }
  return '';
}

function renderRunButton() {
  if (page.busy()) return;
  const reason = blocker();
  page.el.go.disabled = Boolean(reason);
  page.el.goSub.textContent = reason || estimate();
}

// A negative prompt works only through a guidance above 1, and the spec
// names the value it needs in `with_negative`. So when a negative prompt
// appears, the page raises the scale to that value. When it goes, the page
// puts the old value back, unless the scale was moved by hand in between.
// A scale moved below 1 by hand stays there, with a note.
let hadNegative = false;
let raisedFrom = null;    // the scale's value before the page raised it

// The negative the model gets: the typed one, then the avoid parts of the
// picked Looks. Only the typed one is the user's own text.
function typedNegative() {
  return paramSpec('negative') ? document.getElementById('negative').value.trim() : '';
}

function negativeText() {
  return [typedNegative(), lookAvoids()].filter(Boolean).join(', ');
}

function followNegative() {
  const id = scaleParam();
  const spec = id ? paramSpec(id) : null;
  const note = document.getElementById('negative-note');
  const wanted = Boolean(negativeText());
  if (!spec || spec.with_negative === null) {
    note.hidden = true;
    hadNegative = wanted;
    return;
  }
  const input = document.getElementById(id);
  if (wanted && !hadNegative && Number(input.value) < spec.with_negative) {
    raisedFrom = input.value;
    input.value = spec.with_negative;
  }
  if (!wanted && hadNegative && raisedFrom !== null && Number(input.value) === spec.with_negative) {
    input.value = raisedFrom;
  }
  if (!wanted) raisedFrom = null;
  hadNegative = wanted;
  note.hidden = !wanted;
  note.textContent = Number(input.value) > 1
    ? 'Guidance is ' + input.value + ' for the negative prompt. Each image takes about twice as long.'
    : 'A negative prompt works only with guidance above 1. Each image then takes about twice as long.';
}

// The field keeps the user's own text, as the prompt field does. What the
// Look adds shows under it, so the field never looks empty while a
// negative prompt is sent.
function renderNegativeLook() {
  const line = document.getElementById('negative-look');
  const avoids = lookAvoids();
  line.hidden = !avoids;
  line.textContent = avoids ? 'Look adds: ' + avoids : '';
}

function refreshForm() {
  page.region().preview();
  renderNegativeLook();
  // The negative raises the scale, so it runs before the fields are mirrored
  // and the panel draws the value the run will use.
  followNegative();
  renderStrength();
  renderClearSeed();
  pushForm();
  renderRunButton();
  renderRewriteButton();
}

// Every field the drawn components read is mirrored into the store here, in
// one place, so a component redraws when a field of its own changes and
// nothing draws itself because something else happened to run first. The page
// still reads the fields straight from the DOM for its own work; the store is
// the components' copy. `negative` is the prompt the model will get, so a Look
// that adds an avoid part moves it.
function pushForm() {
  const store = page.store();
  if (!store) return;
  store.set('mode', editing() ? 'edit' : 'generate');
  store.set('size', page.el.sizeSelect.value);
  store.set('resolution', page.el.resolutionSelect.value);
  store.set('steps', document.getElementById('steps').value);
  store.set('guidance', document.getElementById('guidance').value);
  store.set('cfg', document.getElementById('cfg').value);
  store.set('seed', document.getElementById('seed').value);
  store.set('negative', negativeText());
}

// The references are an array the page mutates in place, so the store gets a
// copy: the store compares by identity, and a push that does not change it
// would leave the caption and the panel reading a stale list.
function pushReferences() {
  const store = page.store();
  if (!store) return;
  store.set('references', page.references().slice());
}

// The picks are an object the page mutates in place, so the store gets a copy
// for the same reason the references do. The Look trees redraw on it.
function pushLook() {
  const store = page.store();
  if (!store) return;
  store.set('looks', Object.assign({}, look));
}

// The gallery is an array the page mutates in place too, and the strip draws
// from the store, so it reaches the store as a copy for the same reason. The
// shown frame and the run state travel with it: a frame's waiting card and the
// frame in front of it are the same redraw.
function pushGallery() {
  const store = page.store();
  if (!store) return;
  store.set('gallery', page.gallery().slice());
  store.set('view', page.view());
  store.set('busy', page.busy());
}

function growPrompt() {
  const promptInput = page.el.promptInput;
  promptInput.style.height = 'auto';
  promptInput.style.height = Math.min(promptInput.scrollHeight + 2, 320) + 'px';
}

// Templates come from the backend, tuned on its model.
const PLACEHOLDER = /\[[^\]\n]+\]/;

// The list is rebuilt on each open, because it follows the current mode. The
// header and the hint are not items, so arrow keys and Tab skip them.
function openTemplates() {
  const menus = page.menus();
  const region = page.region();
  const templatesMenu = page.el.templatesMenu;
  templatesMenu.replaceChildren();
  const head = document.createElement('div');
  head.className = 'menu-head';
  head.textContent = editing() ? 'Start an edit from a template' : 'Start from a template';
  templatesMenu.append(head);
  currentMode().templates.forEach(function (template) {
    // A template that names the region token needs the draw tool, so it is not
    // offered where the tool is off. With more than one reference there is no
    // print to draw on, and the run would wait for a region that cannot exist.
    if (region.mentions(template.text) && !region.markable()) return;
    const option = menus.menuItem('', template.name, function () { useTemplate(template.text); });
    const note = document.createElement('span');
    note.className = 'item-note';
    note.textContent = template.hint;
    option.querySelector('.item-text').append(note);
    templatesMenu.append(option);
  });
  const foot = document.createElement('div');
  foot.className = 'menu-foot';
  foot.textContent = 'Press Tab to jump to the next [bracket].';
  templatesMenu.append(foot);
  menus.toggleMenu(templatesMenu);
}

function useTemplate(text) {
  page.el.promptInput.value = text;
  growPrompt();
  refreshForm();
  page.el.promptInput.focus();
  selectPlaceholder(0);
}

// Selects the next [placeholder] at or after a position, so typing replaces
// it. Returns false when none is left, and Tab then moves focus as usual.
function selectPlaceholder(from) {
  const found = PLACEHOLDER.exec(page.el.promptInput.value.slice(from));
  if (!found) return false;
  page.el.promptInput.setSelectionRange(from + found.index, from + found.index + found[0].length);
  return true;
}

// ---- Look -------------------------------------------------------------------
// Each choice adds one sentence after the prompt, at run time only, so the
// prompt field keeps the user's own text and a pick stays one click to undo.
// The sentence shows under the field, and the caption shows it muted. The
// rows and their wording come from the backend, tuned on its model.
//
// The rows, the summary's read-back and the chips under the prompt are
// components/look-rows.js. The picks stay here, because the run posts them
// inside the prompt; the page mirrors them into the store, which is what
// redraws those trees. The door below hands over the rows and the pick.
let look = {};            // row name to the labels picked in it

function lookRows() {
  return currentMode().looks;
}

function lookText() {
  return lookRows().map(function (row) {
    const picked = row.options.find(function (option) { return (look[row.name] || []).includes(option[0]); });
    return picked ? picked[1] : '';
  }).filter(Boolean).join(' ');
}

function lookAvoids() {
  if (!paramSpec('negative')) return '';
  return lookRows().map(function (row) {
    const picked = (row.avoids || []).find(function (avoid) { return (look[row.name] || []).includes(avoid[0]); });
    return picked ? picked[1] : '';
  }).filter(Boolean).join(', ');
}

function lookLabels() {
  return lookRows().flatMap(function (row) { return look[row.name] || []; });
}

// A pick replaces the row's pick, so a second click on the chip in force
// takes it back off. The trees read it back through the store.
function pickLook(row, label) {
  const had = (look[row.name] || []).includes(label);
  look[row.name] = had ? [] : [label];
  pushLook();
  refreshForm();
}

// A copy of the picks if this mode offers every one of them, else null.
// Rows differ by mode, so a pick is matched by its row and label.
function picksHere(picks) {
  const fits = Object.keys(picks).filter(function (name) { return picks[name].length; })
    .every(function (name) {
      const row = lookRows().find(function (candidate) { return candidate.name === name; });
      return row && picks[name].every(function (label) {
        return row.options.some(function (option) { return option[0] === label; });
      });
    });
  return fits ? JSON.parse(JSON.stringify(picks)) : null;
}

// The prompt as the model gets it: the user's text, closed as a sentence,
// then the look.
function withLook(prompt) {
  const added = lookText();
  if (!added) return prompt;
  return (/[.!?。！？]$/.test(prompt) ? prompt : prompt + '.') + ' ' + added;
}

function applyMode() {
  const form = page.el.form;
  form.classList.toggle('mode-edit', editing());
  form.classList.toggle('mode-generate', !editing());
  page.el.promptInput.placeholder = currentMode().prompt_hint;
  page.el.templatesToggle.hidden = !currentMode().templates.length;
  document.getElementById('look').hidden = !currentMode().looks.length;
  applyParams();
  // The verb on the run button follows the mode. The store carries the mode to
  // the button's labels; `refreshForm`, a few lines below in every switch,
  // mirrors it.
  hadNegative = false;
  raisedFrom = null;
}

// A mode the backend lacks stays in view, disabled, so the page keeps its shape.
function setupModes() {
  const form = page.el.form;
  form.querySelectorAll('input[name=mode]').forEach(function (radio) {
    const spec = page.modes[radio.value];
    const label = form.querySelector('label[for=' + radio.id + ']');
    radio.disabled = !spec;
    if (spec) label.lastChild.textContent = spec.label;
    else label.title = page.studio.backend.name + ' has no ' + label.textContent.trim().toLowerCase() + ' mode';
  });
  const first = form.querySelector('input[name=mode]:not(:disabled)');
  if (form.querySelector('input[name=mode]:checked').disabled) first.checked = true;
}

// ---- Rewrite -----------------------------------------------------------------
// The rewriter is a second model in the backend and it costs about 30s, so it
// is a button rather than something a run does on its own: the rewritten text
// lands in the box, where it can be read and edited before any image time is
// spent. It is offered only where the backend declares a rewriter for the mode
// on screen, and it sends the prompt WITH the Look sentences, because the Look
// is part of what the user asked for and the rewriter's job is to write all of
// it out at length.
//
// A toggle that rewrote each run was tried first. It cannot be built this way:
// htmx handles the submit from a listener of its own, and a listener added
// later never gets to hold the request.
//
// The button is the job's only control, so it carries the job's state. The
// server splits a rewrite in two: `preparing` is the weight load, and `writing`
// starts at the first segment of the answer. A warm load is instant and a cold
// one is about a minute. Only `writing` has something a press can stop, so only
// `writing` offers Cancel.
const rewriteStages = {
  preparing: { title: 'The rewriter is getting its weights ready', status: 'The rewriter is getting ready' },
  writing: { title: 'Stop the rewrite and keep the prompt you typed', status: 'Rewriting the prompt, about 30s' },
  stopping: { title: 'Stopping the rewrite', status: 'Stopping the rewrite' },
};
let rewriteStage = 'idle';
let rewritePoll = null;

// The text you typed before a rewrite replaced the box. Held apart so the card
// keeps your own words, which the rewritten paragraph otherwise overwrites.
let rewrittenFrom = null;

function rewriteOffered() {
  return (page.studio.rewrite_modes || []).indexOf(currentMode().id) >= 0;
}

// Which verb shows is the DOM's and never the cascade's. The run button's labels
// follow the same rule: `hidden` picks the label. A stylesheet that never loads
// then leaves one verb in the button's name and not three run together.
function showRewriteVerb(button, stage) {
  button.querySelector('.rewrite-idle').hidden = stage !== 'idle' && stage !== 'preparing';
  button.querySelector('.rewrite-cancel').hidden = stage !== 'writing';
  button.querySelector('.rewrite-stopping').hidden = stage !== 'stopping';
}

function renderRewriteButton() {
  const button = document.getElementById('rewrite-toggle');
  if (!button) return;
  button.hidden = !rewriteOffered();
  const empty = !page.el.promptInput.value.trim();
  showRewriteVerb(button, rewriteStage);
  button.disabled = rewriteStage === 'preparing' || rewriteStage === 'stopping'
    || (rewriteStage === 'idle' && (page.busy() || empty));
  const stage = rewriteStages[rewriteStage];
  button.title = stage ? stage.title : (empty
    ? 'Write a prompt to rewrite first. A marked run takes its instruction in the region rows.'
    : 'Rewrite the prompt into a longer instruction before generating');
  // The readout belongs to a run while one is going, so a rewrite only borrows
  // it when nothing else is. Without this a press looks like nothing happened
  // for half a minute, and the button stays live for a second press.
  if (page.busy()) return;
  const status = document.getElementById('status');
  status.hidden = rewriteStage === 'idle';
  if (stage) page.el.statusText.textContent = stage.status;
}

// What the rewriter reports is the page's only view of the job while the answer
// is still coming. The poll is a plain fetch and not htmx, so it stays out of
// the run's own request handling.
function pollRewriteState() {
  fetch('/rewrite/state').then(function (answer) { return answer.json(); }).then(function (state) {
    // A reply that arrives after the request settled or after a cancel press
    // describes a job this page is no longer holding.
    if (rewriteStage === 'idle' || rewriteStage === 'stopping') return;
    // The state only moves forward, from preparing to writing. A reply that
    // still says preparing must not take Cancel away from a job that is already
    // writing, and a reply that says idle before the request is even registered
    // must not move the button at all.
    if (state.stage === 'writing') {
      rewriteStage = 'writing';
      renderRewriteButton();
    }
    rewritePoll = setTimeout(pollRewriteState, 400);
  }).catch(function () {
    // The rewriter's own answer decides when the panel is released, so a state
    // that cannot be read needs no retry: the job settles on its own and the
    // button takes the release with it.
  });
}

function stopRewritePoll() {
  if (rewritePoll === null) return;
  clearTimeout(rewritePoll);
  rewritePoll = null;
}

// The press that starts a job. The panel is held for the whole of it, and the
// poll runs until the request settles, whichever way it settles.
async function startRewrite() {
  rewriteStage = 'preparing';
  holdPanel('Locked while the prompt is being rewritten.', true);
  renderRewriteButton();
  pollRewriteState();
  try {
    await rewritePrompt();
  } catch (error) {
    page.notify('error', 'The rewrite failed: ' + error.message);
  }
  stopRewritePoll();
  rewriteStage = 'idle';
  holdPanel('Locked while the prompt is being rewritten.', false);
  renderRewriteButton();
}

// A cancel press. The panel is released by the rewrite's own answer and not by
// this request, because the rewriter can be mid-segment when the cancel lands.
function cancelRewrite() {
  rewriteStage = 'stopping';
  stopRewritePoll();
  renderRewriteButton();
  fetch('/rewrite/cancel', { method: 'POST' }).catch(function () {
    // The rewrite's own answer releases the panel, so a cancel that never lands
    // needs no report: the button leaves Stopping… when the job stops.
  });
}

async function rewritePrompt() {
  const promptInput = page.el.promptInput;
  const typed = promptInput.value.trim();
  const body = new URLSearchParams();
  body.set('mode', currentMode().id);
  body.set('prompt', withLook(promptInput.value));
  // The pictures the run carries, and not the mask: the mask is a technical
  // picture, and the rewriter is asked about the scene.
  body.set('references', JSON.stringify(page.references().map(function (reference) { return reference.b64; })));
  const answer = await fetch('/rewrite', { method: 'POST', body: body });
  const text = await answer.text();
  let result;
  try {
    result = JSON.parse(text);
  } catch (error) {
    throw new Error(text || answer.statusText);
  }
  if (result.error) throw new Error(result.error);
  // A cancelled rewrite answers with no prompt, so nothing here is applied: the
  // box keeps the words the user typed and `rewrittenFrom` stays as it was, so
  // the card still shows their own sentence.
  if (result.cancelled) return result;
  rewrittenFrom = typed;
  promptInput.value = result.prompt;
  growPrompt();
  // A shape the rewriter suggested is applied, so the run renders what it
  // described. It arrives as one of this mode's own sizes, or as nothing.
  if (result.size) setSelect(page.el.sizeSelect, result.size);
  refreshForm();
  return result;
}

// ---- The panel the two jobs hold ---------------------------------------------
// A run and a rewrite both hold the panel still: the inputs carry the values the
// job is using, so changing one mid-flight would leave the card disagreeing with
// what was actually sent. Each locked control says which job holds it. The locks
// nest, because a rewrite can finish while a run is starting.
//
// The Run button is never locked: during a run it is Cancel, and locking it would
// trap the user with no way out.
const holds = new Set();
let held = [];

function holdPanel(reason, on) {
  if (on) holds.add(reason);
  else holds.delete(reason);
  if (holds.size && !held.length) applyHold();
  else if (!holds.size && held.length) releaseHold();
}

// `disabled` is the obvious way to hold a field and it is the wrong one: the
// browser leaves a disabled field out of the form it submits, so a panel locked
// that way once arrived at the server with no prompt, no mode and no size.
// `readonly` keeps the value in the request, and a pointer-events block covers
// the controls readonly cannot reach, which is the selects and the buttons.
function applyHold() {
  const reason = Array.from(holds).join(' ');
  held = [];
  page.el.form.querySelectorAll('input, textarea, select, button').forEach(function (control) {
    // The Run button is Cancel while a run is going, and the rewrite button is
    // Cancel while a rewrite is writing, so holding either would trap the user
    // with no way out.
    if (control.id === 'go' || control.id === 'rewrite-toggle') return;
    const text = control.tagName === 'TEXTAREA' || (control.tagName === 'INPUT' && control.type === 'text');
    if (text) {
      if (control.readOnly) return;
      control.readOnly = true;
      held.push([control, 'readOnly']);
    } else {
      control.style.pointerEvents = 'none';
      held.push([control, 'pointer']);
    }
    control.dataset.heldTitle = control.getAttribute('title') || '';
    control.title = reason;
  });
}

function releaseHold() {
  held.forEach(function (entry) {
    const control = entry[0];
    if (entry[1] === 'readOnly') control.readOnly = false;
    else control.style.pointerEvents = '';
    if (control.dataset.heldTitle) control.title = control.dataset.heldTitle;
    else control.removeAttribute('title');
    delete control.dataset.heldTitle;
  });
  held = [];
  // The page's own rules decide which controls stay disabled, so they are asked
  // again rather than trusting the state this put back.
  refreshForm();
}

const handle = {
  editing: editing,
  currentMode: currentMode,
  paramSpec: paramSpec,
  maxReferences: maxReferences,
  scaleParam: scaleParam,
  spell: spell,
  lastReference: lastReference,
  addReference: addReference,
  probeSize: probeSize,
  renderReferences: renderReferences,
  look: function () { return look; },
  setLook: function (picks) { look = picks; pushLook(); },
  lookRows: lookRows,
  lookText: lookText,
  lookAvoids: lookAvoids,
  lookLabels: lookLabels,
  pickLook: pickLook,
  picksHere: picksHere,
  withLook: withLook,
  typedNegative: typedNegative,
  negativeText: negativeText,
  rewrittenFrom: function () { return rewrittenFrom; },
  currentOption: currentOption,
  setSelect: setSelect,
  followsReference: followsReference,
  editResolution: editResolution,
  targetRatio: targetRatio,
  targetPixels: targetPixels,
  costKey: costKey,
  stepSeconds: stepSeconds,
  estimate: estimate,
  refreshForm: refreshForm,
  pushForm: pushForm,
  pushReferences: pushReferences,
  pushLook: pushLook,
  pushGallery: pushGallery,
  renderRunButton: renderRunButton,
  renderRewriteButton: renderRewriteButton,
  applyParams: applyParams,
  clampCount: clampCount,
  growPrompt: growPrompt,
  pushLook: pushLook,
  openTemplates: openTemplates,
  // The doors of the components the form is drawn from. Each one hands over what
  // the component cannot read for itself, and the form is the only one that has
  // all of it.
  useStore: function () {
    pushForm();
    pushReferences();
    pushLook();
    pushGallery();
  },
  useSizeChips: function (detail) {
    detail.configure({
      sizes: sizeOptions,
      ratios: ratios,
      resolutions: Array.from(page.el.resolutionSelect.options).map(function (option) { return option.value; }),
      setSelect: setSelect,
      sizeSelect: page.el.sizeSelect,
      resolutionSelect: page.el.resolutionSelect,
      currentOption: currentOption,
      editResolution: editResolution,
      followsReference: followsReference,
      lastReference: lastReference,
    });
  },
  useAdvanced: function (detail) { detail.configure({ scaleParam: scaleParam }); },
  useLookRows: function (detail) {
    detail.configure({
      rows: lookRows,
      picks: function () { return look; },
      text: lookText,
      avoids: lookAvoids,
      labels: lookLabels,
      pick: pickLook,
    });
  },
  useReferences: function (detail) {
    detail.configure({
      limit: maxReferences,
      remove: function (index) {
        page.references().splice(index, 1);
        renderReferences();
      },
    });
  },
};

function wire() {
  const el = page.el;
  fillSelect(el.sizeSelect, 'size');
  fillSelect(el.resolutionSelect, 'resolution');
  readSizes();

  el.referenceInput.addEventListener('change', function () {
    addFiles(el.referenceInput.files);
    el.referenceInput.value = '';
  });
  el.refsZone.addEventListener('click', function () { el.referenceInput.click(); });
  el.refsZone.addEventListener('keydown', function (event) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    el.referenceInput.click();
  });
  el.refsZone.addEventListener('dragover', function (event) {
    event.preventDefault();
    el.refsZone.classList.add('over');
  });
  el.refsZone.addEventListener('dragleave', function () { el.refsZone.classList.remove('over'); });
  el.refsZone.addEventListener('drop', function (event) {
    event.preventDefault();
    el.refsZone.classList.remove('over');
    addFiles(event.dataTransfer.files);
  });
  document.addEventListener('paste', function (event) {
    const files = event.clipboardData ? event.clipboardData.files : [];
    if (!files.length) return;  // a text paste goes to the field as usual
    event.preventDefault();
    addFiles(files);
  });
  document.getElementById('clear-reference').addEventListener('click', function () {
    page.setReferences([]);
    renderReferences();
  });

  el.countToggle.addEventListener('click', openCount);
  document.getElementById('clear-seed').addEventListener('click', function () {
    document.getElementById('seed').value = '';
    refreshForm();
  });

  el.templatesToggle.addEventListener('click', function () {
    if (el.templatesMenu.hidden) openTemplates(); else page.menus().closeMenus();
  });
  el.promptInput.addEventListener('keydown', function (event) {
    if (event.key !== 'Tab' || event.shiftKey) return;
    if (selectPlaceholder(el.promptInput.selectionEnd)) event.preventDefault();
  });
  el.form.addEventListener('input', refreshForm);
  el.form.addEventListener('change', refreshForm);
  el.promptInput.addEventListener('input', growPrompt);

  el.form.querySelectorAll('input[name=mode]').forEach(function (radio) {
    radio.addEventListener('change', function () {
      applyMode();
      page.menus().closeMenus();
      page.setReferences([]);
      el.promptInput.value = '';
      look = {};
      pushLook();
      growPrompt();
      renderReferences();
      // The run in flight is not this form's, so its frame stays as it is.
      if (page.view() !== 'progress') page.renderStage();
    });
  });

  document.getElementById('rewrite-toggle').addEventListener('click', function () {
    // The press is Cancel once the rewriter writes, and dead while it loads its
    // weights, because a load has nothing to stop.
    if (rewriteStage === 'writing') { cancelRewrite(); return; }
    if (rewriteStage !== 'idle') return;
    if (page.busy() || !el.promptInput.value.trim()) return;
    startRewrite();
  });

  // The prompt box carries an instruction the button depends on, so its state is
  // refreshed as it is typed. refreshForm already runs on input for other reasons.
  el.promptInput.addEventListener('input', function () {
    rewrittenFrom = null;   // typing again is your own words, not the rewrite's
    renderRewriteButton();
  });

  // Watching the class the page already sets for a run keeps this out of the run's
  // own start and stop paths, which are easy to get wrong.
  new MutationObserver(function () {
    holdPanel('Locked while the image is being made.', page.busy());
  }).observe(document.body, { attributes: true, attributeFilter: ['class'] });
}

document.dispatchEvent(new CustomEvent('form-ready', {
  detail: {
    configure: function (helpers) {
      Object.assign(page, helpers);
      wire();
      setupModes();
      // The form draws itself here. This module is evaluated before every other
      // and the draw needs no component's handle, so it is the slot in the load
      // the page's own startup took. The stage is the one thing that is not here
      // yet, and it asks for its own draw when it arrives.
      applyMode();
      pushLook();
      renderReferences();
      page.renderStrip();
      page.renderStage();
      renderRewriteButton();
      return handle;
    },
  },
}));
