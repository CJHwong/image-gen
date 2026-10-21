import {html} from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';

// The pencil loop, one hand-drawn stroke that overlaps where it closes. It is
// drawn once, on the redraw that picks a frame, and not on every redraw.
export function pencilLoop(draw = false) {
  return html`<svg class="mark${draw ? ' draw' : ''}" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><path pathLength="1" d="M58 5 C80 5 97 16 98 44 C99 74 84 95 52 96 C20 97 3 80 2 52 C1 24 18 7 44 4 C52 3 62 4 70 7"></path></svg>`;
}
