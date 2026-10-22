// The run: the poll, the post, the cancel, and everything the stage reads while
// one goes.
//
// Single images keep the form transport. Multiple images use one asynchronous
// prepared operation, after the same form hook has composed references, masks
// and prompts. Shared operations import each completed image as it arrives.
//
// htmx keeps `#progress`. The poll swaps that element's children and the
// children carry the next `hx-get`, so nothing here renders over it: the poller
// is planted into it and the module never swaps it.
//
// The page's own script is still a classic script, so it cannot import this
// module. The listener is registered while the markup is parsed and this fires
// while the module is evaluated: after the markup, before any interaction, so
// the handle is in place before the first run.

const page = {};

// The poller clocks itself off its own response, and stops when the server
// says nothing is running. That gap happens between two images of a batch, so
// every request the page sends plants a fresh poller.
const POLLER = '<div hx-get="/progress" hx-trigger="load"'
  + ' hx-target="#progress" hx-swap="innerHTML"></div>';

let progressState = null;
let sharedProgress = null;
let overallPercent = 0;
let observedOperationId = null;
let pace = null;            // how fast this run's steps arrive, for the time left
let cleared = null;         // what Run emptied, kept for Cancel
let cancelRestore = null;   // the copy Cancel asked for, applied once the run ends

// The run's own facts, apart from the form the next run will read.
let runKey = null;
let nativeOperationId = null;
let nativeRunning = false;
let nativeDraftId = null;
let preparedBatch = false;
let runPixels = 0;
let runEstimate = null;     // the estimate model of the mode in flight
let runStepSeconds = 0;     // the pre-run guess per step, until real steps arrive
let batchSource = null;     // the source of a one-image edit, for before and after
let batchSources = [];      // one source per reference, when the batch edits one image at a time
let runLook = null;         // the run's own prompt, look and negative, apart from what the model got
let runSources = [];        // per reference of the run: the frame it came from, or null for an upload
let runWords = [];          // per reference of a batch: the words that image was asked in its own right
let runPrompts = [];        // the same, composed with the box's lead and the Look, which is what the model is given

// When the run in flight started. The button it belongs to carries it, beside
// the run state it already publishes, so the page reads its own state from
// the DOM the way the checks do and nothing has to reach into a closure to
// put the page in a phase.
function startedAt() {
  return Number(page.el.go.dataset.started) || 0;
}

// The tab title shows the progress, so a run can be watched from another tab, and the
// page owns its text: the workspace decides the name in it. A run that ends in the
// background leaves "Done" until the tab is seen.

function snapshotInputs() {
  const params = {};
  page.currentMode().params.forEach(function (param) {
    const node = document.getElementById(param.id);
    if (node) params[param.id] = node.value;
  });
  return {
    view: page.view(),
    prompt: page.el.promptInput.value,
    negative: document.getElementById('negative').value,
    seed: document.getElementById('seed').value,
    count: page.el.countInput.value,
    params: params,
    look: JSON.parse(JSON.stringify(page.look())),
    references: page.references().slice(),
    region: page.region().snapshot(),
  };
}

// Everything the run consumed goes back to nothing: the words, the seed, the marks, the
// references, and the settings with them, because the form the run sent is emptied and the
// guide tells a reader that Run empties the form it sent. A step count picked for one job is
// typed again for the next one, which is the price of that rule and not a fault in it: the
// settings inside one batch are kept, since a chain link never clears the form.
//
// The defaults come from the mode, through the same call a mode switch makes,
// rather than from a value named here that could drift away from the backend.
function clearInputs() {
  const el = page.el;
  const region = page.region();
  el.promptInput.value = '';
  document.getElementById('negative').value = '';
  document.getElementById('seed').value = '';
  el.countInput.value = '1';
  page.setLook({});
  region.clearText();
  page.setReferences([]);
  region.putDown();
  page.currentMode().params.forEach(function (param) {
    const node = document.getElementById(param.id);
    if (node) delete node.dataset.applied;
  });
  page.applyParams();
  page.clampCount();
  page.growPrompt();
  page.pushLook();
  page.renderReferences();
  page.refreshForm();
}

