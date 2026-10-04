// The theme menu, and the theme itself from the moment the page can draw it.
//
// The page's inline head script sets the saved theme before the first paint, so
// the page never flashes the default. That part must stay inline: this module is
// deferred, and a deferred script lets the default paint first.
//
// This module owns everything after that. The theme lives in the store, and the
// document carries it as `data-theme`, so a check reads the state from the DOM
// and not from this module.
//
// showToast still belongs to the page's inline script, and a classic script puts
// its top-level declarations in the global scope, so this module reads it from
// there. A slice of its own moves the toasts.

import { get, set, subscribe } from './state.js';
import { menuItem, toggleMenu } from '../components/popup-menu.js';

const THEMES = [['', 'Darkroom'], ['leica', 'Leica M'], ['kodak', 'Kodak Instamatic'],
  ['polaroid', 'Polaroid SX-70']];

function savedTheme() {
  return document.documentElement.dataset.theme || '';
}

// The one place the theme leaves the store: the document carries it, and this
// browser keeps the pick.
function paintTheme(id) {
  if (id) document.documentElement.dataset.theme = id;
  else delete document.documentElement.dataset.theme;
  try {
    localStorage.setItem('studio-theme', id);
  } catch (error) {
    showToast('info', 'The theme applies to this tab only: ' + error.message);
  }
}

function markTheme() {
  const current = get('theme');
  document.querySelectorAll('#theme-menu [role=menuitemradio]').forEach(function (item) {
    item.setAttribute('aria-checked', String(item.dataset.theme === current));
  });
}

function mountMenu() {
  const menu = document.getElementById('theme-menu');
  document.getElementById('theme-toggle').addEventListener('click', function () { toggleMenu(menu); });
  const section = document.createDocumentFragment();
  const head = document.createElement('div');
  head.className = 'menu-head';
  head.textContent = 'Theme';
  section.append(head);
  THEMES.forEach(function ([id, name]) {
    const item = menuItem('check', name, function () { set('theme', id); });
    item.setAttribute('role', 'menuitemradio');
    item.dataset.theme = id;
    section.append(item);
  });
  // The Images section is the page's, and it appends. This one prepends, so the
  // menu reads the same whichever of the two scripts runs first.
  menu.prepend(section);
}

mountMenu();
// The head script already painted the saved theme. Seed the store from that DOM
// state, then mark the menu. No consumer listens yet, so nothing redraws twice.
set('theme', savedTheme());
markTheme();
// A pick goes into the store as one line. The redraw below is the only thing
// that paints the document and the menu.
subscribe(['theme'], function (field) {
  paintTheme(get(field));
  markTheme();
});
