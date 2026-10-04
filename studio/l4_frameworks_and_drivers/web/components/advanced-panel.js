// The advanced panel: the sentence its summary carries while it is closed, and
// the value beside each of its three sliders.
//
// These draw trees from the store, so they are Lit elements, with the element
// itself as the render root. The panel's own markup, the `details` element and
// its fields stay where they are: `#steps`, `#guidance`, `#cfg` and `#seed` are
// the form's fields, and the page fills their ranges and reads their values.
// Only what the panel draws from state is here.
//
// The page's own script cannot import this module, so the module announces
// itself on `advanced-panel-ready` and the page hands over the one helper this
// panel needs beyond the store: which of the two scale names the mode in force
// declares.
//
// The summary's sentence is only shown while the panel is closed, and that is
// the stylesheet's `details[open] summary .values { visibility: hidden }`, not
// this module's. The wording is the same either way.

import { LitElement, html } from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import { get, subscribe } from '../lib/state.js';

// The page's helpers, on `advanced-panel-ready`.
let page = null;

// The fields the panel's sentence and readouts are sensitive to. `negative` is
// the prompt the model will get, so a Look that adds an avoid part moves it.
const FIELDS = ['steps', 'guidance', 'cfg', 'seed', 'negative', 'mode'];

class Drawn extends LitElement {
  static fields = FIELDS;

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    subscribe(this.constructor.fields, () => this.requestUpdate());
  }
}

// The sentence the closed panel carries: the steps, the scale the mode calls
// guidance or cfg, the seed or that it is random, and whether a negative prompt
// goes with it.
class AdvancedValues extends Drawn {
  static fields = FIELDS;

  render() {
    const steps = get('steps');
    const scaleId = page.scaleParam();
    const scale = scaleId ? ', guidance ' + get(scaleId) : '';
    const seed = (get('seed') || '').trim();
    const negative = get('negative') ? ', negative prompt' : '';
    return html`${steps + ' steps' + scale + ', ' + (seed ? 'seed ' + seed : 'random seed') + negative}`;
  }
}

class StepsValue extends Drawn {
  static fields = FIELDS;

  render() { return html`${get('steps')}`; }
}

class GuidanceValue extends Drawn {
  static fields = FIELDS;

  render() { return html`${get('guidance')}`; }
}

class CfgValue extends Drawn {
  static fields = FIELDS;

  render() { return html`${get('cfg')}`; }
}

customElements.define('advanced-values', AdvancedValues);
customElements.define('steps-value', StepsValue);
customElements.define('guidance-value', GuidanceValue);
customElements.define('cfg-value', CfgValue);

document.dispatchEvent(new CustomEvent('advanced-panel-ready', {
  detail: {
    configure: function (helpers) {
      page = helpers;
      ['advanced-values', 'steps-value', 'guidance-value', 'cfg-value'].forEach(function (name) {
        document.querySelectorAll(name).forEach(function (element) { element.requestUpdate(); });
      });
    },
  },
}));
