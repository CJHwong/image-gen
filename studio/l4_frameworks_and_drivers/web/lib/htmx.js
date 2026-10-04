// The run: the poll, the post, the cancel, and everything the stage reads while
// one goes.
//
// The run stays an htmx post. The region composition depends on the
// `event.detail.parameters` hook, and moving it to `fetch` would move the mask
// contract as well. So the poller clocks itself off its own response, the form's
// own request is what clears the form, and this module is where those listeners
// live.
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
let pace = null;            // how fast this run's steps arrive, for the time left
let cleared = null;         // what Run emptied, kept for Cancel
let cancelRestore = null;   // the copy Cancel asked for, applied once the run ends

// The run's own facts, apart from the form the next run will read.
let runKey = null;
let runPixels = 0;
let runEstimate = null;     // the estimate model of the mode in flight
let runStepSeconds = 0;     // the pre-run guess per step, until real steps arrive
let batchSource = null;     // the source of a one-image edit, for before and after
let runLook = null;         // the run's own prompt, look and negative, apart from what the model got
let runSources = [];        // per reference of the run: the frame it came from, or null for an upload

// When the run in flight started. The button it belongs to carries it, beside
// the run state it already publishes, so the page reads its own state from
// the DOM the way the checks do and nothing has to reach into a closure to
// put the page in a phase.
function startedAt() {
  return Number(page.el.go.dataset.started) || 0;
}

// The tab title shows the progress, so a run can be watched from another tab.
// A run that ends in the background leaves "Done" until the tab is seen.
const BASE_TITLE = document.title;

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
  region.setStrokes(snapshot.region.strokes);
  page.renderStrip();
  page.renderStage();
  page.refreshForm();
}

function startWork(element) {
  const fresh = element === page.el.form;
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
    runEstimate = page.currentMode().estimate;
    page.setRunRatio(page.targetRatio());
    runStepSeconds = page.stepSeconds();
    page.setView('progress');
    progressState = null;
    pace = null;
    page.renderStrip();
    page.renderStage();
  }
}

