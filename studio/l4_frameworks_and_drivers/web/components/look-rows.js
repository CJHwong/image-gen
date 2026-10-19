// The Look: the rows that open onto their chips, the pick the summary reads
// back, and the chips under the prompt that take a pick off again.
//
// Three trees drawn from state, so Lit, and each keeps the element itself as
// the render root: the ids `#look-rows`, `#look-values` and `#look-adds` stay
// on the same three nodes the checks reach.
//
// Two boards share this component: the image form and the video form. A board
// is the page's handle for one form, and every element names its board with
// `data-form`. Each board keeps its own rows, picks and open row, so the two
// forms never see each other's picks.
//
// The picks stay the page's, because the run posts them inside the prompt. The
// module reads them through `picks()` and the page mirrors them into the store,
// which is what redraws these trees. The rows come from the backend, through
// `rows()`.
//
// Nothing stands between the two spans of a row's toggle. The space in a row's
// accessible name is the cascade's: `display: flex` on the toggle makes the
// pick a block of its own, and a text node here would put a space in with the
// stylesheet refused as well, where the name has always read "Lightnone".

import { LitElement, html } from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import { subscribe } from '../lib/state.js';

// One handle per form, registered by the page that owns that form's state.
const boards = new Map();

// The one row showing its chips, per form. It is the tree's own shape, so it is
// not a store field: no consumer outside this module reads it.
const openRows = new Map();

// A pick puts a chip under the prompt and takes the row's own chips away, so
// the content above the row changes height and the row slides out from under
// the pointer. The correction needs the row's top on both sides of the redraw,
// and Lit redraws after the click returns, so the first is read in the click
// and the second once every tree here has drawn.
const settles = new Map();

const FORMS = ['image', 'video'];

function formOf(element) {
  return element.dataset.form === 'video' ? 'video' : 'image';
}

function boardOf(element) {
  return boards.get(formOf(element));
}

// Every tree of one board. The tail sits above the rows, so a wait that covers
// all three covers the height the rows are read against.
function lookElements(form) {
  return ['look-rows', 'look-values', 'look-adds']
    .flatMap((name) => Array.from(document.querySelectorAll(name + '[data-form="' + form + '"]')));
}

function toggleOf(form, name) {
  const board = boards.get(form);
  const scope = board && board.scope();
  if (!scope) return null;
  return scope.querySelector('.look-row-toggle[data-row="' + CSS.escape(name) + '"]');
}

// The sidebar scrolls by as much as the row moved, so the row stays under the
// pointer. A sidebar too short to scroll that far gets the missing room as
// empty space at its foot.
function holdRowUnderPointer(form, pending) {
  const controls = document.querySelector('.controls');
  const toggle = toggleOf(form, pending.row);
  if (!controls || !toggle) return;
  const target = controls.scrollTop + toggle.getBoundingClientRect().top - pending.before;
  const box = controls.getBoundingClientRect();
  const contentEnd = Math.max.apply(null, Array.from(controls.children).map(function (child) {
    return child.getBoundingClientRect().bottom;
  })) - box.top + controls.scrollTop + 28;
  controls.style.setProperty('--slack', Math.max(0, target + controls.clientHeight - contentEnd) + 'px');
  controls.scrollTop = target;
}

class Drawn extends LitElement {
  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    this.bindBoard();
  }

  // The board is registered when the page hands it over, which happens after
  // the element is upgraded. The configure call binds the elements it finds,
  // and this covers one that upgraded later.
  bindBoard() {
    if (this.bound) return;
    const board = boardOf(this);
    if (!board) return;
    this.bound = true;
    subscribe(board.fields || ['looks'], () => this.requestUpdate());
  }
}

class LookRows extends Drawn {
  // The rows are the mode's, so a switch replaces them and the row that was
  // open closes with the set it came from.
  willUpdate() {
    const board = boardOf(this);
    if (!board) return;
    const mode = board.mode();
    if (this.mode !== mode) {
      this.mode = mode;
      openRows.set(formOf(this), null);
    }
  }