function restoreInputs(snapshot) {
  if (!snapshot) return;
  const el = page.el;
  const region = page.region();
  // The stage the region was drawn on comes back first: a mark only survives on
  // the frame it was drawn on, so the frame has to be there before the strokes.
  page.setView(snapshot.view);
  el.promptInput.value = snapshot.prompt;
  document.getElementById('negative').value = snapshot.negative;
  document.getElementById('seed').value = snapshot.seed;
  el.countInput.value = snapshot.count;
  page.setLook(snapshot.look);
  // The rows read their text from here, so it goes back before they are built.
  region.setText(snapshot.region.text);
  page.setReferences(snapshot.references.slice());
  region.putDown();
  page.applyParams();  // this marks every input as applied, so the values below stick
  Object.keys(snapshot.params).forEach(function (id) {
    const node = document.getElementById(id);
    if (node) node.value = snapshot.params[id];
  });
  page.clampCount();
  page.growPrompt();
  page.pushLook();
  page.references().forEach(page.probeSize);
  // This arms the brush again, because a mark belongs to one reference on the
  // stage. Its stroke list starts empty, so the strokes go back after it.
  page.renderReferences();
  region.setStrokes(snapshot.region.strokes, snapshot.region);
  page.renderStrip();
  page.renderStage();
  page.refreshForm();
}

function startWork(element) {
  const fresh = element === page.el.form;
  if (fresh) nativeRunning = true;
  document.body.classList.add('busy');
  page.syncRunState();
  page.el.go.disabled = false;
  page.el.goSub.textContent = '';
  page.el.countToggle.disabled = true;
  page.el.progressSlot.innerHTML = POLLER;
  htmx.process(page.el.progressSlot);
  if (fresh) {
    page.el.go.dataset.started = String(Date.now());
    runKey = page.costKey();
    runPixels = page.targetPixels();
    runEstimate = page.estimateModel();
    page.setRunRatio(page.targetRatio());
    runStepSeconds = page.stepSeconds();
    page.setView('progress');
    progressState = null;
    sharedProgress = null;
    overallPercent = 0;
    pace = null;
    page.renderStrip();
    page.renderStage();
  }
}

// The sources are blobs, and only the entries that arrive hold them. A run that made no image,
// or fewer than it promised, leaves the rest live for the tab's life unless they go back here.
function revokeUnclaimed() {
  const held = new Set();
  page.gallery().forEach(function (entry) {
    if (entry.before) held.add(entry.before);
    (entry.sources || []).forEach(function (source) { if (source) held.add(source); });
  });
  [batchSource].concat(batchSources).forEach(function (url) {
    if (url && !held.has(url)) URL.revokeObjectURL(url);
  });
  batchSource = null;
  batchSources = [];
}

function stopWork() {
  nativeRunning = false;
  if (!page.busy()) return;
  document.title = (document.hidden ? '(Done) ' : '') + page.workspaceTitle();
  document.body.classList.remove('busy', 'stopping');
  page.syncRunState();
  page.el.progressSlot.innerHTML = '';
  progressState = null;
  page.el.countToggle.disabled = false;
  const gallery = page.gallery();
  if (page.view() === 'progress') page.setView(gallery.length ? gallery[0].id : null);
  page.renderStrip();
  page.renderStage();
  page.renderRunButton();
  // A cancelled run puts back what Run emptied, after the stage has settled.
  if (cancelRestore) {
    const snapshot = cancelRestore;
    cancelRestore = null;
    restoreInputs(snapshot);
  }
}

function armCancelRestore() {
  if (!cleared) return;
  cancelRestore = cleared;
  cleared = null;
}

function requestCancel() {
  if (document.body.classList.contains('stopping')) return;
  document.body.classList.add('stopping');
  page.syncRunState();
  page.el.go.disabled = true;
  renderProgress();
  htmx.ajax('POST', '/cancel', { swap: 'none' });
  // The form comes back once the run has really stopped, not now: the progress
  // card lives on the stage, and moving the stage mid-run would take it away
  // from the poller that is still streaming into it.
  armCancelRestore();
}