function stopWork() {
  if (!page.busy()) return;
  document.title = (document.hidden ? '(Done) ' : '') + BASE_TITLE;
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
  cancelRestore = cleared;
  cleared = null;
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
  if (!pace) pace = { label: null, stepTime: 0, stepsTimed: 0, tail: null };
  if (state.label !== pace.label) {
    if (pace.label !== null && pace.lastStepAt) pace.tail = (now - pace.lastStepAt) / 1000;
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

function timeLeft() {
  const state = progressState;
  const perStep = paceRate();
  if (!state || !perStep) return '';
  const tail = pace && pace.tail !== null ? pace.tail : (runEstimate ? runEstimate.overhead : 0);
  const batch = (state.label || '').match(/(\d+) of (\d+)/);
  const imagesAfter = batch ? Number(batch[2]) - Number(batch[1]) : 0;
  const step = state.stage === 'running' ? state.step : 0;
  const sinceStep = pace && pace.lastStepAt ? (Date.now() - pace.lastStepAt) / 1000 : 0;
  const thisImage = Math.max(0, perStep * (state.total - step) + tail - sinceStep);
  const seconds = thisImage + imagesAfter * (perStep * state.total + tail);
  return seconds < 3 ? 'Almost done' : 'About ' + page.spell(seconds) + ' left';
}

function progressNow() {
  const state = progressState;
  const running = Boolean(state && state.stage === 'running' && state.total);
  return { running: running, percent: running ? Math.round(state.step / state.total * 100) : 0 };
}

function renderProgress() {
  if (!page.busy()) return;
  const state = progressState;
  const stopping = document.body.classList.contains('stopping') || (state && state.stopping);
  const now = progressNow();
  const running = now.running;
  let stepText = 'Starting';
  // Before step 0 the backend sets up its model: a rebuild, a switch between
  // generate and edit, or the edit engine's first load. Step 0 is its notice
  // that the engine started, which first encodes the prompt and images. The
  // engine may then run fewer steps (a starting image skips part of the
  // schedule), so the count shows from the first real step.
  if (state && state.stage === 'preparing') stepText = 'Loading the model';
  if (running && state.stage === 'running' && state.step === 0) {
    stepText = runSources.length ? 'Reading the prompt and images' : 'Reading the prompt';
  }
  if (running && state.step > 0) stepText = 'Step ' + state.step + ' of ' + state.total;
  if (stopping) {
    // An engine inside this process can only stop where it looks, which is a step, and
    // before the first step there is nothing to look at. So the label says when, not
    // that it has happened. A child engine is killed outright and this flashes past.
    stepText = state && state.step > 0
      ? 'Stopping at the end of this step' : 'Stopping when the first step arrives';
  }

  // Before the first step the estimate is the only number the page has, and it does
  // not move: the same sentence, redrawn every second, is what a frozen run looks
  // like. The elapsed time does move, so the reading phase says how long it has been
  // reading and a slow engine is visibly still working.
  const reading = running && state && state.step === 0;
  const soFar = startedAt() ? page.spell(Math.max(0, (Date.now() - startedAt()) / 1000)) + ' so far' : '';
  const left = running && !stopping ? (reading ? soFar : timeLeft()) : '';
  // While stopping, the phase text says when the stop lands. It used to be a bare
  // "Stopping", and the sentence built for this case was written and never shown.
  page.el.statusText.textContent = stopping ? stepText : running
    ? [stepText, state.label ? 'image ' + state.label : '',
      left.charAt(0).toLowerCase() + left.slice(1)].filter(Boolean).join(', ')
    : stepText;
  document.title = (running ? '(' + now.percent + '%) ' : '') + BASE_TITLE;
  page.progressCard().paintAll(running, now.percent);
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

function harvest() {
  const incoming = page.el.incoming;
  incoming.querySelectorAll('.item').forEach(function (node) {
    const data = node.dataset;
    const source = node.querySelector('img').src;
    const entry = {
      id: page.takeFrameId(), src: blobUrl(source), b64: source.split(',')[1], seed: data.seed,
      width: data.width, height: data.height, steps: data.steps, elapsed: data.elapsed,
      position: data.position, mode: data.mode, prompt: data.prompt, look: null, negative: '',
      sources: runSources,
      before: data.mode === 'edit' ? batchSource : null,
    };
    if (runLook && data.prompt === runLook.sent) {
      // The user's own words, so the card does not read back the sentence the
      // page composed around the region rows. A run that is rows only has no words
      // of its own, and there the composed sentence is the only record of what the
      // run asked for, so it stands in, written for a reader.
      entry.prompt = runLook.prompt || runLook.reader || data.prompt;
      // The user's own words, kept apart so Reuse prompt has them and not the
      // sentence the page composed. A run that is rows only has none, and an empty
      // box is the honest thing to hand back.
      entry.typed = runLook.typed || runLook.prompt;
      entry.negative = runLook.negative;
      if (runLook.labels.length) entry.look = runLook;
    }
    page.gallery().unshift(entry);
    page.keep(entry);
    page.setArrived(entry.id);
    if (page.view() !== 'progress') page.setView(entry.id);
    node.remove();
  });
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
  renderProgress: renderProgress,
  release: release,
  progressState: function () { return progressState; },
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
    if (!document.hidden && !page.busy()) document.title = BASE_TITLE;
  });

  new MutationObserver(function () {
    const node = page.el.progressSlot.querySelector('.progress-state');
    progressState = node ? {
      stage: node.dataset.stage, step: Number(node.dataset.step), total: Number(node.dataset.total),
      label: node.dataset.label, stopping: node.dataset.stopping === '1',
    } : null;
    trackPace();
    renderProgress();
  }).observe(page.el.progressSlot, { childList: true, subtree: true });

  // The references are an array, not a form field, so they are attached here.
  // Only the form itself carries them: a chain request already has a token.
  document.body.addEventListener('htmx:configRequest', function (event) {
    if (event.detail.elt !== page.el.form) return;
    const references = page.references();
    const region = page.region();
    // Only a one-image edit changes that image in place. An edit from several
    // images composes them, so no single source lines up with the result and
    // a wipe between them would mislead.
    batchSource = page.editing() && references.length === 1
      ? blobUrl('data:image/png;base64,' + references[0].b64) : null;
    runSources = references.map(function (reference) { return reference.source; });
    const own = page.el.promptInput.value.trim();
    runLook = {
      prompt: own, typed: page.rewrittenFrom() || own, sent: page.withLook(own),
      adds: page.lookText(), labels: page.lookLabels(),
      picks: JSON.parse(JSON.stringify(page.look())), negative: page.typedNegative(),
    };
    event.detail.parameters.prompt = runLook.sent;
    if (page.paramSpec('negative')) event.detail.parameters.negative = page.negativeText();
    // A marked region rides as the last image, and the prompt names that image,
    // so the model is told which one carries the mask.
    const mask = region.mask();
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
      page.clearToasts();
      // The copy comes first: startWork moves the stage to the progress card, and
      // the frame the region was drawn on is part of what Cancel has to put back.
      cleared = snapshotInputs();
    }
    startWork(event.detail.elt);
    // The form empties after startWork, which reads it for the run's cost, shape
    // and step time. A chain request carries its own token and never reads the
    // form, so only the form's own request clears.
    if (fresh) clearInputs();
  });
  document.body.addEventListener('htmx:afterSettle', function (event) {
    // A /progress response settles once a second. It is not the end of the run,
    // and treating it as one used to clear the busy state mid-generation.
    if (sideChannel(event)) return;
    if (!document.querySelector('.chain')) stopWork();
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
