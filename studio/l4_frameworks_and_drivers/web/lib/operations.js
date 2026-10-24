import {screenAwake} from './screen-awake.js';
const awake = screenAwake();
// Every tab reads the same operation. Results outlive the request that made them.
const page = {};
const imported = new Set();
const owners = new Set();
const observed = new Set();
const batchItems = new Set();
const batchCounts = new Map();
const openedAt = performance.timeOrigin / 1000;
try {
  JSON.parse(sessionStorage.getItem('studio-seen-operations') || '[]').forEach(id => imported.add(id));
  JSON.parse(sessionStorage.getItem('studio-operation-owners') || '[]').forEach(id => owners.add(id));
  JSON.parse(sessionStorage.getItem('studio-observed-operations') || '[]').forEach(id => observed.add(id));
} catch (error) {
  console.warn('Completed operations were not read:', error);
}
function remember(id) {
  if (!id) return;
  imported.add(id);
  try {
    sessionStorage.setItem('studio-seen-operations', JSON.stringify(Array.from(imported).slice(-256)));
  } catch (error) {
    console.warn('Completed operations were not saved:', error);
  }
}
document.addEventListener('operation-imported', function (event) { remember(event.detail); });
let active = null;
let polling = false;
let stopped = false;
let lastFailure = '';
let progressId = null;
let overallPercent = null;

function elapsed(operation) {
  return Math.max(0, (operation.finished_at || Date.now() / 1000) - operation.started_at);
}

function render(operation) {
  const panel = document.getElementById('shared-operation');
  const label = document.getElementById('shared-operation-label');
  const progress = document.getElementById('shared-operation-progress');
  const cancel = document.getElementById('shared-operation-cancel');
  panel.hidden = !operation;
  if (!operation) return;
  const state = operation.progress || {};
  if (progressId !== operation.id) { progressId = operation.id; overallPercent = null; }
  if (state.total > 0) overallPercent = Math.max(overallPercent || 0, Math.min(99, Math.floor(state.step / state.total * 100)));
  const percent = overallPercent;
  const labels = {rewrite: 'Rewriting prompt', video: 'Generating video', voice: 'Generating voice', image: 'Generating image'};
  const name = operation.kind === 'image' && operation.mode === 'edit' ? 'Editing image' : labels[operation.kind] || 'Generating media';
  const stopping = operation.status === 'stopping';
  const phase = stopping ? 'Stopping' : state.stage === 'preparing' ? 'Loading model'
    : state.total && state.step >= state.total ? 'Finishing' : name;
  const detail = [operation.model, operation.batch_total ? 'Item ' + (operation.batch_index || 1) + ' of ' + operation.batch_total
    : state.label ? 'Image ' + state.label : ''].filter(Boolean).join(' · ');
  label.textContent = !stopping && operation.kind === 'rewrite' && state.stage === 'preparing' ? 'Preparing prompt rewrite' : phase;
  document.getElementById('shared-operation-detail').textContent = detail;
  document.getElementById('shared-operation-percent').textContent = percent === null ? '' : percent + '%';
  const seconds = Math.floor(elapsed(operation));
  document.getElementById('shared-operation-elapsed').textContent = Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0') + ' elapsed';
  if (percent === null) progress.removeAttribute('value');
  else progress.value = percent;
  cancel.disabled = stopping;
  cancel.querySelector('span').textContent = stopping ? 'Stopping…' : 'Cancel';
  panel.dataset.operationId = operation.id;
  panel.dataset.status = operation.status;
}

async function cancelActive() {
  if (!active) return;
  page.prepareNativeCancel(active);
  const operationId = active.id;
  document.getElementById('shared-operation-cancel').disabled = true;
  try {
    const answer = await fetch('/api/v1/operations/' + encodeURIComponent(operationId) + '/cancel', {method: 'POST'});
    if (!answer.ok) throw new Error((await answer.json()).error || 'The operation could not be stopped.');
    await poll();
  } catch (error) {
    page.notify('error', error.message);
  }
}

async function importVideo(operation, answer, identity = operation.id) {
  const contentType = answer.headers.get('content-type') || '';
  const settings = Object.assign({}, operation.settings, {
    operationId: identity, backend: operation.backend, modelName: operation.model,
    createdAt: (operation.completed_at || operation.finished_at) * 1000,
    prompt: operation.prompt, width: operation.width ?? operation.settings?.width,
    height: operation.height ?? operation.settings?.height,
    numFrames: operation.num_frames ?? operation.settings?.num_frames,
    frameRate: operation.frame_rate ?? operation.settings?.frame_rate,
    elapsedSeconds: elapsed(operation),
  });
  settings.duration = settings.numFrames / settings.frameRate;
  const seed = answer.headers.get('X-Studio-Seed');
  if (seed !== null) settings.seed = Number(seed);
  if (contentType.includes('video/mp4')) await page.video().addGeneratedClip(await answer.blob(), settings);
  else page.video().addStubClip(await answer.json(), settings);
}

