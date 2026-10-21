let opening;
function database() {
  if (!opening) opening = new Promise((resolve, reject) => {
    const request = indexedDB.open('studio-voice', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('state');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  return opening;
}

export async function loadVoice() {
  const db = await database();
  return new Promise((resolve, reject) => {
    const request = db.transaction('state').objectStore('state').get('project');
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error);
  });
}

function mergeProject(previous, incoming, draft, selection) {
  if (!previous) return incoming;
  const removed = new Set([...(previous.removed || []), ...(incoming.removed || [])]);
  const cutoff = Math.max(previous.cutoff || 0, incoming.cutoff || 0);
  const base = draft ? incoming : previous;
  const other = draft ? previous : incoming;
  const segments = base.segments.map(segment => ({...segment, takes: segment.takes.slice()}));
  for (const segment of other.segments) {
    let target = segments.find(item => item.id === segment.id);
    if (!target && segment.takes.length) {
      target = {...segment, inScript: false, takes: []};
      segments.push(target);
    }
    if (target) {
      const ids = new Set(target.takes.map(take => take.id));
      target.takes.push(...segment.takes.filter(take => !ids.has(take.id)));
    }
  }
  for (const segment of segments) {
    segment.takes = segment.takes.filter(take => !removed.has(take.id) && take.createdAt > cutoff);
    if (!segment.takes.some(take => take.id === segment.selected)) segment.selected = segment.takes.at(-1)?.id || null;
    if (selection?.segmentId === segment.id && segment.takes.some(take => take.id === selection.takeId)) segment.selected = selection.takeId;
  }
  return {...base, segments: segments.filter(segment => segment.inScript !== false || segment.takes.length), selectedId: selection?.takeId || base.selectedId, removed: Array.from(removed).slice(-2048), cutoff};
}

export async function saveVoice(project, draft = false, selection = null, expectedDraftId = undefined) {
  const db = await database();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction('state', 'readwrite');
    const store = transaction.objectStore('state');
    const current = store.get('project');
    current.onsuccess = () => {
      const replaceDraft = draft && (expectedDraftId === undefined || (current.result?.draftId ?? null) === expectedDraftId);
      store.put(mergeProject(current.result, project, replaceDraft, selection), 'project');
    };
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error || new Error('Voice storage was interrupted.'));
  });
}

export async function clearVoice() {
  const db = await database();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction('state', 'readwrite');
    transaction.objectStore('state').clear();
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error);
  });
}
