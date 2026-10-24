// The kept images: the browser's own store, and the tab that hears about it.
//
// The server keeps no image after it answers, so the browser keeps them, with
// their facts, until Clear all. Each one and its facts go to IndexedDB, so a
// reload or a new tab brings them back; localStorage holds about 5 MB, a few
// images. The store belongs to this address and port. Every change goes out on
// a channel, so each open tab shows the same strip.
//
// Two things stay the page's, and both are read before this module can be
// fetched. The keep setting is one: the page's strip note and its leave warning
// read it while the page is still parsing. The gallery array is the other: a
// run's answer lands in it, and this module only asks for it. So this module
// owns the database and the channel, and the page owns the setting and the
// array.
//
// The page's own script is still a classic script, so it cannot import this
// module and has no other way to put a record in. The listener is registered
// while the markup is parsed and this fires while the module is evaluated:
// after the markup, before any interaction. This door closes when the inline
// script is gone.

// The fields a stored record carries besides its two pictures. A record is read
// back into a gallery entry, so the list is the shape both ends agree on.
const KEPT_FIELDS = ['id', 'number', 'operationId', 'nativeMetadata', 'seed', 'width', 'height', 'steps', 'elapsed', 'position', 'mode', 'prompt',
  'typed', 'look', 'negative', 'sources', 'backend', 'backendId', 'precision', 'at'];

const channel = new BroadcastChannel('studio-gallery');

// The page's own, handed over on the door.
let page = null;

// The handle is opened once and kept: a browser that refuses one is only
// reachable at that first moment.
let database = null;
let videoDatabase = null;
function mediaRemovals(kind) {
  const removedIds = new Set();
  let clearedAt = 0;
  function remember(id) {
    removedIds.add(id);
    if (removedIds.size > 2048) removedIds.delete(removedIds.values().next().value);
  }
  function wasRemoved(entry) {
    try {
      JSON.parse(localStorage.getItem('studio-removed-' + kind) || '[]').forEach(remember);
      clearedAt = Math.max(clearedAt, Number(localStorage.getItem('studio-' + kind + '-cleared-at')) || 0);
    } catch (error) {
      console.warn('Media removals were not read:', error);
    }
    const completedAt = entry.at || entry.createdAt;
    return removedIds.has(String(entry.id)) || Boolean(clearedAt && (!completedAt || completedAt <= clearedAt));
  }
  function markRemoved(message) {
    wasRemoved({});
    if (message.kind.endsWith('remove')) remember(String(message.id));
    if (message.kind.endsWith('clear')) {
      (message.ids || []).forEach(id => remember(String(id)));
      message.clearedAt = message.clearedAt || Date.now();
      clearedAt = Math.max(clearedAt, message.clearedAt);
    }
    try {
      localStorage.setItem('studio-removed-' + kind, JSON.stringify(Array.from(removedIds)));
      localStorage.setItem('studio-' + kind + '-cleared-at', String(clearedAt));
    } catch (error) {
      console.warn('Media removals were not saved:', error);
    }
  }
  return {wasRemoved, markRemoved};
}
const {wasRemoved, markRemoved} = mediaRemovals('images');
const {wasRemoved: videoWasRemoved, markRemoved: markVideoRemoved} = mediaRemovals('videos');

function keepPreferred(media, record, removed) {
  if (!page.keeping() || removed(record)) return;
  const request = media.get(record.id);
  request.onsuccess = function () {
    if (!page.keeping() || removed(record)) return;
    if (!request.result) media.add(record);
    else if (record.nativeMetadata && !request.result.nativeMetadata) media.put(record);
  };
  return request;
}

function clearRemoved(media, removed) {
  const request = media.openCursor();
  request.onsuccess = function () {
    const cursor = request.result;
    if (!cursor) return;
    if (removed(cursor.value)) cursor.delete();
    cursor.continue();
  };
  return request;
}