async function importBatch(operation, answer) {
  const manifest = await answer.json();
  for (const item of manifest.items || []) {
    if (!item.result_url) continue;
    const identity = operation.id + ':' + item.index;
    if (batchItems.has(identity)) continue;
    const response = await fetch(item.result_url, {cache: 'no-store'});
    if (response.status === 404 || response.status === 410) continue;
    if (!response.ok) throw new Error('A completed batch item could not be loaded.');
    const record = {...operation, ...item, id: operation.id + ':' + item.index,
      finished_at: item.completed_at || operation.finished_at};
    if (operation.kind === 'video') await importVideo(record, response, record.id);
    else if (operation.kind === 'image') {
      const result = await response.json();
      await page.addImages(record, result.images || [], item.index - 1);
    }
    batchItems.add(identity);
  }
}

async function importResult(operation) {
  if (imported.has(operation.id) || (operation.client_id === page.clientId && operation.kind !== 'voice'
      && !(operation.kind === 'image' && operation.batch_total))) return;
  if (operation.source === 'ui' && operation.library_id !== page.libraryId && !owners.has(operation.client_id)) return;
  if (operation.source === 'ui' && !owners.has(operation.client_id) && !observed.has(operation.id)
      && operation.started_at < openedAt && (operation.finished_at || 0) < openedAt) return;
  const terminalFailure = operation.status === 'failed' || operation.status === 'cancelled';
  const message = operation.error || (operation.status === 'cancelled' ? 'The operation was cancelled.' : 'The operation failed.');
  if (terminalFailure && !operation.result_url) {
    remember(operation.id);
    page.notify(operation.status === 'failed' ? 'error' : 'info', message);
    return;
  }
  const partialBatch = ['running', 'stopping'].includes(operation.status) && operation.batch_completed > 0;
  if ((!terminalFailure && operation.status !== 'succeeded' && !partialBatch) || !operation.result_url) return;
  if (partialBatch && batchCounts.get(operation.id) >= operation.batch_completed) return;
  const answer = await fetch(operation.result_url, {cache: 'no-store'});
  if (answer.status === 404 || answer.status === 410) {
    remember(operation.id);
    return;
  }
  if (!answer.ok) throw new Error('The completed result could not be loaded.');
  if (operation.kind === 'voice') {
    await customElements.whenDefined('voice-studio');
    await page.voice().importOperation(operation, answer);
  } else if (operation.batch_total || Array.isArray(operation.settings?.items)) {
    await importBatch(operation, answer);
  } else if (operation.kind === 'video') {
    await importVideo(operation, answer);
  } else {
    const result = await answer.json();
    if (operation.kind === 'image') await page.addImages(operation, result.images || []);
    else page.showRewrite(operation, result);
  }
  if (terminalFailure) page.notify(operation.status === 'failed' ? 'error' : 'info', message);
  if (partialBatch) batchCounts.set(operation.id, operation.batch_completed);
  else remember(operation.id);
}

async function poll() {
  if (polling || stopped) return;
  polling = true;
  try {
    const answer = await fetch('/api/v1/state', {cache: 'no-store'});
    if (answer.status === 404) {
      stopped = true;
      awake.set(false);
      return;
    }
    if (answer.status === 503 && (await answer.clone().json()).error === 'The JSON API is not configured.') {
      stopped = true;
      awake.set(false);
      return;
    }
    if (!answer.ok) throw new Error('Shared status is unavailable.');
    const state = await answer.json();
    active = state.active;
    awake.set(active);
    if (active && !observed.has(active.id)) {
      observed.add(active.id);
      try {
        sessionStorage.setItem('studio-observed-operations', JSON.stringify(Array.from(observed).slice(-256)));
      } catch (error) {
        console.warn('Observed operations were not saved:', error);
      }
    }
    render(active);
    if (page.beforeState) page.beforeState();
    try {
      if (state.studio) page.syncModels(state.studio);
      page.setActive(active);
    } finally { if (page.afterState) page.afterState(); }
    if (active && active.kind === 'video' && active.client_id !== page.clientId) {
      page.video().setGenerationProgress(Object.assign({running: true}, active.progress), elapsed(active), {
        width: active.width, height: active.height, modelName: active.model, prompt: active.prompt,
        numFrames: active.num_frames, frameRate: active.frame_rate,
        fastMode: Boolean(active.settings?.fast_mode),
      });
    }
    page.observeDrafts(state.operations || []);
    for (const operation of (state.operations || []).slice().reverse()) {
      await importResult(operation);
      page.finishImageOperation(operation);
    }
    lastFailure = '';
  } catch (error) {
    awake.set(false);
    if (lastFailure !== error.message) page.notify('info', error.message);
    lastFailure = error.message;
  } finally {
    polling = false;
  }
}

document.dispatchEvent(new CustomEvent('operations-ready', {
  detail: {configure(helpers) {
    Object.assign(page, helpers);
    owners.add(page.clientId);
    try {
      sessionStorage.setItem('studio-operation-owners', JSON.stringify(Array.from(owners).slice(-64)));
    } catch (error) {
      console.warn('Operation owners were not saved:', error);
    }
    document.getElementById('shared-operation-cancel').addEventListener('click', cancelActive);
    document.addEventListener('visibilitychange', function () { if (!document.hidden) poll(); });
    window.addEventListener('pagehide', function () { stopped = true; awake.set(false); });
    window.addEventListener('pageshow', function () { stopped = false; poll(); });
    poll();
    window.setInterval(poll, 350);
    return {refresh: poll};
  }},
}));
