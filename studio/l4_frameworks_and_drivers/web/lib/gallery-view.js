// Presentation preferences only. Media records and their IndexedDB schema stay unchanged.
const prefix = 'studio-gallery-view-';
export function galleryView(workspace) {
  try {
    const saved = JSON.parse(sessionStorage.getItem(prefix + workspace) || '{}');
    return saved && typeof saved === 'object' && !Array.isArray(saved) ? saved : {};
  }
  catch { return {}; }
}
export function rememberGalleryView(workspace, patch, keeping = true) {
  try {
    if (!keeping) { sessionStorage.removeItem(prefix + workspace); return; }
    sessionStorage.setItem(prefix + workspace, JSON.stringify({...galleryView(workspace), ...patch}));
  } catch { /* Browsing still works when storage is unavailable. */ }
}
export function preferredGalleryId(workspace, entries, keeping = true) {
  if (!keeping) return null;
  const selected = galleryView(workspace).selected;
  return entries.find(entry => String(entry.id) === String(selected))?.id ?? null;
}
// Only explicit operation-item identities establish a batch; dates and prompts do not.
export function galleryBatch(identity, isOperation = false) {
  return typeof identity === 'string' ? identity.match(/^(.*):\d+$/)?.[1] || (isOperation ? identity : '') : '';
}
