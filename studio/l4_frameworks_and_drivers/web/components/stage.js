// The stage: the print, the bar under it, the two sheets and full screen.
//
// This is behaviour and not a tree. The stage is cleared and rebuilt in the task
// that asked for it, `fitStage` measures the plate and the print from their own
// boxes in that same task, and the caption's ResizeObserver marks a caption the
// moment a resize cuts it. A Lit render lands a microtask later, so a tree here
// would fit a plate that is not drawn yet and mark a caption that has not
// wrapped. The module owns its own redraw, and the page asks for it.
//
// The page's own script is still a classic script, so it cannot import this
// module. The listener is registered while the markup is parsed and this fires
// while the module is evaluated: after the markup, before any interaction, so
// the handle is in place before the first draw asks for a stage.

// What the stage draws with. The DOM helpers live here because the stage and the
// region module are the two that build buttons, and the region takes
// `iconButton` off the handle below rather than keeping a second copy.
export function icon(name) {
  return '<svg class="icon" aria-hidden="true"><use href="#i-' + name + '"/></svg>';
}

export function iconButton(name, label, handler, extra) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'icon-btn' + (extra ? ' ' + extra : '');
  button.title = label;
  button.setAttribute('aria-label', label);
  button.innerHTML = icon(name);
  button.addEventListener('click', handler);
  return button;
}

export function textButton(name, label, handler) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'btn quiet';
  button.innerHTML = icon(name) + label;
  button.addEventListener('click', handler);
  return button;
}

// A frame's number, as printed on the film's edge.
export function frameNumber(id) {
  return String(id).padStart(2, '0');
}

const page = {};

// The card takes the shape of the coming image, fitted inside the stage the
// way the image itself will be.
const REBATE_WIDTH = 20;   // the film's left and right rebate together
const REBATE_HEIGHT = 34;  // top and bottom, the bottom holding the edge print

function fitBox(box, ratio, share) {
  const width = Math.min((page.canvas.clientWidth - 48 - REBATE_WIDTH) * share,
    (page.canvas.clientHeight - 48 - REBATE_HEIGHT) * share * ratio);
  box.style.width = Math.round(width) + 'px';
  box.style.height = Math.round(width / ratio) + 'px';
}

export function fitStage() {
  const plate = page.canvas.querySelector('.card .plate');
  if (plate) fitBox(plate, page.runRatio(), 1);
  const pic = page.canvas.querySelector('.pic');
  if (pic) fitBox(pic, Number(pic.dataset.ratio), 1);
}

export function selected() {
  const gallery = page.gallery();
  const view = page.view();
  return gallery.find(function (entry) { return entry.id === view; });
}

// What the frame was made from: "Generated", "Edited from 01", "Generated from
// your image". A kept image from before the sources were recorded names only
// the mode.
function madeBadge(entry) {
  const badge = document.createElement('span');
  badge.className = 'made';
  badge.append(entry.mode === 'edit' ? 'Edited' : 'Generated');
  const sources = entry.sources || [];
  if (!sources.length) return badge;
  const frameIds = [...new Set(sources.filter(Boolean))];
  const uploads = sources.filter(function (source) { return !source; }).length;
  const parts = frameIds.map(function (id) {
    if (!page.gallery().some(function (other) { return other.id === id; })) return frameNumber(id);
    const link = document.createElement('button');
    link.type = 'button';
    link.textContent = frameNumber(id);
    link.setAttribute('aria-label', 'Show frame ' + frameNumber(id));
    link.addEventListener('click', function () { page.show(id); });
    return link;
  });
  if (uploads) parts.push(uploads === 1 ? 'your image' : uploads + ' of your images');
  badge.append(' from ');
  parts.forEach(function (part, index) {
    if (index) badge.append(index === parts.length - 1 ? ' and ' : ', ');
    badge.append(part);
  });
  return badge;
}

function renderTopPlate() {
  // The readout is for a run: it says what the engine is doing and how long it has
  // been doing it. "Ready" said nothing, so the line waits for a run and goes with it.
  const status = document.getElementById('status');
  status.hidden = !page.busy();
  if (!page.busy()) {
    page.statusText.textContent = '';
  } else if (!page.progressState()) {
    page.statusText.textContent = 'Starting';
  }
}

