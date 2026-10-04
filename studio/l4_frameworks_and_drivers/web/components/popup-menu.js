// The page's popup menus: the backend picker, the theme menu, the count menu and
// the more menu. They differ only in their items, so one manager owns them all.
//
// A menu is a `div.menu` the markup already carries, hidden until it opens. Its
// toggle is the element that names it in `aria-controls`. One menu is open at
// most: a pick, a click outside or Escape closes it, and Escape puts focus back
// on the toggle. The arrow keys walk its items.
//
// This draws no tree. It opens, closes, moves focus and routes keys, and two of
// the four menus rebuild their items on each open. Its work has to finish in the
// task that asked for it: the count menu focuses its checked item in the same
// task it opens, which an asynchronous render could not do. So it is a plain
// light-DOM module and not a Lit element, which the design's Decisions table
// now says.
//
// The page's own script is still a classic script, and a classic script cannot
// import a module. So the manager announces itself on `popup-menus-ready` and
// the page mounts its menu sections in that handler. The event fires while this
// module is evaluated, which is after the markup is parsed and before any
// interaction, so those sections are built in the same slot they always were.
// This one door closes when the inline script is gone.

// The glyph of an item. The page draws its own controls the same way, and the
// item's own markup has to match it, so the two agree by the same three lines.
function glyph(name) {
  return '<svg class="icon" aria-hidden="true"><use href="#i-' + name + '"/></svg>';
}

// The element that opens and closes a menu, named by the menu's own id.
function toggleOf(menu) {
  return document.querySelector('[aria-controls="' + menu.id + '"]');
}

// One item of a menu. `name` is the glyph, or empty for a menu that reads as
// text only, as a template does. The caller sets `menuitemradio` or
// `menuitemcheckbox` and `aria-checked` on what this returns.
export function menuItem(name, label, onPick) {
  const button = document.createElement('button');
  button.type = 'button';
  button.setAttribute('role', 'menuitem');
  button.innerHTML = (name ? glyph(name) : '') + '<span class="item-text"></span>';
  button.querySelector('.item-text').textContent = label;
  button.addEventListener('click', function () {
    closeMenus();
    onPick();
  });
  return button;
}

// Opens the menu, or closes it when it is already open. Opening one closes
// whatever else is open, so the page never shows two. The focus lands in this
// same task, which is what the count menu leans on.
export function toggleMenu(menu) {
  const opening = menu.hidden;
  closeMenus();
  if (!opening) return;
  menu.hidden = false;
  toggleOf(menu).setAttribute('aria-expanded', 'true');
  menu.querySelector('button').focus();
}

export function closeMenus() {
  document.querySelectorAll('.menu:not([hidden])').forEach(function (menu) {
    menu.hidden = true;
    const toggle = toggleOf(menu);
    if (toggle) toggle.setAttribute('aria-expanded', 'false');
  });
}

document.addEventListener('click', function (event) {
  if (event.target.closest('.menu, [aria-controls]')) return;
  closeMenus();
});

document.addEventListener('keydown', function (event) {
  const open = document.querySelector('.menu:not([hidden])');
  if (!open) return;
  if (event.key === 'Escape') {
    closeMenus();
    toggleOf(open).focus();
    return;
  }
  if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
  event.preventDefault();
  const items = Array.from(open.querySelectorAll('button'));
  const step = event.key === 'ArrowDown' ? 1 : -1;
  const index = items.indexOf(document.activeElement);
  items[(index + step + items.length) % items.length].focus();
});

document.dispatchEvent(new CustomEvent('popup-menus-ready', { detail: { menuItem, toggleMenu, closeMenus } }));
