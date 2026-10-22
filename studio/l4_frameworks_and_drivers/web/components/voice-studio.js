import {LitElement, html, svg, nothing, render} from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import {audioPeaks, blobBase64, decodeAudio, downloadAudio, joinAudio, normalizeReference, TRACK_GAP} from '../lib/voice-audio.js';
import {clearVoice, loadVoice, saveVoice} from '../lib/voice-store.js';
import {closeMenus, toggleMenu} from './popup-menu.js';
import './run-button.js';
import './audio-preview.js';
import {mediaDownloadName, mediaExtension} from '../lib/download-name.js';
import {pencilLoop} from './gallery-marker.js';
import './gallery-browser.js';
import {galleryBatch, preferredGalleryId, rememberGalleryView} from '../lib/gallery-view.js';

const DEFAULT_CAPABILITIES = {name: 'Drama-3', modes: []};

function transcriptText(text) {
  if (String(text).includes('<|phoneme_start|>')) return '';
  return String(text).replace(/\[[^\]]*\]/g, '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
}

function durationLabel(seconds) {
  return Number.isFinite(seconds) ? seconds.toFixed(1) + ' s' : '';
}

class VoiceStudio extends LitElement {
  static properties = {
    script: {state: true}, segments: {state: true}, mode: {state: true}, voice: {state: true},
    editText: {state: true},
    reference: {state: true}, referencePending: {state: true}, selectedId: {state: true}, templateName: {state: true},
    fieldValues: {state: true}, activeOperation: {state: true}, showGeneration: {state: true}, recording: {state: true},
    engineOptions: {state: true}, capabilities: {state: true}, seconds: {state: true}, convert: {state: true}, seed: {state: true},
    busy: {state: true}, stopping: {state: true}, error: {state: true}, playing: {state: true},
    position: {state: true}, trackDuration: {state: true}, detailsOpen: {state: true}, previewReady: {state: true}, previewBusy: {state: true}, previewSource: {attribute: false}, previewSpeed: {state: true},
  };