function openStore() {
  if (!database) {
    database = new Promise(function (resolve, reject) {
      const request = indexedDB.open('studio', 1);
      request.onupgradeneeded = function () { request.result.createObjectStore('images', { keyPath: 'id' }); };
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error); };
    });
  }
  return database;
}

// Run one request on the images store. It settles when the transaction ends,
// so a write has landed before any other tab hears of it.
function inStore(access, work) {
  return openStore().then(function (store) {
    return new Promise(function (resolve, reject) {
      const transaction = store.transaction('images', access);
      const request = work(transaction.objectStore('images'));
      transaction.oncomplete = function () { resolve(request ? request.result : undefined); };
      transaction.onabort = function () { reject(transaction.error); };
    });
  });
}

function openVideoStore() {
  if (!videoDatabase) {
    videoDatabase = new Promise(function (resolve, reject) {
      const request = indexedDB.open('studio-video-gallery', 1);
      request.onupgradeneeded = function () { request.result.createObjectStore('clips', { keyPath: 'id' }); };
      request.onsuccess = function () { resolve(request.result); };
      request.onerror = function () { reject(request.error); };
    });
  }
  return videoDatabase;
}

function inVideoStore(access, work) {
  return openVideoStore().then(function (store) {
    return new Promise(function (resolve, reject) {
      const transaction = store.transaction('clips', access);
      const request = work(transaction.objectStore('clips'));
      transaction.oncomplete = function () { resolve(request ? request.result : undefined); };
      transaction.onabort = function () { reject(transaction.error); };
    });
  });
}

function blobOf(url) {
  return fetch(url).then(function (response) { return response.blob(); });
}

// A stored record as the live entry the strip draws. Each image is shown by a
// blob URL, because as a data URL every img that showed it made the browser
// parse megabytes of base64 text again.
// Metadata is browsable without retaining the original PNG or its before image.
function liveEntry(record) {
  const entry = {stored: true, hasBefore: Boolean(record.before)};
  KEPT_FIELDS.forEach(field => { entry[field] = record[field]; });
  entry.loadMedia = () => inStore('readonly', images => images.get(entry.id));
  return entry;
}
const loadedImages = new Map();
let retainingImages = false;
function releaseImage(entry) {
  page.release(entry);
  delete entry.src; delete entry.before; delete entry.b64;
}
async function hydrate(entry) {
  if (entry.src) return entry;
  if (!entry.loading) entry.loading = entry.loadMedia().then(record => {
    if (!record || wasRemoved(entry)) throw new Error('This image is no longer saved.');
    entry.src = URL.createObjectURL(record.png);
    entry.before = record.before && URL.createObjectURL(record.before);
    loadedImages.delete(entry.id); loadedImages.set(entry.id, entry);
    for (const [id, other] of loadedImages) {
      if (retainingImages || forgetPins.size || !page.keeping() || loadedImages.size <= 2) break;
      if (!other.stored || id === entry.id || id === page.selected?.()) continue;
      releaseImage(other); loadedImages.delete(id);
    }
    return entry;
  }).finally(() => { delete entry.loading; });
  return entry.loading;
}

// Read bounded pages, yielding between transactions. Cursor values are discarded after
// metadata extraction; no getAll of original media, decoding, or object URLs on restore.
async function scanRecords(open, name, visit) {
  let after;
  while (true) {
    const db = await open();
    const result = await new Promise((resolve, reject) => {
      const transaction = db.transaction(name, 'readonly');
      const request = transaction.objectStore(name).openCursor(after === undefined ? null : IDBKeyRange.lowerBound(after, true));
      let count = 0, last;
      request.onsuccess = () => {
        const cursor = request.result;
        if (!cursor) return;
        visit(cursor.value); last = cursor.key;
        if (++count < 32) cursor.continue();
      };
      transaction.oncomplete = () => resolve({count, last});
      transaction.onabort = () => reject(transaction.error);
    });
    if (result.count < 32) break;
    after = result.last;
    await new Promise(resolve => setTimeout(resolve, 0));
  }
}