// An empty stage names the next step and offers it as a button.
function renderEmpty() {
  const empty = document.createElement('div');
  empty.className = 'empty';
  const title = document.createElement('strong');
  const line = document.createElement('p');
  const start = document.createElement('button');
  start.type = 'button';
  start.className = 'btn';
  const references = page.references();
  if (page.editing() && references.length) {
    title.textContent = 'Ready to edit';
    line.textContent = 'Say what to change, then press Edit.';
    empty.append(title, line);
    page.canvas.append(empty);
    return;
  }
  if (page.editing()) {
    title.textContent = 'Edit an image';
    line.textContent = 'Add the image, then say what to change.';
    start.innerHTML = icon('image-in') + 'Choose an image';
    start.addEventListener('click', function () { page.referenceInput.click(); });
  } else if (!page.currentMode().templates.length) {
    title.textContent = 'Nothing here yet';
    line.textContent = 'Write a prompt and press Generate.';
    empty.append(title, line);
    page.canvas.append(empty);
    return;
  } else {
    title.textContent = 'Nothing here yet';
    line.textContent = 'Write a prompt and press Generate, or start from a template.';
    start.innerHTML = icon('layout') + 'Browse templates';
    start.addEventListener('click', function (event) {
      event.stopPropagation();  // the click would reach the document and close the menu
      page.openTemplates();
    });
  }
  empty.append(title, line, start);
  page.canvas.append(empty);
}

function renderStageBar(entry) {
  const stageBar = page.stageBar;
  const region = page.region();
  const strip = page.strip();
  const menus = page.menus();
  stageBar.hidden = false;
  stageBar.innerHTML = '';
  const about = document.createElement('div');
  about.className = 'about';
  const facts = document.createElement('div');
  facts.className = 'facts num';
  facts.append(madeBadge(entry));
  if (entry.before) facts.append(strip.toggle());
  // Two groups: which image, then how it was made. A phone puts each on its own line.
  [[entry.position === '1 image' ? '' : 'Image ' + entry.position, 'Seed ' + entry.seed],
   [entry.width + ' × ' + entry.height, entry.steps + ' steps', 'Took ' + entry.elapsed + ' s']
  ].forEach(function (group, index) {
    if (index) {
      const lineBreak = document.createElement('span');
      lineBreak.className = 'break';
      facts.append(lineBreak);
    }
    group.forEach(function (text) {
      if (!text) return;
      const fact = document.createElement('span');
      fact.textContent = text;
      facts.append(fact);
    });
  });
  // The prompt leads, as the frame's caption; the facts sit quietly under it.
  // The Look shows as the muted end of the caption, so the facts leave it out.
  const prompt = document.createElement('p');
  prompt.className = 'prompt-line';
  if (entry.look) {
    const said = document.createElement('span');
    said.className = 'look-said';
    said.textContent = entry.look.adds;
    prompt.append(entry.look.sent.slice(0, -entry.look.adds.length), said);
  } else {
    prompt.textContent = entry.prompt;
  }
  prompt.addEventListener('click', function () { toggleSheet(prompt, entry); });
  prompt.addEventListener('keydown', function (event) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    toggleSheet(prompt, entry);
  });
  about.append(prompt, facts);

  // Every action is page state only; nothing is sent until the next run.
  const actions = document.createElement('div');
  actions.className = 'actions';
  // Edit this and Download are the two next steps people take; the reuse
  // actions are rarer, so they wait behind More to keep the row short.
  const more = document.createElement('div');
  more.className = 'menu-anchor';
  const moreToggle = iconButton('more', 'More actions', function () { menus.toggleMenu(moreMenu); });
  moreToggle.setAttribute('aria-controls', 'more-menu');
  moreToggle.setAttribute('aria-expanded', 'false');
  const moreMenu = document.createElement('div');
  moreMenu.className = 'menu up';
  moreMenu.id = 'more-menu';
  moreMenu.setAttribute('role', 'menu');
  moreMenu.hidden = true;
  moreMenu.append(
    menus.menuItem('image-in', 'Use as reference', function () {
      page.referFrom(entry);
    }),
    menus.menuItem('hash', 'Reuse seed ' + entry.seed, function () {
      document.getElementById('seed').value = entry.seed;
      document.getElementById('advanced').open = true;
      page.refreshForm();
    }),
    menus.menuItem('text', 'Reuse prompt', function () {
      // A Look this mode cannot show comes back as text, so the prompt still says what
      // the model got. Otherwise the user's own words come back, which a region run may
      // have none of: its instruction is the rows, and handing back the composed
      // sentence would put words in the box the user never wrote. An image kept before
      // this field existed has no `typed`, so its prompt stands in.
      const picks = entry.look ? page.picksHere(entry.look.picks) : {};
      page.promptInput.value = picks
        ? (entry.typed !== undefined ? entry.typed : entry.prompt)
        : entry.look.sent;
      page.setLook(picks || {});
      if (page.paramSpec('negative')) document.getElementById('negative').value = entry.negative;
      page.growPrompt();
      page.refreshForm();
      page.promptInput.focus();
    })
  );
  more.append(moreToggle, moreMenu);
  const download = document.createElement('a');
  download.className = 'icon-btn';
  download.href = entry.src;
  download.download = fileName(entry);
  download.title = 'Download';
  download.setAttribute('aria-label', 'Download');
  download.innerHTML = icon('download');
  const rule = document.createElement('span');
  rule.className = 'rule';
  actions.append(textButton('brush', 'Edit this', function () { page.editThis(entry); }), more,
    rule, download,
    iconButton('trash', 'Remove', function () { page.strip().remove(entry.id); }, 'danger'));
  if (document.fullscreenEnabled) {
    actions.append(document.fullscreenElement
      ? iconButton('shrink', 'Exit full screen (F)', toggleFullscreen)
      : iconButton('expand', 'Full screen (F)', toggleFullscreen));
  }
  if (page.region().onPrint()) page.region().tools(stageBar);
  stageBar.append(about, actions);
  captionWatch.disconnect();
  captionWatch.observe(prompt);
}

