// The References: the empty zone's words, the thumbnails and their remove, the
// tile that offers one more, and the note that counts them and measures the last.
//
// A tree drawn from the store, so Lit. The render root is the element itself, so
// every id a check reaches stays on the node it names: `#refs-empty` with its
// `#refs-title` and `#refs-sub`, `#thumbs` and the thumbnail inside it, and
// `#refs-note`. The element draws no box of its own (`display: contents`), so
// those three sit in the zone exactly as they did, and the zone stays the page's:
// `#refs` carries the click, the keydown and the three drag listeners that open
// the chooser, and the page hangs them while the markup is parsed.
//
// The list itself stays the page's, because it is what a run posts and the page
// is the only thing that can read a file into it. The page mirrors the array into
// the store on every change, which is what redraws this tree. The two things the
// tree cannot see arrive on `reference-list-ready`: how many images the mode
// takes, and what a remove does, which is the page's because it owns the array.

import { LitElement, html } from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import { get, subscribe } from '../lib/state.js';

// The page's helpers, on `reference-list-ready`.
let page = null;

const FIELDS = ['references', 'mode'];

// The sprite the page draws its icons from, in the page's own document.
function icon(name) {
  return html`<svg class="icon" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
}

class ReferenceList extends LitElement {
  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    subscribe(FIELDS, () => this.requestUpdate());
  }

  // The note counts the images and reads the last one's measured size back, so a
  // wrong measurement is visible where the mask would take its own shape from it.
  note() {
    const references = get('references') || [];
    if (!references.length) return '';
    if (get('mode') !== 'edit') return 'Drop or paste another image to replace it.';
    const last = references[references.length - 1];
    return references.length + ' of ' + page.limit() + ' images. The result takes the shape of the last one'
      + (last.width ? ', ' + last.width + ' × ' + last.height + '.' : '.');
  }

  render() {
    if (!page) return html``;
    const references = get('references') || [];
    const editing = get('mode') === 'edit';
    const limit = page.limit();
    const count = references.length;
    return html`<div class="refs-empty" id="refs-empty" ?hidden=${count > 0}>${icon('image')}<div><strong id="refs-title">${editing ? 'Add the image to edit' : 'Start from an image'}</strong><span id="refs-sub">${editing ? 'Drop, paste or choose up to ' + limit + '.' : 'Optional. Drop, paste or choose one.'}</span></div></div><div class="thumbs" id="thumbs">${references.map((reference, index) => html`<div class="thumb" title=${reference.name}><img src=${'data:image/png;base64,' + reference.b64} alt=${reference.name}><button type="button" class="remove" aria-label=${'Remove ' + reference.name} @click=${(event) => { event.stopPropagation(); page.remove(index); }}>${icon('x')}</button></div>`)}${editing && count && count < limit ? html`<div class="add-tile">${icon('plus')}</div>` : ''}</div><div class="refs-note" id="refs-note" ?hidden=${count === 0}>${this.note()}</div>`;
  }
}

customElements.define('reference-list', ReferenceList);

// The door. The page registered its listener while the markup was parsed, and
// this fires while the module is evaluated: after the markup, before any
// interaction. The handle is in place before the first render, because Lit
// renders on a microtask and this dispatch is synchronous.
document.dispatchEvent(new CustomEvent('reference-list-ready', {
  detail: {
    configure: function (helpers) {
      page = helpers;
      document.querySelectorAll('reference-list').forEach(function (element) { element.requestUpdate(); });
    },
  },
}));