// Expand the UI's per-reference editing into ordinary one-image API items.
// One seed sequence spans the whole batch, just as it did in the form chain.
function batchPayload(parameters) {
  const body = Object.assign({}, parameters);
  const references = JSON.parse(body.references || '[]');
  const each = batchSources.length > 0 && body.mask !== '1';
  const count = Number(body.count);
  const rawSeed = String(body.seed || '').trim();
  if (rawSeed && !/^\d+$/.test(rawSeed)) throw new Error('seed must be a whole number');
  const seed = rawSeed ? BigInt(rawSeed)
    : BigInt(crypto.getRandomValues(new Uint32Array(1))[0] % 1000000001);
  delete body.count;
  delete body.each_reference;
  delete body.references;
  delete body.seed;
  const items = Array.from({length: count}, function (_, index) {
    const place = each ? index % references.length : -1;
    return {prompt: place >= 0 && runPrompts.length ? runPrompts[place] : body.prompt,
      seed: String(seed + BigInt(index)), references: each ? [references[place]] : references};
  });
  return {...body, kind: 'image', backend: page.backendId, precision: page.precision, items: items};
}

async function submitBatch(parameters, headers) {
  try {
    const answer = await fetch('/image/operations', {method: 'POST',
      headers: {...headers, 'Content-Type': 'application/json'}, body: JSON.stringify(batchPayload(parameters))});
    const operation = await answer.json();
    if (!answer.ok) throw new Error(operation.error || 'The batch could not be started.');
    nativeOperationId = operation.id;
  } catch (error) {
    armCancelRestore();
    revokeUnclaimed();
    stopWork();
    page.notify('error', error.message);
  }
}

// Time left comes from when steps arrive, never from the clock between them:
// dividing by "now" made the number climb during every step and drop at the
// next. The rate carries across the images of a batch. Until two steps have
// arrived, the pre-run guess stands in. An image also needs time after its
// last step, to decode and reach the page. That tail is measured on each
// finished image; before the first, the backend's overhead stands in.
function trackPace() {
  const state = progressState;
  if (!state) return;
  const now = Date.now();
  if (!pace) pace = { label: null, stepTime: 0, stepsTimed: 0 };
  if (state.label !== pace.label) {
    pace.label = state.label;
    pace.lastStep = 0;
    pace.lastStepAt = 0;
  }
  if (state.stage !== 'running' || state.step <= pace.lastStep) return;
  if (pace.lastStepAt) {
    pace.stepTime += (now - pace.lastStepAt) / 1000;
    pace.stepsTimed += state.step - pace.lastStep;
  }
  pace.lastStep = state.step;
  pace.lastStepAt = now;
  if (pace.stepsTimed >= 2 && runEstimate) {
    page.learnedCost[runKey] = paceRate() / Math.pow(runPixels / 1e6, runEstimate.exponent);
  }
}

function paceRate() {
  return pace && pace.stepsTimed >= 2 ? pace.stepTime / pace.stepsTimed : runStepSeconds;
}

function progressNow() {
  // The legacy /progress poll is per image; shared operation counters cover the
  // complete batch. Never alternate those two scales on the same preview.
  const state = sharedProgress || progressState;
  const running = Boolean(state && state.stage === 'running' && state.total);
  const batch = !sharedProgress && (state?.label || '').match(/(\d+) of (\d+)/);
  const fraction = !running ? 0 : batch
    ? (Number(batch[1]) - 1 + state.step / state.total) / Number(batch[2])
    : state.step / state.total;
  overallPercent = Math.max(overallPercent, Math.min(99, Math.floor(fraction * 100)));
  return { running: running || overallPercent > 0, percent: overallPercent };
}

function renderProgress() {
  if (!page.busy()) return;
  const now = progressNow();
  document.title = (now.running ? '(' + now.percent + '%) ' : '') + page.workspaceTitle();
  page.progressCard().paintAll(now.running, now.percent);
}

