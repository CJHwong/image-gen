// The store. One place holds the page's state, and one rule draws it.
//
// A consumer names the fields it draws from. A mutation names the field it
// touched, and the store redraws only the consumers that named it. Nothing draws
// itself because something else happened to run first. That order bug is what
// this replaces: thirteen sections each hold their own variables and call
// renderX() by hand.
//
// The fields are the design's (PAGE-REFACTOR.md, "State"). A consumer may name a
// field or its whole group. A value is a whole value, so the store compares by
// identity and an unchanged one redraws nothing.

export const GROUPS = {
  form: ['mode', 'prompt', 'typed', 'size', 'resolution', 'steps', 'guidance', 'cfg', 'seed',
    'negative', 'count', 'looks'],
  references: ['references', 'marks', 'marking'],
  results: ['gallery', 'view', 'busy', 'progress'],
  kept: ['keeping', 'theme', 'fullscreen'],
  run: ['cleared', 'cancelRestore', 'runLook'],
};

// Which group a field belongs to. A name that is neither a field nor a group
// throws, so a typo fails at the call and not in silence.
const GROUP_OF = new Map();
Object.entries(GROUPS).forEach(function ([group, fields]) {
  fields.forEach(function (field) { GROUP_OF.set(field, group); });
});

const values = new Map();
const consumers = new Set();

function groupOf(name) {
  if (GROUP_OF.has(name)) return GROUP_OF.get(name);
  if (name in GROUPS) return name;
  throw new Error('Unknown state field or group: ' + name);
}

export function get(field) {
  groupOf(field);
  return values.get(field);
}

export function set(field, value) {
  const group = groupOf(field);
  if (Object.is(values.get(field), value)) return;
  values.set(field, value);
  consumers.forEach(function (consumer) {
    if (consumer.fields.has(field) || consumer.groups.has(group)) consumer.redraw(field);
  });
}

// A consumer names the fields, or the groups, it draws from. The store keeps the
// redraw and calls it with the field that changed.
export function subscribe(names, redraw) {
  const consumer = { fields: new Set(), groups: new Set(), redraw: redraw };
  names.forEach(function (name) {
    if (name in GROUPS) consumer.groups.add(name);
    else { groupOf(name); consumer.fields.add(name); }
  });
  consumers.add(consumer);
}

// The door. The page's own script is still a classic script, so it cannot import
// this module and has no other way to mirror a field into the store. The store
// announces itself on `state-ready`, and the page holds the handle it gets in
// that handler. The page registered the listener while the markup was parsed,
// and this fires while the module is evaluated: after the markup, before any
// interaction, so the handle is in place before the first form change. This door
// closes when the inline script is gone.
document.dispatchEvent(new CustomEvent('state-ready', { detail: { get, set, subscribe } }));