export function renderStage() {
  const region = page.region();
  renderTopPlate();
  // A mark belongs to the picture it was drawn on: another frame, another
  // reference, or a mode that does not take a region drops it. A run moves the
  // stage to its progress card and takes the mark with it, which is the one case
  // that is not the user's doing, so that one is dropped without a word.
  region.dropStale(page.busy() || page.view() === 'progress' ? '' : 'The mark went with its picture.');
  page.canvas.innerHTML = '';
  const stageBar = page.stageBar;
  stageBar.hidden = true;
  // Cleared, or the last frame's facts stay in this hidden bar. A check read them as the
  // run's own, which turned an engine failure into a report about the wrong mode.
  stageBar.innerHTML = '';
  stageBar.classList.remove('reserved');
  if (page.view() === 'progress' && page.busy()) {
    // The caption's room is kept through the run, so the frame does not
    // move when the plate turns into the print.
    stageBar.innerHTML = '';
    stageBar.hidden = false;
    stageBar.classList.add('reserved');
    // The card is components/progress-card.js. htmx keeps `#progress`, the
    // element the poll swaps, and that module draws this and never touches it.
    page.progressCard().mount(page.canvas, page.edgeName, frameNumber(page.nextId()));
    fitStage();
    page.renderProgress();
    return;
  }
  const entry = selected();
  if (!entry) return renderEmpty();
  const shot = document.createElement('div');
  shot.className = 'shot' + (entry.id === page.arrivedId() ? ' arrive' : '');
  const pic = document.createElement('div');
  pic.className = 'pic';
  pic.dataset.ratio = entry.width / entry.height;
  const image = document.createElement('img');
  image.src = entry.src;
  image.alt = entry.prompt;
  pic.append(image);
  if (entry.before && page.strip().comparing()) page.strip().compare(pic, entry);
  if (region.onPrint()) region.mount(pic);
  const edge = document.createElement('div');
  edge.className = 'edge';
  edge.innerHTML = '<span>' + page.edgeName + '</span><span>' + frameNumber(entry.id) + '</span>';
  shot.append(pic, edge);
  if (region.onPrint()) shot.classList.add('marking');
  // A brush on the print takes the drag that the divided view's divider would
  // take, since the divider covers the whole print. The divided view goes while
  // the brush is here, and it is off the print rather than shown dead.
  page.canvas.append(shot);
  page.clearArrived();
  // The bar takes its height from the stage, so the shot is fitted after it.
  renderStageBar(entry);
  fitStage();
  region.sync();
}

// A label is a toggle only while it is cut, or its sheet is open. The watch
// marks it again when a resize cuts it or gives it room.
const captionWatch = new ResizeObserver(function (entries) {
  entries.forEach(function (entry) { markCaption(entry.target); });
});

export function markCaption(prompt) {
  const open = Boolean(page.canvas.querySelector('.sheet'));
  if (open || prompt.scrollHeight > prompt.clientHeight + 1) {
    prompt.setAttribute('role', 'button');
    prompt.tabIndex = 0;
    prompt.setAttribute('aria-expanded', String(open));
  } else {
    prompt.removeAttribute('role');
    prompt.removeAttribute('tabindex');
    prompt.removeAttribute('aria-expanded');
  }
}

