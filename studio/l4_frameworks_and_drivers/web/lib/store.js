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
const KEPT_FIELDS = ['id', 'seed', 'width', 'height', 'steps', 'elapsed', 'position', 'mode', 'prompt',
  'typed', 'look', 'negative', 'sources'];

const channel = new BroadcastChannel('studio-gallery');

// The page's own, handed over on the door.
let page = null;

// The handle is opened once and kept: a browser that refuses one is only
// reachable at that first moment.
let database = null;

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
  if (!page.keeping()) return;
  Promise.all([blobOf(entry.src), entry.before ? blobOf(entry.before) : null]).then(function ([png, before]) {
    const record = { png: png, before: before };
    KEPT_FIELDS.forEach(function (field) { record[field] = entry[field]; });
    return inStore('readwrite', function (images) { return images.add(record); });
  }).then(function () {
    channel.postMessage({ kind: 'add', id: entry.id });
  }).catch(function (error) {
    page.notify('error', 'The browser did not keep image ' + page.frameNumber(entry.id) + ': ' + error.message
      + ' It stays in this tab until a reload. Download it to keep it.');
  });
}

// Delete from the store, then tell the other tabs. The work is the caller's,
// because what goes is the caller's to name. With keeping off there is nothing
// stored, and each tab's strip is its own.
function forget(work, message) {
  if (!page.keeping()) return;
  inStore('readwrite', work).then(function () {
    channel.postMessage(message);
  }).catch(function (error) {
    page.notify('error', 'The browser did not remove the image: ' + error.message);
  });
}

function load() {
  if (!page.keeping()) return;
  inStore('readonly', function (images) { return images.getAll(); }).then(function (records) {
    for (const record of records) page.admit(liveEntry(record));
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
  inStore('readwrite', function (images) { images.clear(); }).catch(function (error) {
    page.notify('error', 'The kept images were not removed: ' + error.message);
  });
}

// A message from another tab. The one kind that carries an image is read back
// out of the store here, because the picture is too big to travel; the rest say
// what another tab did to the strip, and they are the page's to carry out.
channel.addEventListener('message', function (event) {
  const message = event.data;
  if (message.kind !== 'add') return page.heard(message);
  if (!page.keeping()) return;
  inStore('readonly', function (images) { return images.get(message.id); }).then(function (record) {
    if (!record) return;
    page.admit(liveEntry(record));
    page.showNewest();
  }).catch(function (error) {
    page.notify('error', 'An image from another tab did not load: ' + error.message);
  });
});

const handle = {
  keep: keep,
  forget: forget,
  load: load,
  announce: announce,
  blobOf: blobOf,
  fields: function () { return KEPT_FIELDS; },
};

document.dispatchEvent(new CustomEvent('store-ready', {
  detail: {
    configure: function (helpers) {
      page = helpers;
      return handle;
    },
  },
}));