function sideChannel(event) {
  const config = event.detail.requestConfig || event.detail.pathInfo || {};
  const path = config.path || config.requestPath || '';
  return path === '/progress' || path === '/cancel';
}

// Each image is shown by a blob URL. As a data URL, every img that showed it
// made the browser parse megabytes of base64 text again. The base64 stays on
// the entry for the moment the image goes back to the server as a reference.
function blobUrl(dataUrl) {
  const comma = dataUrl.indexOf(',');
  const binary = atob(dataUrl.slice(comma + 1));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index++) bytes[index] = binary.charCodeAt(index);
  const type = dataUrl.slice(5, dataUrl.indexOf(';'));
  return URL.createObjectURL(new Blob([bytes], { type: type }));
}

// A batch of edits shares one source, so it is freed with the last of them.
function release(entry) {
  const gallery = page.gallery();
  URL.revokeObjectURL(entry.src);
  const shared = entry.before === batchSource || gallery.some(function (other) {
    return other.before === entry.before;
  });
  if (entry.before && !shared) URL.revokeObjectURL(entry.before);
}

// What the wipe compares this result against: the reference it edited, when the batch walked
// them one at a time, or the one source of a single-image edit, or nothing.
function beforeOf(data) {
  const place = Number(data.reference);
  if (place >= 0) return batchSources[place] || null;
  return batchSource;
}

function harvest() {
  const incoming = page.el.incoming;
  incoming.querySelectorAll('.item').forEach(function (node) {
    const data = node.dataset;
    const source = node.querySelector('img').src;
    const id = data.operationStarted ? Math.floor(Number(data.operationStarted) * 1000) * 16 + Math.max(0, parseInt(data.position, 10) - 1) : page.takeFrameId();
    const entry = {
      id: id, number: data.operationStarted ? page.takeFrameId(id) : id, nativeMetadata: true,
      operationId: data.operationId || '', src: blobUrl(source), b64: source.split(',')[1], seed: data.seed,
      width: data.width, height: data.height, steps: data.steps, elapsed: data.elapsed,
      position: data.position, mode: data.mode, prompt: data.prompt, look: null, negative: '',
      // A delayed response must not restore an image completed before Clear all.
      at: Number(data.operationCompleted) * 1000 || Date.now(),
      // Which model made this one, taken now because the page knows it now. A
      // switch reloads the page but keeps the strip, so without this every frame
      // would wear whichever model was selected last. `edgeName` is the active
      // model's, in the form the edge draws, and the page hands it to this module
      // on the run handle, beside `takeFrameId`.
      backend: page.edgeName,
      // The model's id beside its name, because a download names a file with it and
      // a file name cannot carry the capitals and the spaces the edge draws.
      backendId: page.backendId,
      precision: page.precision,
      // A batch of one result each edited one picture, so it says so. Composed, every
      // reference really did go into it, which is what all of them means.
      sources: Number(data.reference) >= 0 ? [runSources[Number(data.reference)] || ''] : runSources,
      before: data.mode === 'edit' ? beforeOf(data) : null,
    };
    if (runLook && data.prompt === runLook.sent) {
      // The user's own words, so the card does not read back the sentence the
      // page composed around the region rows. A run that is rows only has no words
      // of its own, and there the composed sentence is the only record of what the
      // run asked for, so it stands in, written for a reader.
      entry.prompt = runLook.prompt || runLook.reader || data.prompt;
      // The user's own words, kept apart so Reuse prompt has them and not the
      // sentence the page composed. A run that is rows only has none, and an empty
      // box is the honest thing to hand back. A rewrite puts a model's paragraph in
      // the box, so what this holds is the text that was in the box before it.
      entry.typed = runLook.typed || runLook.prompt;
      entry.negative = runLook.negative;
      if (runLook.labels.length) entry.look = runLook;
    }
    // A batch wrote each image its own instruction, so the card of that image reads back the
    // whole instruction it was given, and Reuse prompt hands back the words that image was
    // asked in its own right. The match above cannot find them: they are not the run's single
    // prompt, they are that image's own.
    const place = Number(data.reference);
    if (place >= 0 && runWords.length > place) {
      entry.prompt = runPrompts[place];
      entry.typed = runWords[place];
      entry.negative = runLook ? runLook.negative : '';
      if (runLook && runLook.labels.length) entry.look = runLook;
    }
    if (entry.operationId) nativeOperationId = entry.operationId;
    if (entry.operationId && !incoming.querySelector('.chain')) document.dispatchEvent(new CustomEvent('operation-imported', {detail: entry.operationId}));
    const admitted = page.admit(entry);
    if (!admitted) {
      node.remove();
      return;
    }
    page.keep(admitted);
    page.setArrived(entry.id);
    if (page.view() !== 'progress') page.setView(entry.id);
    node.remove();
  });
  const terminalNotice = incoming.querySelector(':scope > .err, :scope > .hint');
  if (terminalNotice && nativeOperationId) {
    document.dispatchEvent(new CustomEvent('operation-imported', {detail: nativeOperationId}));
  }
  incoming.querySelectorAll(':scope > .err, :scope > .hint').forEach(function (node) {
    page.notify(node.classList.contains('err') ? 'error' : 'info', node.textContent);
    node.remove();
  });
  // The last image of a batch arrives by a chain placeholder, and removing it
  // here detaches the node htmx then fires afterSettle on, so that event never
  // reaches the body. The run ends here instead, once no link is left.
  // stopWork renders, and a second render would restart the arrival fade.
  if (page.busy() && !incoming.querySelector('.chain')) return stopWork();
  page.renderStrip();
  page.renderStage();
}

