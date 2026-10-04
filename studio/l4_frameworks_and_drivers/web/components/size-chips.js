// Size and resolution: the ratio chips, the sizes of the chosen shape, the
// resolution buttons and the caption above them.
//
// These draw trees from the store, so they are Lit elements. The render root is
// the element itself, so the markup keeps its id, its class and its attributes:
// htmx resolves `hx-target` with `document.querySelector`, and the browser checks
// read the DOM.
//
// The page's own script is still a classic script. It cannot import this module,
// and this module cannot see the page's helpers while the markup is parsed. So
// the module announces itself on `size-chips-ready` with a `configure` function,
// and the page hands over what it owns: the two option lists, the two form
// selects the chips drive, and the four derivations the size field shares with
// the run estimate. Those four stay the page's until their own slice moves them.
//
// A redraw is the store's: each element names the fields it is sensitive to, and
// the page mirrors the fields into the store on every form change.

import { LitElement, html } from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import { subscribe } from '../lib/state.js';

// The page's helpers, on `size-chips-ready`.
let page = null;

// A block of pixels to the name both modes give it. The exact pixels show once,
// in the caption above.
function megapixels(pixels) {
  const mp = pixels / 1e6;
  return (mp < 1 ? mp.toFixed(1) : String(Math.round(mp * 10) / 10)) + ' MP';
}

// A ratio's glyph, drawn as the page always drew it.
function glyph(ratio) {
  if (ratio === 'match') {
    return html`<span class="glyph"><i class="dashed" style="width:13px;height:13px"></i></span>`;
  }
  const parts = ratio.split(':').map(Number);
  const wide = parts[0] >= parts[1];
  const width = wide ? 16 : Math.round(16 * parts[0] / parts[1]);
  const height = wide ? Math.round(16 * parts[1] / parts[0]) : 16;
  return html`<span class="glyph"><i style="width:${width}px;height:${height}px"></i></span>`;
}

// The shape the chips and the tiers agree on.
function ratioInForce() {
  const current = page.currentOption();
  return current ? current.ratio : 'match';
}

// A chip sets the shape, at the tier nearest one megapixel, where the model was
// trained. A pick of the shape already in force does nothing.
function pickRatio(ratio) {
  if (ratio === 'match') return page.setSelect(page.sizeSelect, 'match');
  const current = page.currentOption();
  if (current && current.ratio === ratio) return;
  const group = page.sizes.filter(function (option) { return option.ratio === ratio; });
  const preferred = group.slice().sort(function (a, b) {
    return Math.abs(a.width * a.height - 1048576) - Math.abs(b.width * b.height - 1048576);
  })[0];
  page.setSelect(page.sizeSelect, preferred.value);
}

// Every element here draws from the store, so every one redraws when a field it
// named changes. The values themselves come from the page's own accessors, so a
// mirrored field can never disagree with the control it mirrors.
class Drawn extends LitElement {
  static fields = [];

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    subscribe(this.constructor.fields, () => this.requestUpdate());
  }
}

const SIZE_FIELDS = ['size', 'resolution', 'references', 'mode'];

class SizeChips extends Drawn {
  static fields = SIZE_FIELDS;

  render() {
    const ratio = ratioInForce();
    return html`${page.ratios.concat(['match']).map((one) => html`<button type="button" class="chip" data-ratio=${one} aria-pressed=${String(one === ratio)} @click=${() => pickRatio(one)}>${glyph(one)}<span>${one === 'match' ? 'Match' : one}</span></button>`)}`;
  }
}

// The sizes of the chosen shape, smallest first. A backend with a resolution
// parameter asks for pixels and not for a shape, so it has no tiers to show.
class TierSizes extends Drawn {
  static fields = SIZE_FIELDS;

  willUpdate() {
    this.hidden = ratioInForce() === 'match';
  }

  render() {
    const ratio = ratioInForce();
    const chosen = page.sizeSelect.value;
    return html`${page.sizes.filter(function (option) { return option.ratio === ratio; })
      .sort(function (a, b) { return a.width * a.height - b.width * b.height; })
      .map((option) => html`<button type="button" class="num" title=${option.width + ' × ' + option.height} aria-pressed=${String(option.value === chosen)} @click=${() => page.setSelect(page.sizeSelect, option.value)}>${megapixels(option.width * option.height)}</button>`)}`;
  }
}

// A resolution sets pixels only, and the shape follows the reference. The names
// follow the chosen ratio, which is why a check finds the first tier by its
// position and not by its name.
class EditSizes extends Drawn {
  static fields = SIZE_FIELDS;

  render() {
    const chosen = page.resolutionSelect.value;
    return html`${page.resolutions.slice()
      .sort(function (a, b) { return (a === 'match' ? 0 : Number(a)) - (b === 'match' ? 0 : Number(b)); })
      .map((value) => html`<button type="button" class="num" data-value=${value} aria-pressed=${String(value === chosen)} @click=${() => page.setSelect(page.resolutionSelect, value)}>${value === 'match' ? 'Match' : megapixels(Number(value) ** 2)}</button>`)}`;
  }
}

class SizeCaption extends Drawn {
  static fields = SIZE_FIELDS;

  render() {
    const current = page.currentOption();
    const reference = page.lastReference();
    let text;
    if (page.followsReference()) {
      text = reference && reference.width
        ? 'about ' + page.editResolution() + ' px, shape follows the image'
        : 'shape follows the image';
    } else if (current) {
      text = current.width + ' × ' + current.height;
    } else {
      text = reference ? 'reference shape, about 1 MP' : '1024 × 1024 until you add an image';
    }
    return html`${text}`;
  }
}

customElements.define('size-chips', SizeChips);
customElements.define('tier-sizes', TierSizes);
customElements.define('edit-sizes', EditSizes);
customElements.define('size-caption', SizeCaption);

// The door. The page registered its listener while the markup was parsed, and
// this fires while the module is evaluated: after the markup, before any
// interaction. The handle is in place before the first render, because Lit
// renders on a microtask and this dispatch is synchronous.
document.dispatchEvent(new CustomEvent('size-chips-ready', {
  detail: {
    configure: function (helpers) {
      page = helpers;
      ['size-chips', 'tier-sizes', 'edit-sizes', 'size-caption'].forEach(function (name) {
        document.querySelectorAll(name).forEach(function (element) { element.requestUpdate(); });
      });
    },
  },
}));
