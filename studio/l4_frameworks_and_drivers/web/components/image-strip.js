// The gallery: the strip's frames, which image is shown, and the before and
// after wipe on an edit's print.
//
// The strip draws a tree from state, so it is a Lit element and its render root
// is the element itself: `#strip` keeps its id, its class and the shape of its
// children, and each frame stays a `button` named `"<mode>, seed <n>"` that a
// role query reaches. The frames are the only thing this draws: the head above
// them, `#strip-note`, `#download-gallery` and `#clear-gallery`, stay in the
// page's markup, because the page holds them and hangs their listeners there.
//
// A frame is never rebuilt while its image lives. `repeat` keys each frame by
// its image id, so an image that arrives at the front moves the others along
// instead of rebuilding them: a rebuilt frame reloads its image and restarts
// its entrance.
//
// The wipe is behaviour and not a tree. It is an input, an animation that
// writes `--split` on the print's own box once per frame, and two tags. It is
// drawn into the `.pic` the stage owns, so the page asks for it and this draws
// it.
//
// The ways out of the gallery are behaviour too. The array itself stays the
// page's to hold, because a run's answer and a kept image both land in it and
// both are the page's to put there; this asks the page for the array the way
// the region asks for the reference list, and never keeps a second copy that
// could disagree with it.

import { LitElement, html } from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import { repeat } from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/directives/repeat.js/+esm';
import { get, subscribe } from '../lib/state.js';

// The page's helpers, on `image-strip-ready`.
let page = null;

// The fields a frame is drawn from. A run's answer, a kept image and another
// tab's message all reach this module through the page's array, which the page
// mirrors into the store; `busy` is what puts the waiting frame in front.
const FIELDS = ['gallery', 'view', 'busy'];

