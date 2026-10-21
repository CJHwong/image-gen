let opening;
function database() {
  if (!opening) opening = new Promise((resolve, reject) => {
    const request = indexedDB.open('studio-drafts', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('inputs');
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
  return opening;
}

export async function loadDraft(key) {
  const db = await database();
  return new Promise((resolve, reject) => {
    const request = db.transaction('inputs').objectStore('inputs').get(key);
    request.onsuccess = () => resolve(request.result || null);
    request.onerror = () => reject(request.error);
  });
}

export async function saveDraft(key, record, expectedId = undefined) {
  const db = await database();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction('inputs', 'readwrite');
    const store = transaction.objectStore('inputs');
    const current = store.get(key);
    let saved = false;
    current.onsuccess = () => {
      if (expectedId !== undefined && current.result?.id !== expectedId) return;
      if (current.result?.updatedAt > record.updatedAt) return;
      store.put(record, key);
      saved = true;
    };
    transaction.oncomplete = () => resolve(saved);
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error || new Error('Draft storage was interrupted.'));
  });
}

export async function clearDrafts() {
  const db = await database();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction('inputs', 'readwrite');
    transaction.objectStore('inputs').clear();
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error);
  });
}

function createDrafts(page) {
  const records = {};
  const loading = new Set();
  const finishing = new Set();
  let applying = false;
  let stateDepth = 0;
  let epoch = 0;
  const paused = new Set();
  const restores = new Map();
  let writes = Promise.resolve();
  const key = workspace => workspace + ':' + page.backend(workspace);
  const stamp = () => performance.timeOrigin + performance.now();
  const failure = error => {
    console.warn('Input settings were not saved:', error);
    page.notify('error', 'This browser could not keep the input settings.');
  };
  function queue(action) { writes = writes.then(action).catch(failure); return writes; }
  function record(inputs, submitted = null) {
    return {id: crypto.randomUUID(), updatedAt: stamp(), inputs: structuredClone(inputs), submitted};
  }
  function changed(workspace) {
    if (applying || stateDepth || paused.has(workspace) || !page.keeping() || page.blocked()) return;
    const name = key(workspace);
    const next = record(page.snapshot(workspace));
    records[name] = next;
    const version = epoch;
    queue(() => version === epoch && page.keeping() ? saveDraft(name, next) : undefined);
  }
  async function restore(workspace) {
    const name = key(workspace);
    const version = epoch;
    const token = Symbol();
    restores.set(workspace, token);
    paused.delete(workspace);
    loading.add(workspace);
    try {
      const stored = await loadDraft(name);
      if (page.ready) await page.ready(workspace);
      if (version !== epoch || name !== key(workspace) || restores.get(workspace) !== token || !page.keeping()) return;
      if (records[name]?.updatedAt > (stored?.updatedAt || 0)) return;
      records[name] = stored;
      if (!stored) return;
      applying = true;
      page.restore(workspace, structuredClone(stored.inputs));
    } catch (error) { failure(error); }
    finally {
      applying = false;
      if (restores.get(workspace) === token) loading.delete(workspace);
    }
  }
  function submit(workspace) {
    if (!page.keeping()) return;
    const name = key(workspace);
    const next = record(page.snapshot(workspace), {clientId: page.clientId});
    records[name] = next;
    const version = epoch;
    queue(() => version === epoch && page.keeping() ? saveDraft(name, next) : undefined);
    return next.id;
  }
  async function finish(workspace, submitted, operation) {
    finishing.add(operation.id);
    const name = key(workspace);
    const version = epoch;
    try {
      const next = record(operation.status === 'succeeded' ? page.empty(workspace, submitted.inputs) : submitted.inputs);
      const saved = await queue(() => version === epoch && page.keeping() ? saveDraft(name, next, submitted.id) : false);
      if (!saved || version !== epoch || name !== key(workspace) || records[name]?.id !== submitted.id) return;
      records[name] = next;
      applying = true;
      page.restore(workspace, structuredClone(next.inputs));
    } finally { applying = false; finishing.delete(operation.id); }
  }
  function observe(operations) {
    const ordered = operations.slice().sort((left, right) => right.started_at - left.started_at);
    for (const workspace of ['image', 'video']) {
      const name = key(workspace);
      const saved = records[name];
      if (!saved?.submitted || loading.has(workspace)) continue;
      const operation = ordered.find(one => one.workspace === workspace && one.client_id === saved.submitted.clientId
        && one.settings?.draft_id === saved.id);
      if (operation && !['running', 'stopping'].includes(operation.status) && !page.blocked() && !finishing.has(operation.id)) {
        finish(workspace, saved, operation).catch(failure);
      }
    }
  }
  function keep(on) {
    epoch += 1;
    if (on) {
      changed('image');
      changed('video');
    } else {
      Object.keys(records).forEach(name => { delete records[name]; });
      queue(clearDrafts);
    }
  }
  document.addEventListener('draft-change', event => changed(event.detail));
  document.addEventListener('input', event => {
    if (event.target.closest('#video-controls')) changed('video');
  });
  document.addEventListener('change', event => {
    if (event.target.closest('#video-controls')) changed('video');
  });
  document.addEventListener('click', event => {
    if (event.target.closest('#video-controls')) queueMicrotask(() => changed('video'));
  });
  if (page.keeping()) {
    restore('image');
    restore('video');
  }
  return {changed, restore, submit, observe, keep,
    suspend: () => { stateDepth += 1; }, resume: () => { stateDepth -= 1; }, pause: workspace => paused.add(workspace), flushed: () => writes, loading: () => loading.size > 0};
}

document.dispatchEvent(new CustomEvent('drafts-ready', {detail: {configure: createDrafts}}));