function keep(entry) {
  if (!page.keeping() || wasRemoved(entry) || (entry.stored && !entry.src)) return Promise.resolve();
  return Promise.all([blobOf(entry.src), entry.before ? blobOf(entry.before) : null]).then(function ([png, before]) {
    const record = { png: png, before: before };
    KEPT_FIELDS.forEach(function (field) { record[field] = entry[field]; });
    return inStore('readwrite', function (images) {
      if (!page.keeping() || wasRemoved(entry)) return;
      if (!entry.operationId) return images.add(record);
      return keepPreferred(images, record, wasRemoved);
    });
  }).then(function () {
    if (!page.keeping() || wasRemoved(entry)) return;
    entry.stored = true; entry.hasBefore = Boolean(entry.before);
    entry.loadMedia = () => inStore('readonly', images => images.get(entry.id));
    // A retained image does not need a second base64 copy in memory.
    delete entry.b64;
    loadedImages.set(entry.id, entry);
    for (const [id, other] of loadedImages) {
      if (retainingImages || forgetPins.size || !page.keeping() || loadedImages.size <= 2) break;
      if (!other.stored || id === entry.id || id === page.selected?.()) continue;
      releaseImage(other); loadedImages.delete(id);
    }
    channel.postMessage({ kind: 'add', id: entry.id });
  }).catch(function (error) {
    page.notify('error', 'The browser did not keep image ' + page.frameNumber(entry.id) + ': ' + error.message
      + ' It stays in this tab until a reload. Download it to keep it.');
  });
}

function keepVideo(clip, mp4, thumbnail) {
  if (!page.keeping() || videoWasRemoved(clip)) return Promise.resolve(false);
  const record = {
    id: clip.id,
    name: clip.name,
    duration: clip.duration,
    metadata: clip.metadata,
    createdAt: clip.createdAt,
    nativeMetadata: clip.nativeMetadata,
    mp4: mp4,
    thumbnail: thumbnail || null,
  };
  return inVideoStore('readwrite', function (clips) { return keepPreferred(clips, record, videoWasRemoved); }).then(function () {
    channel.postMessage({kind: 'video-add', id: clip.id});
    return true;
  }).catch(function (error) {
    page.notify('error', 'The browser did not keep video ' + clip.name + ': ' + error.message
      + ' It stays in this tab until a reload.');
    return false;
  });
}

function keepVideoThumbnail(id, thumbnail) {
  if (!page.keeping()) return Promise.resolve(false);
  return inVideoStore('readwrite', function (clips) {
    const request = clips.get(id);
    request.onsuccess = function () {
      if (!request.result) return;
      request.result.thumbnail = thumbnail;
      clips.put(request.result);
    };
    return request;
  }).then(function () {
    return true;
  }).catch(function (error) {
    page.notify('error', 'The browser did not keep the thumbnail for video ' + id + ': ' + error.message);
    return false;
  });
}

async function loadVideos() {
  if (!page.keeping()) return [];
  const records = [];
  try {
    await scanRecords(openVideoStore, 'clips', record => {
      if (videoWasRemoved(record)) return;
      const {mp4, thumbnail, ...metadata} = record;
      records.push(metadata);
    });
    return records.sort((first, second) => first.createdAt - second.createdAt);
  } catch (error) { page.notify('error', 'The saved videos did not load: ' + error.message); return []; }
}

function removeVideo(id) {
  const message = {kind: 'video-remove', id: id};
  markVideoRemoved(message);
  channel.postMessage(message);
  if (!page.keeping()) return Promise.resolve(true);
  return inVideoStore('readwrite', function (clips) { return clips.delete(id); }).then(function () {
    return true;
  }).catch(function (error) {
    page.notify('error', 'The browser did not remove video ' + id + ': ' + error.message);
    return false;
  });
}