// The page draws its own controls from the same sprite, and the two must agree
// on the three lines, so this draws a glyph exactly as `popup-menu.js` does.
function glyph(name) {
  return html`<svg class="icon" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
}

// The pencil loop, one hand-drawn stroke that overlaps where it closes. It is
// drawn once, on the redraw that picks a frame, and not on every redraw.
function pencilLoop(draw) {
  return html`<svg class="mark${draw ? ' draw' : ''}" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><path pathLength="1" d="M58 5 C80 5 97 16 98 44 C99 74 84 95 52 96 C20 97 3 80 2 52 C1 24 18 7 44 4 C52 3 62 4 70 7"></path></svg>`;
}

class ImageStrip extends LitElement {
  createRenderRoot() { return this; }

  // The frames that have arrived, so a frame's entrance plays once and its
  // class stays, as it did while the page built a frame by hand and kept the
  // node it built.
  arrivedIds = new Set();
  // The frame the loop was last drawn on, so the loop draws once. It is this
  // module's own: no consumer outside it reads it, so it is not a store field.
  markedId = undefined;
  // Whether this redraw is the one that picks the frame, for the loop.
  drawLoop = false;
  // A step the arrow keys asked for, kept until this element's own trees draw.
  pendingStep = null;

  connectedCallback() {
    super.connectedCallback();
    subscribe(FIELDS, () => this.requestUpdate());
  }

  // The page hands the one-shot over here, before the stage clears it: the
  // arrival is read while the strip still holds it, and the class it adds stays
  // on the frame.
  arrived(id) {
    if (id !== null && id !== undefined) this.arrivedIds.add(id);
  }

  // Which frame the loop is drawn on, decided before the tree draws so the
  // class is part of the render and no imperative pass has to chase it.
  willUpdate() {
    const view = get('view');
    this.drawLoop = view !== 'progress' && this.markedId !== view;
    this.markedId = view;
  }

  // The arrow keys walk the strip. The correction needs the selected frame's
  // box after the redraw, and Lit redraws after the key returns, so the page
  // asks for the step and this reads the geometry once its own trees have
  // drawn. The page does not sequence a render it does not own.
  step(delta) {
    const order = (get('busy') ? ['progress'] : []).concat(this.entries().map((entry) => entry.id));
    const next = order[order.indexOf(page.view()) + delta];
    if (next === undefined) return;
    this.pendingStep = { focus: this.contains(document.activeElement) };
    page.show(next);
  }

  updated() {
    if (!page) return;
    // The waiting frame takes its width from the shape of the run in flight,
    // which is the page's. It is read here rather than mirrored, because a
    // mirror of the run's shape is a copy that can disagree with it.
    const waiting = this.querySelector('.frame.pending .still');
    if (waiting) {
      waiting.style.width = Math.round(64 * Math.min(2, Math.max(0.5, page.pending().ratio))) + 'px';
    }
    const step = this.pendingStep;
    this.pendingStep = null;
    if (!step) return;
    const selected = this.querySelector('.frame.selected');
    if (!selected) return;
    selected.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    if (step.focus) selected.focus();
  }

  entries() {
    return get('gallery') || [];
  }

  // One frame per image, oldest first, with the waiting frame in front while a
  // run goes. `key` is the frame's own identity for `repeat`.
  rows() {
    const view = get('view');
    const rows = this.entries().map((entry) => ({
      key: String(entry.id), entry: entry,
      selected: view === entry.id, arrive: this.arrivedIds.has(entry.id),
      draw: this.drawLoop && view === entry.id, number: page.frameNumber(entry.id),
    }));
    if (get('busy')) {
      rows.unshift({
        key: 'progress', pending: true, selected: view === 'progress',
        number: page.frameNumber(page.pending().number),
      });
    }
    return rows;
  }

  frame(row) {
    const entry = row.entry;
    return html`<button type="button" class="frame${row.arrive ? ' arrive' : ''}${row.selected ? ' selected' : ''}" title=${'Seed ' + entry.seed} aria-label=${entry.mode + ', seed ' + entry.seed} @click=${() => page.show(entry.id)}><span class="still"><img alt="" src=${entry.src}>${entry.mode === 'edit' ? html`<span class="corner">${glyph('brush')}</span>` : ''}</span><span class="no">${row.number}</span>${row.selected ? pencilLoop(row.draw) : ''}</button>`;
  }

  waiting(row) {
    return html`<button type="button" class="frame pending${row.selected ? ' selected' : ''}" aria-label="Show the image in progress" @click=${() => page.show('progress')}><span class="still waiting"><span class="exposure"></span></span><span class="no">${row.number}</span>${row.selected ? pencilLoop(false) : ''}</button>`;
  }

  render() {
    if (!page) return html``;
    return html`${repeat(this.rows(), (row) => row.key, (row) => (row.pending ? this.waiting(row) : this.frame(row)))}`;
  }
}

customElements.define('image-strip', ImageStrip);

// ---- The before and after wipe -------------------------------------------------
// One choice for every edit, kept across reloads like the theme. It is the
// wipe's own state: the stage bar draws the switch, so it asks for it here.
const COMPARE_KEY = 'studio-compare';
let comparing = readCompare();

function readCompare() {
  try {
    return localStorage.getItem(COMPARE_KEY) !== 'off';
  } catch (error) {
    console.warn('The compare setting was not read:', error);
    return true;
  }
}

// The stage bar's switch. It carries its own state, which is what a user reads,
// and the stage was drawn again after a press, so focus goes back to it.
function toggle() {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'compare';
  button.textContent = 'Compare';
  button.title = comparing ? 'Hide the before and after slider' : 'Show the before and after slider';
  button.setAttribute('aria-pressed', String(comparing));
  button.addEventListener('click', function () {
    comparing = !comparing;
    try {
      localStorage.setItem(COMPARE_KEY, comparing ? 'on' : 'off');
    } catch (error) {
      console.warn('The compare setting was not saved:', error);
    }
    page.renderStage();
    const again = document.querySelector('#stage-bar .compare');
    if (again) again.focus();
  });
  return button;
}

// The first time an edit shows, the divider sweeps in from the left edge, which
// shows it can be dragged. After that it opens at the middle. The wipe is drawn
// into the print's own box, which the stage owns, so the page asks for it.
function compare(pic, entry) {
  const before = document.createElement('img');
  before.className = 'before';
  before.src = entry.before;
  before.alt = 'The image before the edit';
  const range = document.createElement('input');
  range.type = 'range';
  range.className = 'compare-range';
  range.min = '0';
  range.max = '100';
  range.setAttribute('aria-label', 'Compare before and after');
  const divider = document.createElement('div');
  divider.className = 'divider';
  divider.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-grip"/></svg>';
  const left = document.createElement('span');
  left.className = 'compare-tag left';
  left.textContent = 'Before';
  const right = document.createElement('span');
  right.className = 'compare-tag right';
  right.textContent = 'After';
  function split() { pic.style.setProperty('--split', range.value + '%'); }
  range.addEventListener('input', split);
  pic.append(before, range, divider, left, right);
  range.value = '50';
  split();
  if (entry.swept || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  entry.swept = true;
  sweep(range, split);
}

// The wipe paints in the frame the browser is about to draw, so the property it
// writes is read back on the next paint and the sweep is smooth. It stops when
// the print goes or a person takes the control.
function sweep(range, split) {
  const delay = 650;      // once the print is in focus, while its grain still settles
  const length = 650;
  let start = null;
  range.value = '0';
  split();
  requestAnimationFrame(function frame(now) {
    if (!range.isConnected || range.dataset.touched) return;
    if (start === null) start = now + delay;
    const progress = Math.min(1, Math.max(0, (now - start) / length));
    range.value = String(Math.round(50 * (1 - Math.pow(1 - progress, 3))));
    split();
    if (progress < 1) requestAnimationFrame(frame);
  });
  range.addEventListener('pointerdown', function () { range.dataset.touched = '1'; }, { once: true });
  range.addEventListener('keydown', function () { range.dataset.touched = '1'; }, { once: true });
}

// ---- The ways out of the gallery ------------------------------------------------
function saveFile(url, name) {
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
}

// Every image on the strip, oldest first, then one file with their prompts,
// since an image file holds no prompt. Each name starts with the frame number:
// two images can share a seed, and the browser would rename the second one.
// The files leave one at a time, because a browser drops downloads that come
// too close together. A batch of edits shares one source, saved once.
function download() {
  const befores = new Map();
  const facts = [];
  const pause = function () { return new Promise(function (resolve) { setTimeout(resolve, 300); }); };
  const saving = page.gallery().slice().reverse().reduce(function (previous, entry) {
    return previous.then(function () {
      const file = page.frameNumber(entry.id) + '-' + page.fileName(entry);
      saveFile(entry.src, file);
      const fact = { file: file, before: null };
      page.keptFields().forEach(function (field) { fact[field] = entry[field]; });
      facts.push(fact);
      if (!entry.before) return pause();
      const known = befores.has(entry.before);
      if (!known) befores.set(entry.before, file.replace(/\.png$/, '-before.png'));
      fact.before = befores.get(entry.before);
      if (known) return pause();
      return pause().then(function () {
        saveFile(entry.before, fact.before);
        return pause();
      });
    });
  }, Promise.resolve());
  saving.then(function () {
    const url = URL.createObjectURL(new Blob([JSON.stringify(facts, null, 2)], { type: 'application/json' }));
    saveFile(url, 'studio-prompts.json');
    setTimeout(function () { URL.revokeObjectURL(url); }, 10000);
  }).catch(function (error) {
    page.notify('error', 'Download all stopped: ' + error.message);
  });
}

// The shown image gives way to its neighbour. Another tab's removal leaves this
// tab's view alone unless it shows that image.
function drop(id) {
  const gallery = page.gallery();
  const index = gallery.findIndex(function (entry) { return entry.id === id; });
  if (index < 0) return;
  page.release(gallery.splice(index, 1)[0]);
  if (page.view() === id) {
    const neighbour = gallery[Math.min(index, gallery.length - 1)];
    page.setView(neighbour ? neighbour.id : null);
  }
  page.redraw();
  page.renderStage();
}

function remove(id) {
  drop(id);
  page.forget(function (images) { images.delete(id); }, { kind: 'remove', id: id });
}

function dropAll() {
  const gallery = page.gallery();
  const cleared = gallery.slice();
  gallery.length = 0;
  cleared.forEach(page.release);
  page.setView(get('busy') ? 'progress' : null);
  page.redraw();
  page.renderStage();
}

function clear() {
  const gallery = page.gallery();
  const question = page.keeping()
    ? 'Remove all ' + gallery.length + ' images from this browser? Every open tab clears too.'
    : 'Remove all ' + gallery.length + ' images from this tab?';
  if (!confirm(question)) return;
  dropAll();
  page.forget(function (images) { images.clear(); }, { kind: 'clear' });
}

const handle = {
  compare: compare,
  comparing: function () { return comparing; },
  toggle: toggle,
  download: download,
  clear: clear,
  remove: remove,
  drop: drop,
  dropAll: dropAll,
  arrived: function (id) {
    const element = document.querySelector('image-strip');
    if (element) element.arrived(id);
  },
  step: function (delta) {
    const element = document.querySelector('image-strip');
    if (element) element.step(delta);
  },
};

// The door. The page registered its listener while the markup was parsed, and
// this fires while the module is evaluated: after the markup, before any
// interaction. The page hands over the array it holds and the rest of what it
// owns and this module cannot see, and takes the handle back. The element is
// redrawn here as well, because it was upgraded by `customElements.define`
// above and its first render must wait for the page's helpers.
document.dispatchEvent(new CustomEvent('image-strip-ready', {
  detail: {
    configure: function (helpers) {
      page = helpers;
      const element = document.querySelector('image-strip');
      if (element) element.requestUpdate();
      return handle;
    },
  },
}));