  updated() {
    const form = formOf(this);
    const pending = settles.get(form);
    if (!pending) return;
    settles.delete(form);
    Promise.all(lookElements(form).map((element) => element.updateComplete)).then(function () {
      holdRowUnderPointer(form, pending);
    });
  }

  toggleRow(name) {
    const form = formOf(this);
    openRows.set(form, openRows.get(form) === name ? null : name);
    this.requestUpdate();
  }

  // A pick from the rows puts the text under the prompt above them.
  pickInPlace(row, label) {
    const form = formOf(this);
    const toggle = toggleOf(form, row.name);
    settles.set(form, { row: row.name, before: toggle ? toggle.getBoundingClientRect().top : 0 });
    openRows.set(form, null);
    boardOf(this).pick(row, label);
  }

  render() {
    const page = boardOf(this);
    if (!page) return html``;
    const form = formOf(this);
    const open = openRows.get(form);
    return html`${page.rows().map((row) => {
      const picks = page.picks()[row.name] || [];
      const picked = picks[0];
      const shown = open === row.name;
      return html`<div class="look-row"><button type="button" class="look-row-toggle" data-row=${row.name} aria-expanded=${String(shown)} @click=${() => this.toggleRow(row.name)}><span class="label">${row.name}</span><span class="look-pick${picked ? ' picked' : ''}">${picked || 'none'}</span></button><div class="look-chips" ?hidden=${!shown}>${row.options.map(([label]) => html`<button type="button" class="chip" aria-pressed=${String(picks.includes(label))} @click=${() => this.pickInPlace(row, label)}>${label}</button>`)}</div></div>`;
    })}`;
  }
}

// The summary's read-back: the picks by name, in the rows' own order, or `none`.
class LookValues extends Drawn {
  render() {
    const page = boardOf(this);
    if (!page) return html``;
    const labels = page.labels();
    return html`${labels.length ? labels.join(', ') : 'none'}`;
  }
}

// Under the prompt: one chip per pick, which takes it back off, then the
// sentence the run adds and the avoid part the negative prompt will carry.
// An unpick closes an open row as a pick does, and needs no correction: it is
// not a click on a row.
function unpick(form, row, label) {
  openRows.set(form, null);
  boards.get(form).pick(row, label);
}

class LookAdds extends Drawn {
  willUpdate() {
    const page = boardOf(this);
    this.hidden = !page || !page.text();
  }

  render() {
    const page = boardOf(this);
    if (!page) return html``;
    const added = page.text();
    if (!added) return html``;
    const picks = page.picks();
    const avoids = page.avoids();
    const form = formOf(this);
    return html`${page.rows().flatMap((row) => (picks[row.name] || []).map((label) => html`<button type="button" class="chip" aria-label=${'Remove ' + label} @click=${() => unpick(form, row, label)}>${label} ×</button>`))}<span class="caption">The run adds this after your words:</span><q>${added}</q>${avoids ? html`<p class="look-avoids">${'Negative prompt adds: ' + avoids + '. Each image takes about twice as long.'}</p>` : ''}`;
  }
}

customElements.define('look-rows', LookRows);
customElements.define('look-values', LookValues);
customElements.define('look-adds', LookAdds);

// The door. The page registered its listener while the markup was parsed, and
// this fires while the module is evaluated: after the markup, before any
// interaction. The handle is in place before the first render, because Lit
// renders on a microtask and this dispatch is synchronous.
document.dispatchEvent(new CustomEvent('look-rows-ready', {
  detail: {
    configure: function (helpers) {
      const form = FORMS.includes(helpers.form) ? helpers.form : 'image';
      boards.set(form, helpers);
      lookElements(form).forEach(function (element) {
        if (element.bindBoard) element.bindBoard();
        element.requestUpdate();
      });
    },
  },
}));