function clearVideos(ids = []) {
  const message = {kind: 'video-clear', ids: ids};
  markVideoRemoved(message);
  channel.postMessage(message);
  if (!page.keeping()) return Promise.resolve(true);
  return inVideoStore('readwrite', function (clips) { return clearRemoved(clips, videoWasRemoved); }).then(function () {
    return true;
  }).catch(function (error) {
    page.notify('error', 'The saved videos were not removed: ' + error.message);
    return false;
  });
}

// Delete from the store, then tell the other tabs. The work is the caller's,
// because what goes is the caller's to name. With keeping off there is nothing
// stored, and each tab's strip is its own.
function forget(work, message) {
  markRemoved(message);
  if (!page.keeping()) return;
  inStore('readwrite', message.kind === 'clear' ? images => clearRemoved(images, wasRemoved) : work).then(function () {
    channel.postMessage(message);
  }).catch(function (error) {
    page.notify('error', 'The browser did not remove the image: ' + error.message);
  });
}

async function load() {
  if (!page.keeping()) return;
  try {
    await scanRecords(openStore, 'images', record => { if (!wasRemoved(record)) page.admit(liveEntry(record)); });
    page.showNewest();
  } catch (error) { page.notify('error', 'The kept images did not load: ' + error.message); }
}

// Off empties the store at once; the images stay in the open tabs until a
// reload. On keeps what the tab shows now, which is the page's to walk and this
// module's to write, one image at a time.
// Before disabling persistence, every open tab materializes its own lazy records.
// Discovery/acknowledgement finishes before any shared store is cleared.
const forgetting = new Map();
const forgetPins = new Set();
function pinForget(token) { forgetPins.add(token); page.pinMedia(true); }
function unpinForget(token) { forgetPins.delete(token); page.pinMedia(Boolean(forgetPins.size)); }