// The typed prompt, the Look's sentence and the negative, each named, as the
// model got them. Focus goes to Close, and back to the label after.
export function toggleSheet(prompt, entry) {
  if (!prompt.hasAttribute('role')) return;
  if (page.canvas.querySelector('.sheet')) return closeSheet();
  const sheet = document.createElement('div');
  sheet.className = 'sheet';
  sheet.id = 'prompt-sheet';
  sheet.setAttribute('role', 'region');
  sheet.setAttribute('aria-label', 'The whole prompt');
  const list = document.createElement('dl');
  [['Prompt', entry.prompt], ['Look', entry.look ? entry.look.adds : ''], ['Negative', entry.negative]]
    .forEach(function ([term, text]) {
      if (!text) return;
      const name = document.createElement('dt');
      const value = document.createElement('dd');
      name.textContent = term;
      value.textContent = text;
      list.append(name, value);
    });
  const close = iconButton('x', 'Close', closeSheet, 'close');
  sheet.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;
    event.stopPropagation();
    closeSheet();
  });
  sheet.append(list, close);
  page.canvas.append(sheet);
  prompt.setAttribute('aria-controls', sheet.id);
  markCaption(prompt);
  close.focus();
}

export function closeSheet() {
  const canvas = page.canvas;
  const sheet = canvas.querySelector('.sheet');
  if (!sheet) return;
  sheet.remove();
  const prompt = page.stageBar.querySelector('.prompt-line');
  if (!prompt) return;
  markCaption(prompt);
  prompt.focus();
}

// The studio had no manual, so this is it: short, and about what the page does rather
// than about what the model can do. It is the same sheet the prompt opens in, because
// that is the shape this page already has for reading something over the print.
const GUIDE = [
  ['Generate, or Edit', 'Generate writes a picture from a prompt. Edit changes one you already have, and needs an image from the strip: click a frame, then Edit this.'],
  ['Mark a region', "Fill the area you want changed. Do not circle it: the mark's own shape is the shape that comes back repainted."],
  ['What changes there', 'One row per marked colour says what changes in that area. Or pick the Mark a region template and leave the rows empty.'],
  ['The brush', 'Three widths, and a loupe follows the brush while you draw. The area you mark is the area that changes, so keep the mark close to what should change.'],
  ['The wait', 'An edit reads your prompt and images for about a minute before its first step. The line in the top bar counts that time.'],
  ['Run and Cancel', 'Run empties the form it sent. Cancel puts all of it back, the marked region included.'],
  ['The strip', 'Images stay in the strip. Download the ones you want before you clear it.'],
];

export function closeGuide() {
  const sheet = document.getElementById('guide-sheet');
  if (!sheet) return;
  sheet.remove();
  const toggle = document.getElementById('guide-toggle');
  toggle.setAttribute('aria-expanded', 'false');
  toggle.focus();
}

export function openGuide() {
  if (document.getElementById('guide-sheet')) return closeGuide();
  const sheet = document.createElement('div');
  sheet.className = 'sheet';
  sheet.id = 'guide-sheet';
  sheet.setAttribute('role', 'region');
  sheet.setAttribute('aria-label', 'How to use this studio');
  const list = document.createElement('dl');
  GUIDE.forEach(function (pair) {
    const term = document.createElement('dt');
    const text = document.createElement('dd');
    term.textContent = pair[0];
    text.textContent = pair[1];
    list.append(term, text);
  });
  const close = iconButton('x', 'Close', closeGuide, 'close');
  sheet.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;
    event.stopPropagation();
    closeGuide();
  });
  sheet.append(list, close);
  page.canvas.append(sheet);
  document.getElementById('guide-toggle').setAttribute('aria-expanded', 'true');
  close.focus();
}

// ---- Full screen -------------------------------------------------------------
// The stage and the sheet fill the screen. F toggles it, and Escape leaves by
// the browser's own rule. The arrow keys walk the strip, which is the page's.
export function toggleFullscreen() {
  const change = document.fullscreenElement ? document.exitFullscreen() : page.work.requestFullscreen();
  change.catch(function (error) { page.notify('error', 'Full screen failed: ' + error.message); });
}

function fileName(entry) {
  return page.backendId + '-' + entry.mode + '-' + entry.seed + '.png';
}

const handle = {
  iconButton: iconButton,
  frameNumber: frameNumber,
  fileName: fileName,
  renderStage: renderStage,
  fitStage: fitStage,
  markCaption: markCaption,
  toggleSheet: toggleSheet,
  closeSheet: closeSheet,
  openGuide: openGuide,
  closeGuide: closeGuide,
  toggleFullscreen: toggleFullscreen,
  selected: selected,
};

window.addEventListener('resize', fitStage);
document.addEventListener('fullscreenchange', renderStage);

document.dispatchEvent(new CustomEvent('stage-ready', {
  detail: {
    configure: function (helpers) {
      Object.assign(page, helpers);
      return handle;
    },
  },
}));