const handle = {
  prepareCancel: function (operation) {
    if (!nativeRunning || !nativeDraftId || operation.settings?.draft_id !== nativeDraftId) return false;
    armCancelRestore();
    return true;
  },
  finishOperation: function (operation) {
    if (!preparedBatch || !nativeRunning || operation.settings?.draft_id !== nativeDraftId) return;
    if (!['succeeded', 'failed', 'cancelled'].includes(operation.status)) return;
    if (operation.status !== 'succeeded') armCancelRestore();
    revokeUnclaimed();
    stopWork();
  },
  decorateImage: function (operation, image, entry, position) {
    if (!preparedBatch || operation.settings?.draft_id !== nativeDraftId) return;
    const place = batchSources.length ? position % batchSources.length : -1;
    entry.nativeMetadata = true;
    entry.operationId = operation.id.split(':')[0];
    entry.position = position + 1;
    entry.sources = place >= 0 ? [runSources[place] || ''] : runSources;
    entry.before = image.mode === 'edit' ? (place >= 0 ? batchSources[place] : batchSource) : null;
    if (runLook && image.prompt === runLook.sent) {
      entry.prompt = runLook.prompt || runLook.reader || image.prompt;
      entry.typed = runLook.typed || runLook.prompt;
      entry.negative = runLook.negative;
      if (runLook.labels.length) entry.look = runLook;
    }
    if (place >= 0 && runWords.length > place) {
      entry.prompt = runPrompts[place];
      entry.typed = runWords[place];
      entry.negative = runLook.negative;
      if (runLook.labels.length) entry.look = runLook;
    }
  },
  updateBackend: function (backend) {
    page.backendId = backend.id;
    page.edgeName = backend.name.toUpperCase().replace(/-/g, ' ');
    page.precision = backend.badge;
  },
  snapshotInputs: snapshotInputs,
  restoreInputs: restoreInputs,
  renderProgress: renderProgress,
  release: release,
  observeOperation: function (operation) {
    if (operation?.kind === 'image') {
      if (observedOperationId !== operation.id) overallPercent = 0;
      if (observedOperationId !== operation.id && !document.body.classList.contains('busy')) {
        page.el.go.dataset.started = String(operation.started_at * 1000);
        const settings = operation.settings || {};
        page.setRunRatio((operation.width || settings.width || 1) / (operation.height || settings.height || 1));
        page.setView('progress');
      }
      observedOperationId = operation.id;
      sharedProgress = operation.progress || null;
      renderProgress();
    } else if (observedOperationId) {
      observedOperationId = null;
      sharedProgress = null;
      if (!document.body.classList.contains('busy')) {
        progressState = null;
        document.title = page.workspaceTitle();
        if (page.view() === 'progress') page.setView(page.gallery()[0]?.id ?? null);
      }
    }
  },
  progressState: function () { return sharedProgress || progressState; },
};