  constructor() {
    super();
    this.script = '';
    this.draftId = crypto.randomUUID();
    this.editText = '';
    this.segments = [];
    this.mode = 'design';
    this.voice = '';
    this.reference = null;
    this.referencePending = false;
    this.selectedId = null;
    this.templateName = '';
    this.fieldValues = {};
    this.activeOperation = null;
    this.showGeneration = false;
    this.recording = false;
    this.recordingPending = false;
    this.capabilities = DEFAULT_CAPABILITIES;
    this.seconds = 0;
    this.convert = 'tw2s';
    this.seed = '';
    this.busy = false;
    this.stopping = false;
    this.error = '';
    this.playing = false;
    this.position = 0;
    this.trackDuration = 0;
    this.detailsOpen = false;
    this.previewReady = false;
    this.previewBusy = false;
    this.previewSource = null;
    this.previewSpeed = 1;
    this.options = {};
    this.engineOptions = {};
    this.saved = Promise.resolve();
    this.loading = true;
    this.importing = new Set();
    this.imported = new Set();
    this.batchCounts = new Map();
    this.fetchedItems = new Set();
    this.removed = new Set();
    this.cutoff = 0;
    try {
      this.removed = new Set(JSON.parse(localStorage.getItem('studio-voice-removed') || '[]'));
      this.cutoff = Number(localStorage.getItem('studio-voice-cutoff') || 0);
    } catch (error) { console.warn('Voice removals could not be read:', error); }
    this.urls = new Set();
    this.storageEpoch = 0;
    this.referenceVersion = 0;
    this.trackRevision = 0;
    this.playbackRevision = 0;
    this.player = new Audio();
    this.player.onended = () => { this.playing = false; };
    this.player.onpause = () => { this.playing = false; };
    this.player.onplay = () => { this.playing = true; };
    this.player.ontimeupdate = () => { this.position = this.player.currentTime; };
    this.player.ondurationchange = () => { this.trackDuration = Number.isFinite(this.player.duration) ? this.player.duration : 0; };
    this.player.onerror = () => this.fail('The audio could not be played.');
    this.channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('studio-voice') : null;
    if (this.channel) this.channel.onmessage = event => this.receive(event.data);
    this.pasteHandler = event => {
      if (this.hidden || this.locked) return;
      const file = Array.from(event.clipboardData?.files || []).find(item => item.type.startsWith('audio/'));
      if (file) { event.preventDefault(); this.addReference(file); }
    };
  }

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    document.addEventListener('paste', this.pasteHandler);
    this.restore();
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this.player.pause();
    this.channel?.close();
    document.removeEventListener('paste', this.pasteHandler);
    this.urls.forEach(url => URL.revokeObjectURL(url));
    this.stopRecording();
  }

  configure(options) {
    this.options = {...this.options, ...options};
    if (options.capabilities) {
      if ((this.capabilities.backend_id || this.draftBackend) && (this.capabilities.backend_id || this.draftBackend) !== options.capabilities.backend_id) {
        this.templateName = '';
        this.fieldValues = {};
        this.engineOptions = {};
      }
      this.capabilities = options.capabilities;
      this.reconcileMode();
      this.trimReferenceIfNeeded();
    }
    this.requestUpdate();
  }

  reconcileMode() {
    if (this.capabilities.modes.length && !this.capabilities.modes.some(mode => mode.id === this.mode)) {
      this.stopRecording();
      this.mode = this.capabilities.default_mode || this.capabilities.modes[0].id;
      this.templateName = '';
      this.fieldValues = {};
    }
  }

  hasParam(id) { return Boolean(this.currentMode?.params.some(param => param.id === id)); }
  get needsReference() { return Boolean(this.currentMode?.min_references); }

  get takesCount() { return this.segments.reduce((count, segment) => count + segment.takes.length, 0); }

  get selectedTakes() {
    return this.segments.filter(segment => segment.inScript !== false).map(segment => segment.takes.find(take => take.id === segment.selected) || segment.takes[0]).filter(Boolean);
  }

  get scriptDuration() {
    const takes = this.selectedTakes;
    return takes.reduce((total, take) => total + take.duration, 0) + Math.max(0, takes.length - 1) * TRACK_GAP;
  }
  get currentMode() { return this.capabilities.modes.find(mode => mode.id === this.mode); }
  get templates() { return this.currentMode?.templates || []; }
  get selectedTake() {
    for (const segment of this.segments) {
      const take = segment.takes.find(item => item.id === this.selectedId);
      if (take) return {segment, take};
    }
    return null;
  }
  get previewItem() {
    if (this.selectedTake) return this.selectedTake;
    const segment = this.segments.find(item => item.takes.length) || this.segments[0];
    if (!segment) return null;
    return {segment, take: segment.takes.find(take => take.id === segment.selected) || segment.takes[0] || null};
  }

  get pending() { return this.segments.filter(segment => segment.inScript !== false && !segment.takes.length); }
  get ready() { return Boolean(this.capabilities.modes.length && this.options.clientId); }
  get referenceBusy() { return this.needsReference && (this.referencePending || this.recordingPending); }
  get locked() { return this.busy || Boolean(this.activeOperation); }
  get voiceRunning() { return this.busy || this.activeOperation?.kind === 'voice'; }
  get showingGeneration() { return this.voiceRunning && this.showGeneration; }
  get instruction() {
    const template = this.templates.find(item => item.name === this.templateName);
    if (!template) return this.editText.trim();
    return template.text.replace(/\{([^}]+)\}/g, (_, name) => String(this.fieldValues[name] ?? ''));
  }
  get templateComplete() {
    const template = this.templates.find(item => item.name === this.templateName);
    return !template?.fields.some(field => String(this.fieldValues[field.id] ?? '').trim() === '');
  }
  get referenceLimitReason() {
    const limit = this.capabilities.max_seconds || 120;
    return this.needsReference && this.reference?.duration > limit ? 'Select a reference of ' + limit + ' seconds or shorter' : '';
  }
  get referenceClipSeconds() {
    return this.capabilities.backend_id === 'drama3' ? this.capabilities.max_seconds || 15 : Infinity;
  }

  trimReferenceIfNeeded() {
    if (this.reference?.duration > this.referenceClipSeconds && !this.referencePending) {
      this.chooseReference(this.reference.blob, this.reference);
    }
  }
  get reason() {
    if (!this.ready) return 'Connecting to Voice studio';
    if (this.locked) return 'Another operation is active';
    if (this.recording) return 'Stop recording first';
    if (this.referenceBusy) return this.recordingPending ? 'Opening microphone' : 'Preparing reference audio';
    if (this.needsReference && !this.reference) return 'Add a reference recording';
    if (this.referenceLimitReason) return this.referenceLimitReason;
    if (this.hasParam('ref_text') && !this.reference?.transcript?.trim()) return 'Transcribe the reference recording';
    for (const param of this.currentMode?.params || []) {
      if (param.kind !== 'number') continue;
      const value = this.engineOptions[param.id] ?? param.default;
      if (!Number.isFinite(value) || (param.minimum != null && value < param.minimum)
          || (param.maximum != null && value > param.maximum) || (param.integer && !Number.isInteger(value))) {
        const label = param.id === 'max_tokens' ? 'Audio token limit' : param.id.replaceAll('_', ' ');
        return label + ' must be between ' + param.minimum + ' and ' + param.maximum;
      }
    }
    if (!this.templateComplete) return 'Fill the template fields';
    if (this.mode === 'design' && !this.voice.trim()) {
      return this.script.trim() ? 'Choose a voice template or write your own' : 'Add a script and choose a voice template';
    }
    if (this.mode === 'edit') {
      const template = this.templates.find(item => item.name === this.templateName);
      if (template?.fields.some(field => String(this.fieldValues[field.id] ?? '').trim() === '')) return 'Fill the template fields';
      return this.instruction ? '' : 'Describe the change';
    }
    if (!this.segments.some(segment => segment.inScript !== false)) return 'Write a script';
    return '';
  }

  fail(message) {
    this.error = message;
    this.options.notify?.('error', message);
  }

  async restore() {
    try {
      if (localStorage.getItem('studio-keep') === 'off') return;
      const stored = await loadVoice();
      if (stored && !this.script && !this.takesCount) this.adopt(stored);
    } catch (error) {
      this.options.notify?.('error', 'Voice storage could not be opened. Export takes before closing this tab.');
      console.warn(error);
    } finally {
      this.loading = false;
    }
  }

  adopt(stored) {
    this.script = stored.script || '';
    this.draftId = stored.draftId || null;
    this.editText = stored.editText || '';
    this.voice = stored.voice || '';
    this.mode = stored.mode || this.capabilities.default_mode || 'design';
    this.seconds = stored.seconds || 0;
    this.convert = stored.convert || 'tw2s';
    this.seed = stored.seed ?? '';
    this.draftBackend = stored.backend || null;
    this.engineOptions = stored.backend && this.capabilities.backend_id && stored.backend !== this.capabilities.backend_id ? {} : stored.engineOptions || {};
    this.reference = stored.reference || null;
    this.templateName = stored.templateName || '';
    this.fieldValues = stored.fieldValues || {};
    this.editSegmentId = stored.editSegmentId || null;
    if (stored.backend && this.capabilities.backend_id && stored.backend !== this.capabilities.backend_id) { this.templateName = ''; this.fieldValues = {}; }
    this.reconcileMode();
    this.trimReferenceIfNeeded();
    this.cutoff = Math.max(this.cutoff, stored.cutoff || 0);
    this.removed = new Set([...this.removed, ...(stored.removed || [])]);
    this.segments = (stored.segments || []).map(segment => ({...segment,
      takes: segment.takes.filter(take => !this.removed.has(take.id) && take.createdAt > this.cutoff).map(take => this.hydrate(take)),
    })).filter(segment => segment.inScript !== false || segment.takes.length);
    this.selectedId = preferredGalleryId('voice', this.segments.flatMap(segment => segment.takes), this.options.keeping?.() !== false)
      || stored.selectedId || null;
    if (this.mode !== 'edit') this.setScript(this.script);
  }

  hydrate(take) {
    if (take.url) return take;
    const url = URL.createObjectURL(take.blob);
    this.urls.add(url);
    return {...take, url};
  }

  snapshot() {
    return {
      backend: this.capabilities.backend_id, script: this.script, draftId: this.draftId, editText: this.editText, voice: this.voice, mode: this.mode, seconds: this.seconds,
      engineOptions: this.engineOptions, convert: this.convert, seed: this.seed, reference: this.reference,
      templateName: this.templateName, fieldValues: this.fieldValues, editSegmentId: this.editSegmentId,
      cutoff: this.cutoff, removed: Array.from(this.removed).slice(-2048), selectedId: this.selectedId,
      segments: this.segments.map(segment => ({...segment, takes: segment.takes.map(({url, ...take}) => take)})),
    };
  }

  persist(draft = false, selection = null, expectedDraftId = undefined) {
    if (this.loading || this.options.keeping?.() === false) return;
    if (draft) this.draftId = crypto.randomUUID();
    const project = this.snapshot();
    const epoch = this.storageEpoch;
    this.saved = this.saved.then(() => {
      if (epoch === this.storageEpoch && this.options.keeping?.() !== false) return saveVoice(project, draft, selection, expectedDraftId);
    }).catch(error => {
      console.warn(error);
      this.options.notify?.('error', 'This browser did not keep the voice project. Export the WAV before closing this tab.');
    });
  }

  receive(message) {
    if (message.kind === 'take') this.addTake(message.take, message.text, false, message.segmentId);
    if (message.kind === 'remove') this.removeTake(message.id, false);
    if (message.kind === 'clear') this.clearCompleted(message.cutoff, false);
  }

  setScript(value) {
    this.invalidateTrack();
    this.script = value;
    if (this.mode !== 'edit') {
      const remaining = this.segments.slice();
      const texts = value.trim() ? [value.trim()] : [];
      const current = texts.map(text => {
        const index = remaining.findIndex(segment => segment.text === text);
        return index >= 0 ? {...remaining.splice(index, 1)[0], inScript: true}
          : {id: crypto.randomUUID(), text, takes: [], selected: null, inScript: true};
      });
      const history = remaining.filter(segment => segment.takes.length).map(segment => ({...segment, inScript: false}));
      this.segments = [...current, ...history];
    }
    this.persist(true);
  }

  selectMode(mode) {
    if (this.locked) return;
    if (!this.capabilities.modes.some(candidate => candidate.id === mode)) return;
    if (!this.capabilities.modes.find(candidate => candidate.id === mode)?.min_references) this.stopRecording();
    this.mode = mode;
    this.templateName = '';
    this.fieldValues = {};
    this.error = '';
    if (mode !== 'edit') this.setScript(this.script);
    else this.persist(true);
  }

  selectTemplate(name) {
    if (this.locked) return;
    closeMenus();
    this.templateName = name;
    const template = this.templates.find(item => item.name === name);
    this.fieldValues = Object.fromEntries((template?.fields || []).map(field => [field.id, field.default ?? '']));
    if (template?.target === 'voice') this.voice = this.templateText(template);
    else if (template && this.mode !== 'edit') this.setScript(this.templateText(template));
    else if (this.mode === 'design') this.voice = '';
    this.persist(true);
  }

  templateText(template, values = this.fieldValues) {
    return template.text.replace(/\{([^}]+)\}/g, (_, name) => String(values[name] ?? template.fields.find(field => field.id === name)?.default ?? ''));
  }

  setTemplateValue(name, value) {
    this.fieldValues = {...this.fieldValues, [name]: value};
    const template = this.templates.find(item => item.name === this.templateName);
    if (template?.target === 'voice') this.voice = this.templateText(template);
    else if (template && this.mode !== 'edit') this.setScript(this.templateText(template));
    this.persist(true);
  }

  async chooseReference(file, {name, transcript = ''} = {}) {
    if (!file || this.locked) return;
    const version = ++this.referenceVersion;
    this.referencePending = false;
    if (file.size > (this.capabilities.max_reference_megabytes || 32) * 1024 * 1024) {
      this.fail('The reference is too large. Choose an audio file smaller than 32 MB.');
      return;
    }
    this.referencePending = true;
    try {
      let normalized, backend;
      do {
        backend = this.capabilities.backend_id;
        normalized = await normalizeReference(file, this.capabilities.reference_sample_rate || 24000, this.referenceClipSeconds);
        if (version !== this.referenceVersion || this.locked) return;
      } while (backend !== this.capabilities.backend_id);
      if (normalized.duration > (this.capabilities.max_seconds || 120)) throw new Error('The reference must be ' + (this.capabilities.max_seconds || 120) + ' seconds or shorter.');
      if (normalized.blob.size > (this.capabilities.max_reference_megabytes || 32) * 1024 * 1024) throw new Error('The normalized recording exceeds the audio size limit.');
      this.reference = {...normalized, name: name || file.name || 'recording.wav', transcript: normalized.trimmed ? '' : transcript};
      this.editSegmentId = null;
      this.error = '';
      this.persist(true);
    } catch (error) {
      if (version === this.referenceVersion) this.fail('This audio file could not be read: ' + error.message);
    } finally {
      if (version === this.referenceVersion) this.referencePending = false;
    }
  }

  async addReference(file) {
    if (!file || this.locked) return;
    if (!file.type.startsWith('audio/')) { this.fail('Choose an audio recording as the voice reference.'); return; }
    if (!this.needsReference) this.selectMode('clone');
    await this.chooseReference(file);
  }

  async toggleRecording() {
    if (this.recording) { this.stopRecording(); return; }
    if (this.reference || this.recordingPending || this.locked) return;
    if (!navigator.mediaDevices?.getUserMedia) { this.fail('Recording needs localhost or HTTPS microphone access.'); return; }
    this.recordingPending = true;
    this.requestUpdate();
    let stream = null;
    try {
      stream = await navigator.mediaDevices.getUserMedia({audio: true});
      if (this.hidden || this.locked || !this.needsReference) { stream.getTracks().forEach(track => track.stop()); return; }
      this.recorderStream = stream;
      this.recorder = new MediaRecorder(stream);
      const chunks = [];
      this.recorder.ondataavailable = event => { if (event.data.size) chunks.push(event.data); };
      this.recorder.onstop = () => {
        clearTimeout(this.recordingTimer);
        const blob = new Blob(chunks, {type: this.recorder.mimeType});
        stream.getTracks().forEach(track => track.stop());
        this.recording = false;
        this.chooseReference(new File([blob], 'recording.webm', {type: blob.type}));
      };
      this.recorder.start();
      this.recording = true;
      this.recordingTimer = setTimeout(() => this.stopRecording(), (this.capabilities.max_seconds || 120) * 1000);
    } catch (error) {
      stream?.getTracks().forEach(track => track.stop());
      this.fail('The microphone could not be opened: ' + error.message);
    } finally {
      this.recordingPending = false;
      this.requestUpdate();
    }
  }

  stopRecording() {
    clearTimeout(this.recordingTimer);
    if (this.recorder?.state === 'recording') this.recorder.stop();
  }

  setOperation(operation) {
    const previous = this.activeOperation;
    this.activeOperation = operation;
    if (operation?.kind === 'voice' && operation.id !== previous?.id && !this.busy) {
      const mode = operation.mode || operation.settings?.mode;
      if (this.capabilities.modes.some(candidate => candidate.id === mode)) this.mode = mode;
      this.showGeneration = true;
      this.detailsOpen = false;
      this.pausePlayback();
    }
  }

  async generate(segment = null) {
    if (!this.ready || this.locked || this.recording || this.referenceBusy || (!segment && this.reason)) return;
    if (segment && this.referenceLimitReason) { this.fail(this.referenceLimitReason); return; }
    if (segment && this.hasParam('ref_text') && !this.reference?.transcript?.trim()) { this.fail('Transcribe the reference recording'); return; }
    if (segment && !this.templateComplete) { this.fail('Fill the template fields'); return; }
    if (segment && this.needsReference && !this.reference) { this.fail('Add a reference recording first.'); return; }
    const submittedDraftId = this.draftId;
    this.showGeneration = true;
    this.detailsOpen = false;
    this.pausePlayback();
    this.busy = true;
    this.error = '';
    try {
      const items = this.mode === 'edit' ? [{text: this.instruction, segment_id: this.editSegmentId,
        segment_text: this.segments.find(item => item.id === this.editSegmentId)?.text}]
        : (segment ? [segment] : this.segments.filter(item => item.inScript !== false).slice(0, 1)).map(item => ({text: item.text, segment_id: item.id}));
      const payload = {
        kind: 'voice', workspace: 'voice', backend: this.capabilities.backend_id || 'auk', mode: this.mode,
        client_id: this.options.clientId,
      };
      for (const param of this.currentMode.params) {
        if (param.id in this.engineOptions) payload[param.id] = this.engineOptions[param.id];
      }
      if (this.hasParam('voice')) payload.voice = this.voice;
      if (this.hasParam('seconds')) payload.seconds = Number(this.seconds);
      if (this.hasParam('convert')) payload.convert = this.convert;
      if (this.hasParam('ref_text')) payload.ref_text = this.reference?.transcript || '';
      if (this.templateName) {
        payload.template = this.templateName;
        payload.template_values = {...this.fieldValues};
      }
      if (this.seed !== '') payload.seed = Number(this.seed);
      const reference = this.needsReference ? this.reference : null;
      if (reference) payload.reference = {wav_base64: await blobBase64(reference.blob), name: reference.name};
      if (items.length === 1) Object.assign(payload, items[0]);
      else payload.items = items;
      const response = await fetch('/voice/operations', {
        method: 'POST', headers: {'Content-Type': 'application/json', 'X-Studio-Client': this.options.clientId,
          'X-Studio-Library': this.options.libraryId}, body: JSON.stringify(payload),
      });
      const operation = await response.json();
      if (!response.ok) throw new Error(operation.error || 'The voice operation could not start.');
      this.ownOperationId = operation.id;
      this.requestUpdate();
      let state;
      do {
        await new Promise(resolve => setTimeout(resolve, 350));
        const answer = await fetch('/api/v1/operations/' + encodeURIComponent(operation.id), {cache: 'no-store'});
        state = await answer.json();
        if (!answer.ok) throw new Error(state.error || 'The operation status could not be read.');
        if (state.result_url && state.batch_completed > 0) await this.importOperation(state);
      } while (state.status === 'running' || state.status === 'stopping');
      if (state.result_url) await this.importOperation(state);
      document.dispatchEvent(new CustomEvent('operation-imported', {detail: operation.id}));
      if (state.status === 'failed') throw new Error(state.error || 'The voice operation failed.');
      if (state.status === 'succeeded') this.clearInputs(submittedDraftId);
      if (state.status === 'cancelled') this.options.notify?.('info', 'The voice operation stopped. Completed takes remain.');
    } catch (error) {
      this.fail(error.message);
    } finally {
      this.ownOperationId = null;
      this.busy = false;
      this.stopping = false;
      this.persist();
    }
  }

  clearInputs(expectedDraftId) {
    this.invalidateTrack();
    this.script = '';
    this.voice = '';
    this.editText = '';
    this.templateName = '';
    this.fieldValues = {};
    this.referenceVersion += 1;
    this.reference = null;
    this.referencePending = false;
    this.editSegmentId = null;
    this.seed = '';
    this.seconds = 0;
    this.convert = 'tw2s';
    this.engineOptions = {};
    this.segments = this.segments.filter(segment => segment.takes.length).map(segment => ({...segment, inScript: false}));
    this.persist(true, null, expectedDraftId);
  }

  async importOperation(operation, answer = null) {
    if (this.imported.has(operation.id) || this.importing.has(operation.id)) return;
    if (['running', 'stopping'].includes(operation.status) && this.batchCounts.get(operation.id) >= operation.batch_completed) return;
    this.importing.add(operation.id);
    try {
      const response = answer || await fetch(operation.result_url, {cache: 'no-store'});
      if (!response.ok) throw new Error('The completed voice result could not be read.');
      if ((response.headers.get('content-type') || '').includes('application/json')) {
        const manifest = await response.json();
        for (const [index, item] of (manifest.items || manifest.results || []).entries()) {
          if (!item.result_url) continue;
          const identity = operation.id + ':' + index;
          if (this.fetchedItems.has(identity)) continue;
          const answer = await fetch(item.result_url);
          if (!answer.ok) throw new Error('A completed voice segment could not be loaded.');
          await this.addAudio(await answer.blob(), {...operation, ...item,
            id: identity, text: item.text || item.settings?.text || operation.settings?.items?.[index]?.text,
          });
          this.fetchedItems.add(identity);
        }
        this.batchCounts.set(operation.id, manifest.items?.length || manifest.results?.length || 0);
      } else {
        await this.addAudio(await response.blob(), {...operation, text: operation.text || operation.settings?.text});
      }
      if (!['running', 'stopping'].includes(operation.status)) this.imported.add(operation.id);
    } finally {
      this.importing.delete(operation.id);
    }
  }

  async addAudio(blob, settings) {
    const id = 'voice-operation-' + settings.id;
    const createdAt = (settings.completed_at || settings.finished_at || Date.now() / 1000) * 1000;
    if (this.removed.has(id) || createdAt <= this.cutoff || this.segments.some(segment => segment.takes.some(take => take.id === id))) return;
    const decoded = await decodeAudio(blob);
    const design = this.capabilities.modes.find(mode => mode.id === 'design');
    const template = design?.templates?.find(item => item.name === (settings.settings?.template || settings.template));
    const voice = template ? this.templateText(template, settings.settings?.template_values || settings.template_values || {})
      : settings.settings?.voice || settings.voice || '';
    const take = {id, blob, createdAt, duration: decoded.duration, peaks: audioPeaks(decoded.samples),
      seed: settings.seed, mode: settings.settings?.mode || settings.mode || 'design',
      voice, model: settings.model || 'AuK Flash',
      backend: settings.settings?.backend || settings.backend || (settings.model === 'AuK' ? 'auk_base' : 'auk'),
      convert: settings.settings?.convert || settings.convert || 'tw2s',
      elapsed: settings.finished_at && settings.started_at ? settings.finished_at - settings.started_at : null};
    this.addTake(take, settings.settings?.segment_text || settings.segment_text || settings.text || settings.prompt || 'Imported voice',
      true, settings.settings?.segment_id || settings.segment_id || 'voice-line-' + settings.id);
  }

  addTake(take, text, broadcast = true, segmentId = null) {
    this.detailsOpen = false;
    if (this.removed.has(take.id) || take.createdAt <= this.cutoff || this.segments.some(segment => segment.takes.some(item => item.id === take.id))) return;
    this.pausePlayback();
    this.invalidateTrack();
    const index = segmentId ? this.segments.findIndex(segment => segment.id === segmentId)
      : this.segments.findIndex(segment => segment.text === text && !segment.takes.length);
    const segment = index >= 0 ? this.segments[index] : {id: segmentId || crypto.randomUUID(), text, takes: [], selected: null, inScript: false};
    const updated = {...segment, takes: [...segment.takes, this.hydrate(take)], selected: take.id};
    this.segments = index >= 0 ? this.segments.map((item, offset) => offset === index ? updated : item) : [...this.segments, updated];
    this.selectedId = take.id;
    if (broadcast) this.channel?.postMessage({kind: 'take', take, text, segmentId: segment.id});
    this.persist(false, {segmentId: segment.id, takeId: take.id});
  }

  removeTake(id, broadcast = true) {
    this.detailsOpen = false;
    this.invalidateTrack();
    this.removed.add(id);
    this.saveRemovals();
    if (this.selectedId === id) { this.player.pause(); this.selectedId = null; }
    this.segments.forEach(segment => segment.takes.filter(take => take.id === id).forEach(take => this.releaseUrl(take.url)));
    this.segments = this.segments.map(segment => ({...segment, takes: segment.takes.filter(take => take.id !== id),
      selected: segment.selected === id ? segment.takes.find(take => take.id !== id)?.id || null : segment.selected}))
      .filter(segment => segment.inScript !== false || segment.takes.length);
    if (broadcast) this.channel?.postMessage({kind: 'remove', id});
    this.persist();
  }

  clearCompleted(cutoff = Date.now(), broadcast = true) {
    this.detailsOpen = false;
    this.invalidateTrack();
    this.player.pause();
    this.cutoff = Math.max(this.cutoff, cutoff);
    this.segments.forEach(segment => segment.takes.forEach(take => { if (take.createdAt <= this.cutoff) this.removed.add(take.id); }));
    this.segments.forEach(segment => segment.takes.filter(take => take.createdAt <= this.cutoff).forEach(take => this.releaseUrl(take.url)));
    this.saveRemovals();
    this.segments = this.segments.map(segment => ({...segment, takes: segment.takes.filter(take => take.createdAt > this.cutoff), selected: null}))
      .filter(segment => segment.inScript !== false || segment.takes.length);
    this.selectedId = null;
    if (broadcast) this.channel?.postMessage({kind: 'clear', cutoff});
    this.persist();
  }

  async setKeeping(keep) {
    rememberGalleryView('voice', {}, keep);
    if (keep) this.persist(true);
    else {
      this.storageEpoch += 1;
      try {
        await this.saved;
        await clearVoice();
      } catch (error) {
        console.warn(error);
        this.fail('This browser could not clear the saved voice project.');
      }
    }
  }

  selectTake(segmentId, takeId) {
    this.showGeneration = false;
    this.detailsOpen = false;
    closeMenus();
    this.pausePlayback();
    this.invalidateTrack();
    this.segments = this.segments.map(segment => segment.id === segmentId ? {...segment, selected: takeId} : segment);
    this.selectedId = takeId;
    rememberGalleryView('voice', {selected: takeId}, this.options.keeping?.() !== false);
    this.persist(false, {segmentId, takeId});
  }

  galleryKey(event) {
    const buttons = Array.from(this.querySelectorAll('.voice-clip, .voice-render-pending'));
    const index = buttons.indexOf(event.target.closest('button'));
    if (index < 0) return;
    const moves = {ArrowRight: Math.min(index + 1, buttons.length - 1), ArrowLeft: Math.max(0, index - 1), Home: 0, End: buttons.length - 1};
    if (!(event.key in moves)) return;
    event.preventDefault();
    event.stopPropagation();
    const button = buttons[moves[event.key]];
    button.click();
    button.focus();
    button.scrollIntoView({block: 'nearest', inline: 'nearest'});
  }

  stepTake(delta) {
    const clips = this.segments.flatMap(segment => segment.takes.map(take => ({segment, take})))
      .sort((a, b) => b.take.createdAt - a.take.createdAt);
    const next = clips[clips.findIndex(({take}) => take.id === this.previewItem?.take?.id) + delta];
    if (!next) return false;
    this.selectTake(next.segment.id, next.take.id);
    this.updateComplete.then(() => this.querySelector('.voice-clip.selected')?.scrollIntoView({block: 'nearest', inline: 'nearest'}));
    return true;
  }

  pausePlayback() {
    this.playbackRevision++;
    this.player.pause();
    this.querySelector('audio-preview')?.pause();
  }

  async useSelection(event) {
    if (this.hidden) return;
    if (this.locked) { this.fail('Another operation is active.'); return; }
    const {action, blob, start, end, name} = event.detail;
    if (action === 'video') {
      try { await this.options.onSendToVideo?.({blob, name}); }
      catch (error) { this.fail(error.message); }
      return;
    }
    if (action === 'clone') {
      if (this.recording || this.referenceBusy) { this.fail('Stop recording and wait for the reference audio first.'); return; }
      this.pausePlayback();
      this.editSegmentId = null;
      this.selectMode('clone');
      await this.chooseReference(blob, {name, transcript: start === 0 && end === this.querySelector('audio-preview')?.duration ? transcriptText(this.previewItem?.segment.text || '') : ''});
      return;
    }
    if (action !== 'edit' || !this.capabilities.modes.some(mode => mode.id === 'edit')) return;
    const preview = this.querySelector('audio-preview');
    const take = this.previewItem?.take;
    if (take && preview?.blob === take.blob && start === 0 && end === preview.duration) {
      this.pausePlayback();
      await this.useForEdit(take);
      return;
    }
    this.pausePlayback();
    this.referenceVersion += 1;
    this.referencePending = false;
    this.reference = {blob, name, duration: end - start};
    this.editSegmentId = null;
    this.selectMode('edit');
  }

  async reuseSettings(item) {
    if (this.locked || this.recording || this.referenceBusy) return;
    closeMenus();
    this.pausePlayback();
    const {segment, take} = item;
    this.selectMode(this.capabilities.modes.some(mode => mode.id === take.mode) ? take.mode : this.capabilities.default_mode || 'design');
    this.voice = take.voice || '';
    this.convert = take.convert || 'tw2s';
    this.setScript(segment.text);
    if (this.needsReference) await this.chooseReference(take.blob, {name: 'voice-reference.wav', transcript: transcriptText(segment.text)});
    this.persist(true);
    document.getElementById('voice-text')?.focus();
  }

  async useForEdit(take) {
    if (this.locked) return;
    this.referenceVersion += 1;
    this.referencePending = false;
    this.reference = {blob: take.blob, name: 'take.wav', duration: take.duration};
    this.editSegmentId = this.segments.find(segment => segment.takes.some(item => item.id === take.id))?.id;
    this.selectMode('edit');
  }

  saveRemovals() {
    try {
      localStorage.setItem('studio-voice-removed', JSON.stringify(Array.from(this.removed).slice(-2048)));
      localStorage.setItem('studio-voice-cutoff', String(this.cutoff));
    } catch (error) { console.warn('Voice removals could not be saved:', error); }
  }

  releaseUrl(url) {
    if (!url) return;
    URL.revokeObjectURL(url);
    this.urls.delete(url);
  }

  invalidateTrack() {
    this.trackRevision++;
    if (this.trackUrl && this.player.src === this.trackUrl) {
      this.player.pause();
      this.player.removeAttribute('src');
      this.player.load();
      this.trackDuration = 0;
      this.position = 0;
    }
    this.releaseUrl(this.trackUrl);
    this.trackUrl = null;
  }

  async exportTrack(play = false) {
    const revision = this.trackRevision;
    const playbackRevision = this.playbackRevision;
    const takes = this.selectedTakes;
    if (!takes.length) return;
    try {
      const joined = await joinAudio(takes.map(take => take.blob));
      if (play) {
        if (revision !== this.trackRevision || playbackRevision !== this.playbackRevision) return;
        this.releaseUrl(this.trackUrl);
        const url = URL.createObjectURL(joined);
        this.trackUrl = url;
        this.urls.add(url);
        this.player.src = url;
        await this.player.play();
      } else downloadAudio(joined, mediaDownloadName({kind: 'audio', text: this.script,
        at: Math.max(...takes.map(take => take.createdAt || 0)) || undefined,
        id: takes.map(take => take.id).join(','), extension: 'wav'}));
    } catch (error) {
      if (!play || (revision === this.trackRevision && playbackRevision === this.playbackRevision)) this.fail(error.message);
    }
  }

  async playTrack() {
    const revision = ++this.playbackRevision;
    this.querySelector('audio-preview')?.pause();
    if (this.playing) { this.player.pause(); return; }
    if (this.trackUrl && this.player.src === this.trackUrl && !this.player.ended) {
      try { await this.player.play(); } catch (error) { if (revision === this.playbackRevision) this.fail(error.message); }
      return;
    }
    await this.exportTrack(true);
  }

  async cancel() {
    const id = this.ownOperationId || this.activeOperation?.id;
    if (!id || this.stopping) return;
    this.stopping = true;
    try {
      const answer = await fetch('/api/v1/operations/' + encodeURIComponent(id) + '/cancel', {method: 'POST'});
      if (!answer.ok) throw new Error((await answer.json()).error || 'The operation could not be stopped.');
    } catch (error) { this.stopping = false; this.fail(error.message); }
  }

  templateFields(template) {
    if (!template) return nothing;
    return html`<p class="caption voice-note">${template.hint}</p>
      ${template.fields.map(field => html`<label class="field voice-template-field">${this.mode === 'design' ? field.id[0].toUpperCase() + field.id.slice(1) : field.id}
        ${field.choices?.length ? html`<select .value=${String(this.fieldValues[field.id] ?? '')} ?disabled=${this.locked}
          @change=${event => this.setTemplateValue(field.id, event.target.value)}>
          ${field.choices.map(choice => html`<option value=${choice.value} ?selected=${String(choice.value) === String(this.fieldValues[field.id] ?? '')}>${choice.label}</option>`)}</select>`
          : html`<input type=${field.kind === 'number' ? 'number' : 'text'} .value=${String(this.fieldValues[field.id] ?? '')}
            min=${field.minimum ?? nothing} max=${field.maximum ?? nothing} step=${field.step ?? nothing} ?disabled=${this.locked}
            @input=${event => this.setTemplateValue(field.id, event.target.value)}>`}</label>`)}`;
  }

  templateButton() {
    if (!this.templates.length) return nothing;
    return html`<div class="head-actions"><button type="button" class="pill" id="voice-templates-toggle" aria-expanded="false" aria-controls="voice-templates"
      ?disabled=${this.locked} @click=${() => toggleMenu(document.getElementById('voice-templates'))}>
      <svg class="icon" aria-hidden="true"><use href="#i-layout"/></svg>${this.templateName || 'Templates'}</button></div>`;
  }

  templateMenu() {
    if (!this.templates.length) return nothing;
    return html`<div class="menu" id="voice-templates" role="menu" hidden>
      <button type="button" role="menuitem" ?disabled=${this.locked} @click=${() => this.selectTemplate('')}>${this.mode === 'design' ? 'Write your own' : this.mode === 'edit' ? 'Custom instruction' : 'Write your own script'}</button>
      ${this.templates.map(item => html`<button type="button" role="menuitem" ?disabled=${this.locked}
        @click=${() => this.selectTemplate(item.name)}>${item.name}</button>`)}
    </div>`;
  }

  controlsTemplate() {
    const editing = this.mode === 'edit';
    const template = this.templates.find(item => item.name === this.templateName);
    return html`
      <div class="voice-panel" @dragover=${event => event.preventDefault()}
        @drop=${event => { event.preventDefault(); this.addReference(event.dataTransfer.files[0]); }}
        @keydown=${event => { if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) { event.preventDefault(); event.stopPropagation(); this.generate(); } }}>
        <div class="modes voice-mode-picker" role="radiogroup" aria-label="Voice mode">
          ${this.capabilities.modes.map(mode => html`<input type="radio" id=${'voice-mode-' + mode.id} name="voice-mode" value=${mode.id}
            .checked=${this.mode === mode.id} ?disabled=${this.locked} @change=${() => this.selectMode(mode.id)}>
            <label for=${'voice-mode-' + mode.id}><svg class="icon" aria-hidden="true"><use href=${'#i-' + (mode.id === 'edit' ? 'brush' : mode.id === 'clone' ? 'music' : 'sparkle')}/></svg>${mode.label}</label>`)}
        </div>
        <section class="field prompt-field voice-script-group">
          <div class="field-head">
            <label for="voice-text">${editing ? 'What to change' : 'Script'}</label>
            ${!this.hasParam('voice') ? this.templateButton() : nothing}
          </div>
          ${!this.hasParam('voice') ? this.templateMenu() : nothing}
          <textarea id="voice-text" aria-required="true" rows="4" maxlength="20000" .value=${editing ? (template ? this.instruction : this.editText) : this.script} ?disabled=${this.locked}
            placeholder=${editing ? 'Describe the change to the recording.' : this.currentMode?.text_hint || 'Write the words for one continuous audio clip.'}
            @input=${event => {
              if (editing) {
                this.editText = event.target.value;
                this.templateName = '';
                this.fieldValues = {};
                this.persist(true);
              } else {
                if (!this.hasParam('voice')) { this.templateName = ''; this.fieldValues = {}; }
                this.setScript(event.target.value);
              }
            }}></textarea>
          ${!this.hasParam('voice') ? this.templateFields(template) : nothing}
          <p class="caption voice-note">${editing ? 'Edit changes the reference recording. Your existing clips stay in the gallery.'
            : 'Generate creates one continuous clip for the whole script.'}</p>
        </section>
        ${this.hasParam('voice') ? html`<section class="field prompt-field">
          <div class="field-head"><label for="voice-description">Voice description</label>${this.templateButton()}</div>
          ${this.templateMenu()}
          <textarea id="voice-description" rows="3" aria-required="true" .value=${this.voice} ?disabled=${this.locked}
            placeholder="Choose a template, or describe the voice and delivery."
            @input=${event => { this.voice = event.target.value; this.templateName = ''; this.fieldValues = {}; this.persist(true); }}></textarea>
          ${this.templateFields(template)}
          ${!template ? html`<p class="caption voice-note">Describe the speaker, tone and delivery. The script supplies the spoken words.</p>` : nothing}
        </section>` : this.needsReference ? html`<section class="field voice-reference-group">
          <div class="field-head"><label for="voice-reference">Reference recording</label>
            <button type="button" class="text-btn" ?disabled=${this.locked || this.recordingPending || Boolean(this.reference) && !this.recording} @click=${() => this.toggleRecording()}>${this.recording ? 'Stop recording' : this.recordingPending ? 'Opening microphone' : 'Record'}</button></div>
          <input id="voice-reference" type="file" accept="audio/*" hidden ?disabled=${this.locked || this.recording}
            @change=${event => { this.chooseReference(event.target.files[0]); event.target.value = ''; }}>
          ${this.reference ? html`<div class="voice-reference-card video-audios">
            <div class="video-audio">
              <div class="video-audio-picture"><span class="video-audio-badge"><svg class="icon" aria-hidden="true"><use href="#i-music"/></svg></span>
                <button type="button" class="video-audio-remove" aria-label="Clear voice reference" ?disabled=${this.locked}
                  @click=${() => { this.referenceVersion += 1; this.referencePending = false; this.reference = null; this.editSegmentId = null; this.persist(true); }}>
                  <svg class="icon" aria-hidden="true"><use href="#i-x"/></svg></button>
              </div>
              <div><span class="video-audio-name">${this.reference.name}</span><span class="caption">${durationLabel(this.reference.duration)}${this.reference.trimmed ? ' · First 15 s' : ''}</span></div>
            </div>
          </div>` : html`<button type="button" class="refs" id="voice-reference-choose" ?disabled=${this.locked || this.recording}
            aria-label="Add reference recording" @click=${() => document.getElementById('voice-reference').click()}>
            <span class="refs-empty"><svg class="icon" aria-hidden="true"><use href="#i-music"/></svg>
              <span><strong>Add reference recording</strong>Click to choose, or drop or paste audio.</span></span>
          </button>`}
          ${this.referencePending ? html`<p class="caption voice-note" role="status">Preparing reference audio</p>` : nothing}
          <p class="caption voice-note">${editing ? 'Choose the recording to change.' : 'Use a clean recording of one speaker, up to ' + (this.capabilities.max_seconds || 120) + ' s. Only the voice is copied; the script supplies the words.'}${this.referenceClipSeconds < Infinity ? ' Longer recordings use the first 15 s.' : ''}</p>
          ${this.hasParam('ref_text') ? html`<label class="field" for="voice-reference-text">Reference transcript
            <textarea id="voice-reference-text" rows="3" aria-required="true" .value=${this.reference?.transcript || ''}
              ?disabled=${this.locked || !this.reference} placeholder="Write exactly what is spoken in the reference."
              @input=${event => { this.reference = {...this.reference, transcript: event.target.value}; this.persist(true); }}></textarea>
            <span class="caption">Drama-3 needs the exact words to separate the speaker’s voice from the reference content. Correct this after trimming.</span></label>` : nothing}
        </section>` : nothing}
        <details class="voice-advanced">
          <summary>Advanced <span class="values num">${this.hasParam('seconds') && this.seconds > 0 ? this.seconds + ' s' : 'Automatic duration'}, ${String(this.seed).trim() ? 'seed ' + this.seed : 'random seed'}</span></summary>
          <div class="advanced">
            ${this.hasParam('seconds') ? html`<div class="field">
              <div class="field-head"><label for="voice-seconds">Duration</label><span class="caption">Seconds</span></div>
              <input id="voice-seconds" type="number" min="0" max="120" step="0.5" .value=${String(this.seconds)} ?disabled=${this.locked}
                @input=${event => { this.seconds = event.target.value; this.persist(true); }}>
              <span class="caption">Use 0 for automatic duration.</span>
            </div>` : nothing}
            <div class="field">
              <div class="field-head"><label for="voice-seed">Seed</label></div>
              <input id="voice-seed" type="number" min="0" step="1" inputmode="numeric" placeholder="Random" .value=${String(this.seed)} ?disabled=${this.locked}
                @input=${event => { this.seed = event.target.value; this.persist(true); }}>
              <span class="caption">Leave blank for a random seed.</span>
            </div>
            ${this.hasParam('convert') ? html`<div class="field">
              <label for="voice-convert">Chinese characters</label><select id="voice-convert" aria-describedby="voice-convert-hint" .value=${this.convert} ?disabled=${this.locked}
                @change=${event => { this.convert = event.target.value; this.persist(true); }}>
                <option value="tw2s" ?selected=${this.convert === 'tw2s'}>Traditional to Simplified for pronunciation</option><option value="off" ?selected=${this.convert === 'off'}>As written</option>
              </select>
              <span class="caption" id="voice-convert-hint">AuK can mispronounce Traditional Chinese. Conversion helps pronunciation while keeping your script and Taiwan vocabulary unchanged. Choose As written to disable conversion.</span>
            </div>` : nothing}
            ${(this.currentMode?.params || []).filter(param => !['seconds', 'voice', 'convert', 'ref_text'].includes(param.id)).map(param => html`<label class="field" for=${'voice-param-' + param.id}>${param.id === 'max_tokens' ? 'Audio token limit' : param.id.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase())}
              <input id=${'voice-param-' + param.id} type="number" min=${param.minimum ?? nothing} max=${param.maximum ?? nothing}
                step=${param.step || (param.integer ? 1 : 0.1)} .value=${String(this.engineOptions[param.id] ?? param.default)} ?disabled=${this.locked}
                @input=${event => { this.engineOptions = {...this.engineOptions, [param.id]: Number(event.target.value)}; this.persist(true); }}>
              <span class="caption">${param.id === 'max_tokens' ? '64–2048 audio frames per script chunk. Higher values may prolong repetition.' : param.hint}</span></label>`)}
            ${this.capabilities.loading?.note ? html`<p class="caption voice-note">${this.capabilities.loading.note}</p>` : nothing}
          </div>
        </details>
        ${this.error ? html`<p class="voice-error" role="alert">${this.error}</p>` : nothing}
      </div>`;
  }

  footerTemplate() {
    const own = this.busy && this.ownOperationId;
    const stopping = own && (this.stopping || this.activeOperation?.status === 'stopping');
    const starting = this.busy && !this.ownOperationId;
    const state = stopping ? 'stopping' : starting ? 'starting' : own ? 'busy' : 'idle';
    const caption = this.mode === 'edit' ? 'Creates an edited clip' : 'One continuous clip';
    return html`<button id="voice-generate" class="run-button" type="button" data-state=${state} ?disabled=${starting || stopping || (!own && Boolean(this.reason))}
      @click=${() => own ? this.cancel() : this.generate()}>
      <run-button id="voice-run-labels" data-mode=${this.mode === 'edit' ? 'edit' : 'generate'} data-state=${state}></run-button>
      <span class="sub num" id="voice-go-sub">${starting ? 'Preparing the request' : own ? 'Completed clips remain if you stop' : this.reason || caption}</span>
    </button>`;
  }

  updated(changes) {
    if (changes.has('selectedId') && this.selectedId) {
      rememberGalleryView('voice', {selected: this.selectedId}, this.options.keeping?.() !== false);
    }
    if (changes.has('busy')) this.options.onBusyChange?.();
    if (!this.locked && (changes.has('busy') || changes.has('activeOperation'))) this.trimReferenceIfNeeded();
    const controls = document.getElementById('voice-controls');
    const footer = document.getElementById('voice-footer');
    if (controls) render(this.controlsTemplate(), controls);
    if (footer) render(this.footerTemplate(), footer);
    const menu = document.getElementById('voice-templates');
    if (this.locked && menu && !menu.hidden) closeMenus();
  }

  renderWaveform(take) {
    return html`<svg class="voice-waveform" viewBox="0 0 320 48" role="img" aria-label="Audio waveform">
      ${(take?.peaks || Array(80).fill(0.06)).map((peak, index) => svg`<line x1=${index * 4 + 1} x2=${index * 4 + 1}
        y1=${24 - Math.max(1, peak * 22)} y2=${24 + Math.max(1, peak * 22)}></line>`)}</svg>`;
  }

  async openDetails(event) {
    this.detailsTrigger = event?.currentTarget;
    this.detailsOpen = true;
    await this.updateComplete;
    this.querySelector('#voice-details-close')?.focus();
  }

  closeDetails() {
    this.detailsOpen = false;
    this.detailsTrigger?.focus();
  }

  renderMetadata(item) {
    if (!this.detailsOpen || !item) return nothing;
    return html`<section class="sheet" id="voice-details-sheet" role="region" aria-label="Audio details"
      @keydown=${event => { if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); this.closeDetails(); } }}>
      <dl><dt>Script</dt><dd>${item.segment.text}</dd>
        ${item.take?.voice ? html`<dt>Voice description</dt><dd>${item.take.voice}</dd>` : nothing}
        ${item.take ? html`<dt>Model</dt><dd>${item.take.model || 'AuK Flash'}</dd>
          <dt>Mode</dt><dd>${item.take.mode || 'design'}</dd>
          <dt>Duration</dt><dd>${durationLabel(item.take.duration)}</dd>
          <dt>Seed</dt><dd>${item.take.seed ?? 'Random'}</dd>` : nothing}</dl>
      <button type="button" class="icon-btn close" id="voice-details-close" aria-label="Close audio details" title="Close" @click=${() => this.closeDetails()}>
        <svg class="icon" aria-hidden="true"><use href="#i-x"></use></svg></button>
    </section>`;
  }

  renderTrackMenu(item) {
    const joined = this.selectedTakes.length > 1;
    const canReuse = !this.locked && !this.recording && !this.referenceBusy;
    const selectionReady = this.previewReady && this.previewSource === item.take.blob && !this.previewBusy;
    return html`<div class="menu-anchor">
      <button type="button" class="icon-btn" id="voice-track-toggle" aria-label="More actions" title="More actions"
        aria-controls="voice-track-menu" aria-expanded="false" @click=${() => toggleMenu(this.querySelector('#voice-track-menu'))}>
        <svg class="icon" aria-hidden="true"><use href="#i-more"></use></svg></button>
      <div id="voice-track-menu" class="voice-track-menu menu up" role="menu" aria-label="Audio actions" hidden>
        <button type="button" role="menuitem" id="voice-selected-reuse" ?disabled=${!canReuse}
          @click=${() => this.reuseSettings(item)}>Reuse script and voice</button>
        <button type="button" role="menuitem" id="voice-selected-video" ?disabled=${!selectionReady || this.locked}
          @click=${() => { closeMenus(); this.querySelector('audio-preview')?.action('video'); }}>Send to Video</button>
        <button type="button" role="menuitem" id="voice-selected-clone" ?disabled=${!selectionReady || !canReuse}
          @click=${() => { closeMenus(); this.querySelector('audio-preview')?.action('clone'); }}>Send to Clone</button>
        ${joined ? html`<button type="button" role="menuitem" @click=${() => { closeMenus(); this.playTrack(); }}>${this.playing ? 'Pause joined audio' : 'Play joined audio'}</button>
          <button type="button" role="menuitem" @click=${() => { closeMenus(); this.exportTrack(); }}>Download joined audio</button>` : nothing}
      </div></div>`;
  }

  renderDetails(item) {
    if (!item) return nothing;
    const {segment, take} = item;
    const selectionReady = this.previewReady && this.previewSource === take?.blob && !this.previewBusy;
    return html`<section class="stage-bar voice-output-details" id="voice-output-details" aria-label="Voice preview details">
      <div class="about">
        <p class="prompt-line voice-output-script" title=${segment.text} role="button" tabindex="0"
          aria-controls="voice-details-sheet" aria-expanded=${String(this.detailsOpen)} @click=${this.openDetails}
          @keydown=${event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopPropagation(); this.openDetails(event); } }}>${segment.text}</p>
        ${take?.voice ? html`<p class="prompt-line voice-output-description" title=${take.voice} role="button" tabindex="0"
          aria-controls="voice-details-sheet" aria-expanded=${String(this.detailsOpen)} @click=${this.openDetails}
          @keydown=${event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopPropagation(); this.openDetails(event); } }}><span class="caption">Voice description: </span>${take.voice}</p>` : nothing}
        <div class="facts num" aria-label="Voice metadata">
          <span>${take ? 'Audio ' + this.clipNumber(take) : 'Script'}</span>
          ${take ? html`<span>${durationLabel(take.duration)}</span><span>${take.model || 'AuK Flash'}</span>
            <span>${take.mode || 'design'}</span><span>${Number.isInteger(take.seed) ? 'Seed ' + take.seed : 'Random seed'}</span>
            ${Number.isFinite(take.elapsed) ? html`<span>Took ${durationLabel(take.elapsed)}</span>` : nothing}` : html`<span>Not generated</span>`}
        </div>
      </div>
      <div class="actions voice-output-actions">
        ${take && this.capabilities.modes.some(mode => mode.id === 'edit') ? html`          <button type="button" class="btn quiet" id="voice-selected-edit" ?disabled=${!selectionReady || this.locked}
            @click=${() => this.querySelector('audio-preview')?.action('edit')}>
            <svg class="icon" aria-hidden="true"><use href="#i-brush"></use></svg>Edit</button>` : nothing}
        ${take ? this.renderTrackMenu(item) : nothing}
        ${take ? html`<span class="rule" aria-hidden="true"></span>
          <button type="button" class="icon-btn" id="voice-selected-download" aria-label="Download audio" title="Download"
            ?disabled=${!selectionReady} @click=${() => this.querySelector('audio-preview')?.action('download')}>
            <svg class="icon" aria-hidden="true"><use href="#i-download"></use></svg></button>
          <button type="button" class="icon-btn danger" id="voice-selected-remove" aria-label="Remove audio" title="Remove"
            @click=${() => this.removeTake(take.id)}><svg class="icon" aria-hidden="true"><use href="#i-trash"></use></svg></button>` : nothing}
      </div>
    </section>`;
  }

  clipNumber(take) {
    const clips = this.segments.flatMap(segment => segment.takes).sort((first, second) => first.createdAt - second.createdAt);
    return clips.findIndex(clip => clip.id === take.id) + 1;
  }

  renderGallery(item) {
    const rendering = this.voiceRunning;
    const clips = this.segments.flatMap(segment => segment.takes.map(take => ({segment, take})));
    clips.sort((first, second) => (second.take?.createdAt ?? Infinity) - (first.take?.createdAt ?? Infinity));
    return html`<section class="strip-wrap voice-gallery" id="voice-gallery" aria-label="Voice gallery" ?hidden=${!clips.length && !rendering}>
      <div class="strip-head"><span>${this.takesCount} ${this.takesCount === 1 ? 'clip' : 'clips'}</span>
        <gallery-browser workspace="voice" .items=${clips.map(({segment, take}) => ({id: take.id,
          number: this.clipNumber(take), text: segment.text, description: take.voice, model: take.model,
          mode: take.mode, seed: take.seed, at: take.createdAt, duration: take.duration, peaks: take.peaks,
          batch: galleryBatch(take.id), downloadable: Boolean(take.blob)}))}
          .selectedId=${item?.take?.id} .keeping=${this.options.keeping?.() !== false}
          .pending=${rendering} .pendingSelected=${this.showingGeneration}
          .showPending=${() => { this.pausePlayback(); this.showGeneration = true; this.detailsOpen = false; }}
          .choose=${id => { const found = clips.find(({take}) => take.id === id); if (found) this.selectTake(found.segment.id, id); }}
          .removeItem=${id => { this.removeTake(id); return !this.segments.some(segment => segment.takes.some(take => take.id === id)); }}
          .download=${async ids => {
            for (const {segment, take} of clips.filter(({take}) => ids.includes(take.id))) {
              downloadAudio(take.blob, mediaDownloadName({kind: 'audio', text: segment.text,
                at: take.createdAt, id: take.id, extension: mediaExtension(take.blob.type, 'wav')}));
              await new Promise(resolve => setTimeout(resolve, 300));
            }
          }} .playback=${() => this.querySelector('audio-preview')?.play()}></gallery-browser>
        <span class="strip-actions"><button type="button" class="text-btn" ?disabled=${!this.takesCount} @click=${() => {
          if (confirm('Remove all completed audio clips from this browser?')) this.clearCompleted();
        }}>Clear all</button></span></div>
      <div class="strip voice-clips" role="group" aria-label="Generated audio" @keydown=${event => this.galleryKey(event)}>
        ${rendering ? html`<button type="button" class=${'frame pending voice-render-pending' + (this.showingGeneration ? ' selected' : '')}
          aria-label="Show audio generation" aria-pressed=${String(this.showingGeneration)}
          @click=${() => { this.pausePlayback(); this.showGeneration = true; this.detailsOpen = false; }}>
          <span class="still voice-clip-thumb"><span class="video-pending-indicator" aria-hidden="true"></span><span>Generating</span></span>
          <span class="no">${String(this.takesCount + 1).padStart(2, '0')}</span>${this.showingGeneration ? pencilLoop() : nothing}
        </button>` : nothing}
        ${clips.map(({segment, take}) => html`
          <button type="button" class=${'frame voice-clip' + (item?.take?.id === take.id && !this.showingGeneration ? ' selected' : '')}
            data-take-id=${take.id} data-segment-id=${segment.id} aria-pressed=${String(item?.take?.id === take.id && !this.showingGeneration)}
            aria-label=${'Select audio ' + this.clipNumber(take)} title=${segment.text}
            @click=${() => this.selectTake(segment.id, take.id)}>
            <span class="still voice-clip-thumb">${this.renderWaveform(take)}<span class="voice-clip-duration num">${durationLabel(take.duration)}</span></span>
            <span class="no">${String(this.clipNumber(take)).padStart(2, '0')}</span>${item?.take?.id === take.id && !this.showingGeneration ? pencilLoop(true) : nothing}</button>`)}
      </div>
    </section>`;
  }

  renderGeneration() {
    const operation = this.activeOperation?.kind === 'voice' ? this.activeOperation : null;
    const progress = operation?.progress || {};
    const percent = progress.total > 0 ? Math.max(0, Math.min(99, Math.round((progress.step || 0) / progress.total * 100))) : null;
    const editing = (operation?.mode || this.mode) === 'edit';
    let label = editing ? 'Editing audio' : 'Generating audio';
    if (!progress.step) label = 'Preparing audio';
    if (progress.total > 0 && progress.step >= progress.total) label = 'Finishing audio';
    let phase = !progress.step ? 'preparing' : progress.total > 0 && progress.step >= progress.total ? 'finishing' : 'generating';
    if (this.stopping || operation?.status === 'stopping') { label = 'Stopping audio'; phase = 'stopping'; }
    const bars = Array.from({length: 64}, (_, index) => {
      const height = 12 + Math.abs(Math.sin(index * 0.73) * Math.cos(index * 0.19)) * 68;
      return svg`<line x1=${index * 10 + 5} x2=${index * 10 + 5} y1=${50 - height / 2} y2=${50 + height / 2}
        style=${'--bar-delay: ' + (-index * 0.07).toFixed(2) + 's'}></line>`;
    });
    return html`<section class="voice-generation audio-preview" id="voice-generation" data-phase=${phase}
      aria-label="Audio generation">
      <div class="audio-preview-heading voice-generation-status"><strong>${label}</strong><span>${operation?.model || this.capabilities.name}</span></div>
      <div class="audio-preview-wave voice-generation-wave" role="progressbar" aria-label="Audio generation progress"
        aria-valuemin="0" aria-valuemax="100" aria-valuenow=${percent === null ? nothing : percent}
        aria-valuetext=${percent === null ? label : label + ', ' + percent + '%'}>
        <svg viewBox="0 0 640 100" preserveAspectRatio="none" aria-hidden="true">
          <defs><clipPath id="voice-generation-clip"><rect width=${percent === null ? 0 : percent * 6.4} height="100"></rect></clipPath></defs>
          <g class="voice-generation-bars voice-generation-outline">${bars}</g>
          <g class="voice-generation-bars voice-generation-fill" clip-path="url(#voice-generation-clip)">${bars}</g>
        </svg>
      </div>
      <p class="voice-generation-note">Illustrative waveform · ${phase === 'finishing' ? 'Saving your audio' : phase === 'stopping' ? 'Waiting for generation to stop' : 'Audio becomes playable when generation completes'}</p>
    </section>`;
  }

  render() {
    const item = this.previewItem;
    return html`<div class="voice-studio-shell" @dragover=${event => event.preventDefault()}
      @drop=${event => { event.preventDefault(); this.addReference(event.dataTransfer.files[0]); }}>
      <div class="voice-preview-area stage">
        <div id="voice-preview-pane">
          ${this.showingGeneration ? this.renderGeneration() : item?.take ? html`<audio-preview id="voice-audio-preview" class=${this.previewReady ? 'voice-result-ready' : ''} .blob=${item.take.blob}
            .downloadText=${item.segment.text} .downloadAt=${item.take.createdAt} .downloadId=${item.take.id} .speed=${this.previewSpeed}
            .label=${'Audio ' + this.clipNumber(item.take)}
            .locked=${this.locked} @audio-preview-play=${() => this.pausePlayback()}
            @audio-preview-action=${event => this.useSelection(event)}
            @audio-preview-state=${event => {
              this.previewSource = event.detail.blob;
              this.previewSpeed = event.detail.speed;
              this.previewReady = event.detail.ready;
              this.previewBusy = event.detail.busy;
            }}></audio-preview>` : html`
            <div class="voice-empty video-empty empty"><div class="video-empty-mark">AUDIO</div><strong>Preview audio</strong>
              <span>${item ? 'This segment has no audio yet.' : this.mode === 'edit' ? 'Add a reference recording and describe the change.' : this.hasParam('voice') ? 'Write a script, choose a voice and generate an audio clip.' : 'Write a script and generate an audio clip.'}</span>
              ${!item ? html`<button type="button" class="pill" @click=${() => document.getElementById('voice-text').focus()}>${this.mode === 'edit' ? 'Describe the change' : 'Write a script'}</button>` : nothing}
            </div>`}
        </div>
        ${this.showingGeneration ? nothing : this.renderDetails(item)}
        ${this.showingGeneration ? nothing : this.renderMetadata(item)}
      </div>
      ${this.renderGallery(item)}
    </div>`;
  }

}

customElements.define('voice-studio', VoiceStudio);
