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
function liveEntry(record) {
  const entry = {
    src: URL.createObjectURL(record.png),
    before: record.before && URL.createObjectURL(record.before),
  };
  KEPT_FIELDS.forEach(function (field) { entry[field] = record[field]; });
  return entry;
}

function keep(entry) {
  if (!page.keeping() || wasRemoved(entry)) return Promise.resolve();
  return Promise.all([blobOf(entry.src), entry.before ? blobOf(entry.before) : null]).then(function ([png, before]) {
    const record = { png: png, before: before };
    KEPT_FIELDS.forEach(function (field) { record[field] = entry[field]; });
    return inStore('readwrite', function (images) {
      if (!page.keeping() || wasRemoved(entry)) return;
      if (!entry.operationId) return images.add(record);
      return keepPreferred(images, record, wasRemoved);
    });
  }).then(function () {
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

function loadVideos() {
  if (!page.keeping()) return Promise.resolve([]);
  return inVideoStore('readonly', function (clips) { return clips.getAll(); }).then(function (records) {
    return records.filter(record => !videoWasRemoved(record)).sort(function (first, second) { return first.createdAt - second.createdAt; });
  }).catch(function (error) {
    page.notify('error', 'The saved videos did not load: ' + error.message);
    return [];
  });
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

function load() {
  if (!page.keeping()) return;
  return inStore('readonly', function (images) { return images.getAll(); }).then(function (records) {
    for (const record of records) if (!wasRemoved(record)) page.admit(liveEntry(record));
    page.showNewest();
  }).catch(function (error) {
    page.notify('error', 'The kept images did not load: ' + error.message);
  });
}

// Off empties the store at once; the images stay in the open tabs until a
// reload. On keeps what the tab shows now, which is the page's to walk and this
// module's to write, one image at a time.
function announce(on) {
  channel.postMessage({ kind: 'keep', on: on });
  if (on) return;
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
  if (message.kind === 'remove' || message.kind === 'clear') markRemoved(message);
  if (message.kind === 'video-remove' || message.kind === 'video-clear') markVideoRemoved(message);
  if (message.kind !== 'add') return page.heard(message);
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
