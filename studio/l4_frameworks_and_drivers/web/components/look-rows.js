// The Look: the rows that open onto their chips, the pick the summary reads
// back, and the chips under the prompt that take a pick off again.
//
// Three trees drawn from state, so Lit, and each keeps the element itself as
// the render root: the ids `#look-rows`, `#look-values` and `#look-adds` stay
// on the same three nodes the checks reach.
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
import { get, subscribe } from '../lib/state.js';

// The page's helpers, on `look-rows-ready`.
let page = null;

// The one row showing its chips. It is the tree's own shape, so it is not a
// store field: no consumer outside this module reads it.
let openRow = null;

// A pick puts a chip under the prompt and takes the row's own chips away, so
// the content above the row changes height and the row slides out from under
// the pointer. The correction needs the row's top on both sides of the redraw,
// and Lit redraws after the click returns, so the first is read in the click
// and the second once every tree here has drawn.
let settle = null;

const FIELDS = ['looks', 'mode'];

class Drawn extends LitElement {
  static fields = FIELDS;

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    subscribe(this.constructor.fields, () => this.requestUpdate());
  }
}

// Every tree in this module. The tail sits above the rows, so a wait that
// covers all three covers the height the rows are read against.
function lookElements() {
  return ['look-rows', 'look-values', 'look-adds']
    .flatMap((name) => Array.from(document.querySelectorAll(name)));
}

function toggleOf(name) {
  return document.querySelector('.look-row-toggle[data-row="' + CSS.escape(name) + '"]');
}

// The sidebar scrolls by as much as the row moved, so the row stays under the
// pointer. A sidebar too short to scroll that far gets the missing room as
// empty space at its foot.
function holdRowUnderPointer(pending) {
  const controls = document.querySelector('.controls');
  const toggle = toggleOf(pending.row);
  if (!controls || !toggle) return;
  const target = controls.scrollTop + toggle.getBoundingClientRect().top - pending.before;
  const box = controls.getBoundingClientRect();
  const contentEnd = Math.max.apply(null, Array.from(controls.children).map(function (child) {
    return child.getBoundingClientRect().bottom;
  })) - box.top + controls.scrollTop + 28;
  controls.style.setProperty('--slack', Math.max(0, target + controls.clientHeight - contentEnd) + 'px');
  controls.scrollTop = target;
}

// One line per row, with the row's pick. A row shows its options only while it
// is open, and one row is open at a time.
class LookRows extends Drawn {
  static fields = FIELDS;

  // The rows are the mode's, so a switch replaces them and the row that was
  // open closes with the set it came from.
  willUpdate() {
    if (this.mode !== get('mode')) {
      this.mode = get('mode');
      openRow = null;
    }
  }

  updated() {
    const pending = settle;
    if (!pending) return;
    settle = null;
    Promise.all(lookElements().map((element) => element.updateComplete)).then(function () {
      holdRowUnderPointer(pending);
    });
  }

  toggleRow(name) {
    openRow = openRow === name ? null : name;
    this.requestUpdate();
  }

  // A pick from the rows puts the text under the prompt above them.
  pickInPlace(row, label) {
    settle = { row: row.name, before: toggleOf(row.name).getBoundingClientRect().top };
    openRow = null;
    page.pick(row, label);
  }

  render() {
    return html`${page.rows().map((row) => {
      const picks = page.picks()[row.name] || [];
      const picked = picks[0];
      const open = openRow === row.name;
      return html`<div class="look-row"><button type="button" class="look-row-toggle" data-row=${row.name} aria-expanded=${String(open)} @click=${() => this.toggleRow(row.name)}><span class="label">${row.name}</span><span class="look-pick${picked ? ' picked' : ''}">${picked || 'none'}</span></button><div class="look-chips" ?hidden=${!open}>${row.options.map(([label]) => html`<button type="button" class="chip" aria-pressed=${String(picks.includes(label))} @click=${() => this.pickInPlace(row, label)}>${label}</button>`)}</div></div>`;
    })}`;
  }
}

// The summary's read-back: the picks by name, in the rows' own order, or `none`.
class LookValues extends Drawn {
  static fields = FIELDS;

  render() {
    const labels = page.labels();
    return html`${labels.length ? labels.join(', ') : 'none'}`;
  }
}

// Under the prompt: one chip per pick, which takes it back off, then the
// sentence the run adds and the avoid part the negative prompt will carry.
// An unpick closes an open row as a pick does, and needs no correction: it is
// not a click on a row.
function unpick(row, label) {
  openRow = null;
  page.pick(row, label);
}

class LookAdds extends Drawn {
  static fields = FIELDS;

  willUpdate() { this.hidden = !page.text(); }

  render() {
    const added = page.text();
    if (!added) return html``;
    const picks = page.picks();
    const avoids = page.avoids();
    return html`${page.rows().flatMap((row) => (picks[row.name] || []).map((label) => html`<button type="button" class="chip" aria-label=${'Remove ' + label} @click=${() => unpick(row, label)}>${label} ×</button>`))}<q>${added}</q>${avoids ? html`<p class="look-avoids">${'Negative prompt adds: ' + avoids + '. Each image takes about twice as long.'}</p>` : ''}`;
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
      page = helpers;
      lookElements().forEach(function (element) { element.requestUpdate(); });
    },
  },
}));
