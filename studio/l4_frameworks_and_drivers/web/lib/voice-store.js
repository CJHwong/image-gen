let opening;
function database() {
  if (!opening) opening = new Promise((resolve, reject) => {
    const request = indexedDB.open('studio-voice', 2);
    request.onupgradeneeded = event => {
      const db = request.result;
      if (event.oldVersion < 1) db.createObjectStore('state');
      const media = db.createObjectStore('media');
      const state = request.transaction.objectStore('state');
      const current = state.get('project');
      current.onsuccess = () => { if (current.result) state.put(withoutAudio(current.result, media), 'project'); };
    };
    request.onsuccess = () => { request.result.onversionchange = () => request.result.close(); resolve(request.result); };
    request.onblocked = () => reject(new Error('Reload other Studio tabs to update audio storage.'));
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
    const transaction = db.transaction(['state', 'media'], 'readwrite');
    const store = transaction.objectStore('state');
    const current = store.get('project');
    current.onsuccess = () => {
      const replaceDraft = draft && (expectedDraftId === undefined || (current.result?.draftId ?? null) === expectedDraftId);
      const metadata = withoutAudio(project, transaction.objectStore('media'));
      const merged = mergeProject(current.result, metadata, replaceDraft, selection);
      const retained = new Set(merged.segments.flatMap(segment => segment.takes.map(take => take.id)));
      const media = transaction.objectStore('media');
      const cursor = media.openKeyCursor();
      cursor.onsuccess = () => { const entry = cursor.result; if (!entry) return; if (!retained.has(entry.key)) media.delete(entry.key); entry.continue(); };
      store.put(merged, 'project');
    };
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error || new Error('Voice storage was interrupted.'));
  });
}

export async function clearVoice() {
  const db = await database();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(['state', 'media'], 'readwrite');
    transaction.objectStore('state').clear();
    transaction.objectStore('media').clear();
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error);
  });
}

// The project contains searchable facts and peaks; original WAVs live separately.
function withoutAudio(project, media) {
  return {...project, segments: project.segments.map(segment => ({...segment,
    takes: segment.takes.map(take => {
      const {blob, url, mediaLoading, mediaError, ...metadata} = take;
      if (blob && !take.stored) media.put(blob, take.id);
      return {...metadata, stored: Boolean(blob || take.stored)};
    }),
  }))};
}

export async function loadVoiceTake(id) {
  const db = await database();
  return new Promise((resolve, reject) => {
    const request = db.transaction('media').objectStore('media').get(id);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error);
  });
}
