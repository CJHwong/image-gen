// The run button's labels: the two verbs, and the two states of a run.
//
// The button itself is the form's submit button and stays in the page's markup,
// because a custom element cannot submit a form. This draws what the button
// says, into the element itself as the render root, and the page's `#go-sub`
// beside it stays the page's.
//
// Which label shows is the DOM's and never the cascade's. The page used to give
// all but one label `display: none`, so a stylesheet that failed to load left
// the button named "GenerateEdit Cancel Stopping…" to a screen reader, and no
// verb could be matched in it. `hidden` on the label is what picks, here as
// before, and no rule sets `display` on a label.
//
// The run state arrives as this element's own `data-state`, mirrored from `#go`
// by the page, because `stopping` is a class on the body and not a store field.
// The verb arrives from the store's `mode`.

import { LitElement, html } from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import { get, subscribe } from '../lib/state.js';

class RunLabels extends LitElement {
  static properties = { state: { attribute: 'data-state', type: String } };

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    subscribe(['mode'], () => this.requestUpdate());
  }

  render() {
    const stopping = this.state === 'stopping';
    const running = this.state === 'busy' || stopping;
    const editing = get('mode') === 'edit';
    return html`<span class="main"><span class="idle-label" ?hidden=${running}><span class="generate-only" ?hidden=${editing}>Generate</span><span class="edit-only" ?hidden=${!editing}>Edit</span></span><span class="busy-label" ?hidden=${!running || stopping}>Cancel</span><span class="stopping-label" ?hidden=${!stopping}>Stopping&hellip;</span></span>`;
  }
}

customElements.define('run-button', RunLabels);