document.dispatchEvent(new CustomEvent('run-ready', {
  detail: {
    configure: function (helpers) {
      Object.assign(page, helpers);
      listen();
      return handle;
    },
  },
}));

function listen() {

  // Answers arrive by several routes: the form's own request, and each chain
  // placeholder replacing itself. Watching the container catches all of them.
  new MutationObserver(function (records) {
    if (records.some(function (record) { return record.addedNodes.length; })) harvest();
  }).observe(page.el.incoming, { childList: true, subtree: true });

  // While a run goes, the run button is Cancel. A click in the first half
  // second is the second half of a double click on Generate, so it waits.
  // Enter in a text field also clicks this button (an implicit submit), with
  // no click count and the focus left in the field; that is not a cancel.
  page.el.go.addEventListener('click', function (event) {
    if (!page.busy()) return;
    event.preventDefault();
    const implicit = event.detail === 0 && document.activeElement !== page.el.go;
    if (implicit || Date.now() - startedAt() < 500) return;
    requestCancel();
  });

  // The tab title shows the progress, so a run can be watched from another tab.
  // A run that ends in the background leaves "Done" until the tab is seen.
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && !page.busy()) page.setTitle('');
  });

  new MutationObserver(function () {
    const node = page.el.progressSlot.querySelector('.progress-state');
    progressState = node ? {
      stage: node.dataset.stage, step: Number(node.dataset.step), total: Number(node.dataset.total),
      label: node.dataset.label, kind: node.dataset.kind, stopping: node.dataset.stopping === '1',
    } : null;
    trackPace();
    renderProgress();
  }).observe(page.el.progressSlot, { childList: true, subtree: true });

  // The references are an array, not a form field, so they are attached here.
  // Only the form itself carries them: a chain request already has a token.
  document.body.addEventListener('htmx:configRequest', function (event) {
    const elt = event.detail.elt;
    const chain = elt.classList.contains('chain');
    if (elt !== page.el.form && !chain) return;
    // A link of the batch asks for one image, and the index the placeholder publishes is
    // which one. A batch writes each image its own instruction, so that request carries the
    // words of that image and not the run's single prompt. The index counts the requests and
    // not the images: a count above one asks for several results from every image, and the
    // server cycles the references the same way, so the place is taken the same way here.
    if (chain) {
      const index = Number(elt.dataset.index) - 1;
      const place = runPrompts.length ? index % runPrompts.length : -1;
      if (place >= 0 && runPrompts.length > place) event.detail.parameters.prompt = runPrompts[place];
      return;
    }
    nativeOperationId = null;
    preparedBatch = false;
    nativeDraftId = event.detail.parameters.draft_id || null;
    const references = page.references();
    const region = page.region();
    // Only a one-image edit changes that image in place. An edit from several
    // images composes them, so no single source lines up with the result and
    // a wipe between them would mislead.
    batchSource = page.editing() && references.length === 1
      ? blobUrl('data:image/png;base64,' + references[0].b64) : null;
    // One result per reference edits each picture on its own, so every result has a source to
    // wipe against. Composed, no single one lines up, which is what batchSource being null says.
    const chosen = event.detail.elt.querySelector('input[name=each_reference]:checked');
    batchSources = page.editing() && chosen && chosen.value === '1'
      ? references.map(function (reference) { return blobUrl('data:image/png;base64,' + reference.b64); })
      : [];
    runSources = references.map(function (reference) { return reference.source; });
    const own = page.el.promptInput.value.trim();
    runLook = {
      prompt: own, typed: page.rewrittenFrom() || own, sent: page.withLook(own),
      adds: page.lookText(), labels: page.lookLabels(),
      picks: JSON.parse(JSON.stringify(page.look())), negative: page.typedNegative(),
    };
    // One instruction for each image of a batch, or nothing when the run carries a single
    // one. Each image's own row joins the box's words, which lead every image, and the Look is
    // the page's own sentence added last, once.
    const plan = page.eachPlan();
    runWords = plan.map(function (one) { return one.own; });
    runPrompts = plan.map(function (one) { return page.withLook(one.asked); });
    event.detail.parameters.prompt = runPrompts.length ? runPrompts[0] : runLook.sent;
    // What the run is charged for. With one result per reference the count is what each
    // reference gets, so the batch costs that many times the references, and the server's bound
    // is on the images it makes. Posting the product keeps the two the same number.
    event.detail.parameters.count = String(page.imageCount());
    if (page.paramSpec('negative')) event.detail.parameters.negative = page.negativeText();
    // A marked region rides as the last image, and the prompt names that image,
    // so the model is told which one carries the mask.
    const mask = region.mask();
    event.detail.parameters.mask = mask ? '1' : '';
    if (mask) {
      // Measured 2026-09-26: one clause per region, each naming the colour the mask
      // carries, then one line pinning the rest of the picture.
      event.detail.parameters.prompt = region.composed();
      // The card's copy, taken while the rows are still here to read.
      runLook.reader = region.composed(true);
    }
    // `sent` is what the model got, so it is recorded after every override. A
    // masked run sends the composed sentence, and the match in harvest() looked
    // for the pre-composition prompt, so the card lost the user's own words.
    runLook.sent = event.detail.parameters.prompt;
    event.detail.parameters.references = JSON.stringify(references.map(function (r) {
      return r.b64;
    }).concat(mask ? [mask.split(',')[1]] : []));
  });
  document.body.addEventListener('htmx:beforeRequest', function (event) {
    if (sideChannel(event)) return;
    const fresh = event.detail.elt === page.el.form;
    if (fresh) {
      // A failure's toast stays until it is dismissed: a run starting is not a dismissal.
      // The short notices clear themselves after a few seconds.
      // The copy comes first: startWork moves the stage to the progress card, and
      // the frame the region was drawn on is part of what Cancel has to put back.
      cleared = snapshotInputs();
    }
    startWork(event.detail.elt);
    // The form empties after startWork, which reads it for the run's cost, shape
    // and step time. A chain request carries its own token and never reads the
    // form, so only the form's own request clears.
    if (fresh && Number(event.detail.requestConfig.parameters.count) > 1) {
      event.preventDefault();
      preparedBatch = true;
      // Capture the composed parameters before clearing the inputs. The API
      // validates and prepares every item once, before any image is rendered.
      const parameters = Object.assign({}, event.detail.requestConfig.parameters);
      clearInputs();
      submitBatch(parameters, event.detail.requestConfig.headers);
    } else if (fresh) clearInputs();
  });
  document.body.addEventListener('htmx:afterSettle', function (event) {
    // A /progress response settles once a second. It is not the end of the run,
    // and treating it as one used to clear the busy state mid-generation.
    if (sideChannel(event)) return;
    if (!document.querySelector('.chain')) {
    revokeUnclaimed();
    stopWork();
  }
  });
  document.body.addEventListener('htmx:responseError', stopWork);
  document.body.addEventListener('htmx:sendError', function () {
    stopWork();
    page.notify('error', 'The server did not answer. Check that the studio server is still running.');
  });

  // A run, or images kept only in this tab, would be lost to a reload or a close.
  // Browsers show their own fixed text here; the page cannot set it.
  window.addEventListener('beforeunload', function (event) {
    if (!page.busy() && (page.keeping() || !page.gallery().length)) return;
    event.preventDefault();
    event.returnValue = '';
  });
}
