// The progress card: the frame the page shows while a run goes.
//
// This is a drawing with a sequence, not a tree drawn from state, so it is a
// plain light-DOM module and not a Lit element. The design's test decides it:
// the plate's exposure only grows with a sweep, and a drop has to apply in the
// task that asked for it. `paint` reads the offset back between clearing the
// class and putting it on, and a render that landed a tick later would show the
// drop instead of the sweep. The card is also fitted from its own box in the
// same task that builds it, and a Lit render has not happened yet at that
// point.
//
// htmx keeps `#progress`. The poll swaps that element's children, and the
// children it swaps in carry the `hx-get` the next poll arrives on, so a render
// root over that subtree would take the loop with it and the run would stop
// reporting. This module never touches `#progress`: what it draws is the card,
// in `#canvas`, beside it.
//
// The card's own parts are what the checks read: `.card .plate`, `.exposure`
// and `.percent`, and `--exposed` is the property the CSS consumes for the
// sweep, the drop, the rise and the develop. Every one of them stays.

// The card for the run in flight, fitted and painted by the caller: the page
// fits it from the stage it was put in, and paints it on the progress it reads.
// The film's plate comes first, then its edge print, which carries the model's
// name and the number of the frame the run is making.
export function mount(canvas, edge, number) {
  const card = document.createElement('div');
  card.className = 'card';
  card.innerHTML = '<div class="plate"><div class="exposure"></div><span class="percent num"></span></div>'
    + '<div class="edge"><span>' + edge + '</span><span>' + number + '</span></div>';
  canvas.append(card);
}

// Exposure only grows with a sweep. A drop, at the next image of a batch or a
// new run, jumps back to the left edge at once.
function paint(plate, running, percent) {
  const rewind = percent < (parseFloat(plate.style.getPropertyValue('--exposed')) || 0);
  plate.classList.toggle('rewind', rewind);
  plate.classList.toggle('waiting', !running);
  plate.style.setProperty('--exposed', percent + '%');
  if (!rewind) return;
  void plate.offsetWidth;   // apply the drop while the sweep is off
  plate.classList.remove('rewind');
}

// Every plate a run has on the page: the card's own, and the waiting frame the
// strip draws in front of the strip's images. The percentage belongs to the
// card, so a plate without one is painted and nothing is written into it.
export function paintAll(running, percent) {
  document.querySelectorAll('.card, .frame.pending .still').forEach(function (plate) {
    paint(plate, running, percent);
    const label = plate.querySelector('.percent');
    if (label) label.textContent = running ? percent + '%' : '';
  });
}

// The door. The page's own script is still a classic script, so it cannot
// import this module. The listener is registered while the markup is parsed and
// this fires while the module is evaluated: after the markup, before any
// interaction, so the handle is in place before the first run. This door closes
// when the inline script is gone.
document.dispatchEvent(new CustomEvent('progress-card-ready', { detail: { mount, paintAll } }));
