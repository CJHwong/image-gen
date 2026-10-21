// Keep an expanded editor still until the click that leaves it has reached its target.
// Collapsing on mousedown moves controls before mouseup and can swallow their click.
const selector = '.prompt-field textarea';
const pending = new Set();
let pointing = false;

function collapse(field) {
  field.classList.remove('expanded-editor');
  field.dispatchEvent(new Event('editor-collapse'));
}

document.addEventListener('pointerdown', () => {
  pointing = true;
  if (document.activeElement?.matches(selector)) document.activeElement.classList.add('expanded-editor');
}, true);

document.addEventListener('focusin', event => {
  if (event.target.matches(selector)) event.target.classList.add('expanded-editor');
});

document.addEventListener('focusout', event => {
  if (!event.target.matches(selector)) return;
  if (pointing) pending.add(event.target);
  else collapse(event.target);
});

function release() {
  pointing = false;
  setTimeout(() => {
    pending.forEach(field => {
      if (field !== document.activeElement) collapse(field);
    });
    pending.clear();
  }, 0);
}

document.addEventListener('pointerup', release, true);
document.addEventListener('pointercancel', release, true);
window.addEventListener('blur', release);