const tabId = crypto.randomUUID();
const tabLockName = 'studio-gallery-tab-';
let releaseMembership;
let membership = null;
function registerTab() {
  if (navigator.locks) {
    membership = new Promise(resolve => {
      navigator.locks.request(tabLockName + tabId, async () => {
        resolve(); await new Promise(release => { releaseMembership = release; });
      });
    });
  } else {
    localStorage.setItem(tabLockName + tabId, 'open');
    membership = Promise.resolve();
  }
}
registerTab();
window.addEventListener('pagehide', () => {
  releaseMembership?.(); localStorage.removeItem(tabLockName + tabId);
});
window.addEventListener('pageshow', event => { if (event.persisted) registerTab(); });
async function openTabs() {
  await membership;
  if (navigator.locks) {
    const {held} = await navigator.locks.query();
    return held.filter(lock => lock.name.startsWith(tabLockName)).map(lock => lock.name.slice(tabLockName.length));
  }
  return Object.keys(localStorage).filter(key => key.startsWith(tabLockName)).map(key => key.slice(tabLockName.length));
}
let retainingPage;
function retainPage() {
  if (!retainingPage) retainingPage = Promise.resolve().then(() => page.retainMedia()).finally(() => { retainingPage = null; });
  return retainingPage;
}
async function retainImages(entries) {
  retainingImages = true;
  try {
    for (const entry of entries) if (!entry.src) await hydrate(entry);
    for (const entry of entries) { entry.stored = false; delete entry.loadMedia; }
  } finally { retainingImages = false; }
}
async function prepareForget() {
  const token = crypto.randomUUID(), peers = new Map((await openTabs()).filter(id => id !== tabId).map(id => [id, 'waiting']));
  forgetting.set(token, peers);
  pinForget(token);
  channel.postMessage({kind: 'prepare-forget', token});
  try {
    await retainPage();
    await new Promise(resolve => setTimeout(resolve, 250));
    const deadline = Date.now() + 15000;
    while (Array.from(peers.values()).some(value => value === 'waiting')) {
      if (Date.now() > deadline) throw new Error('Another Studio tab could not prepare its media. Try again when that tab is responsive.');
      const live = new Set(await openTabs());
      for (const id of peers.keys()) if (!live.has(id)) peers.delete(id);
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    if (Array.from(peers.values()).some(value => value !== 'ready')) throw new Error('Another Studio tab could not retain its media. Saved files were left intact.');
  } catch (error) {
    channel.postMessage({kind: 'forget-abort', token}); unpinForget(token); throw error;
  } finally { forgetting.delete(token); }
}
function announce(on) {
  channel.postMessage({ kind: 'keep', on: on });
  if (on) return;
  for (const token of forgetPins) unpinForget(token);
  Promise.all([
    inStore('readwrite', function (images) { return images.clear(); }),
    inVideoStore('readwrite', function (clips) { return clips.clear(); }),
  ]).catch(function (error) {
    page.notify('error', 'The kept media were not removed: ' + error.message);
  });
}

// A message from another tab. The one kind that carries an image is read back
// out of the store here, because the picture is too big to travel; the rest say
// what another tab did to the strip, and they are the page's to carry out.
channel.addEventListener('message', function (event) {
  const message = event.data;
  if (message.kind === 'forget-participant' || message.kind === 'forget-ready') {
    const peers = forgetting.get(message.token);
    if (peers && (message.kind === 'forget-ready' || !peers.has(message.tab))) peers.set(message.tab, message.state || 'waiting');
    return;
  }
  if (message.kind === 'forget-abort') { unpinForget(message.token); return; }
  if (message.kind === 'prepare-forget') {
    pinForget(message.token);
    channel.postMessage({kind: 'forget-participant', token: message.token, tab: tabId});
    retainPage().then(() => {
      channel.postMessage({kind: 'forget-ready', token: message.token, tab: tabId, state: 'ready'});
    }).catch(() => channel.postMessage({kind: 'forget-ready', token: message.token, tab: tabId, state: 'failed'}));
    return;
  }
  if (message.kind === 'remove' || message.kind === 'clear') markRemoved(message);
  if (message.kind === 'video-remove' || message.kind === 'video-clear') markVideoRemoved(message);
  if (message.kind !== 'add') {
    page.heard(message);
    if (message.kind === 'keep' && !message.on) for (const token of forgetPins) unpinForget(token);
    return;
  }
  if (!page.keeping()) return;
  inStore('readonly', function (images) { return images.get(message.id); }).then(function (record) {
    if (!record || wasRemoved(record)) return;
    page.admit(liveEntry(record));
    page.showNewest();
  }).catch(function (error) {
    page.notify('error', 'An image from another tab did not load: ' + error.message);
  });
});

// Best-effort storage can be evicted, and a saved video that vanishes is worse than the
// question. Ask once for durable storage; Chrome grants it by its own rules, and a refusal
// is worth one line rather than silence, because the next eviction is invisible.
let durable = null;
let durableAsked = false;

function askForDurableStorage() {
  if (durableAsked) return Promise.resolve(durable);
  durableAsked = true;
  if (!navigator.storage || typeof navigator.storage.persist !== 'function') {
    durable = false;
    return Promise.resolve(false);
  }
  return navigator.storage.persisted()
    .then(function (already) { return already || navigator.storage.persist(); })
    .then(function (granted) { durable = granted; return granted; })
    .catch(function () { durable = false; return false; });
}

const handle = {
  prepareForget, retainImages,
  hydrate: hydrate,
  videoRecord: id => inVideoStore('readonly', clips => clips.get(id)),
  keep: keep,
  keepVideo: keepVideo,
  keepVideoThumbnail: keepVideoThumbnail,
  forget: forget,
  load: load,
  loadVideos: loadVideos,
  removeVideo: removeVideo,
  clearVideos: clearVideos,
  announce: announce,
  blobOf: blobOf,
  fields: function () { return KEPT_FIELDS; },
  persisted: function () { return durable; },
  askForDurableStorage: askForDurableStorage,
  wasRemoved: wasRemoved,
  videoWasRemoved: videoWasRemoved,
};

document.dispatchEvent(new CustomEvent('store-ready', {
  detail: {
    configure: function (helpers) {
      page = helpers;
      return handle;
    },
  },
}));
