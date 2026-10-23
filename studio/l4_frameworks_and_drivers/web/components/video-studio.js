import { LitElement, html, nothing, render as renderTemplate } from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import { closeMenus, menuItem, toggleMenu } from './popup-menu.js';
import {mediaDownloadName, mediaExtension} from '../lib/download-name.js';
import {pencilLoop} from './gallery-marker.js';
import './gallery-browser.js';
import {galleryBatch, galleryView, rememberGalleryView} from '../lib/gallery-view.js';

let nextClipId = 1;

function formatTime(seconds) {
  const tenths = Math.floor(Math.max(0, seconds) * 10);
  const minutes = Math.floor(tenths / 600);
  const wholeSeconds = Math.floor(tenths / 10) % 60;
  return String(minutes).padStart(2, '0') + ':'
    + String(wholeSeconds).padStart(2, '0') + '.' + tenths % 10;
}

function readDataUrl(file) {
  return new Promise(function (resolve, reject) {
    const reader = new FileReader();
    reader.onload = function () { resolve(reader.result); };
    reader.onerror = function () { reject(reader.error || new Error('The image could not be read.')); };
    reader.readAsDataURL(file);
  });
}

function isImageFile(file) {
  return file.type.startsWith('image/') || /\.(png|jpe?g|gif|webp|bmp|tiff?)$/i.test(file.name);
}

function isVideoFile(file) {
  return file.type.startsWith('video/') || /\.(mp4|m4v|mov|webm|ogv)$/i.test(file.name);
}

function isAudioFile(file) {
  return file.type.startsWith('audio/') || /\.(wav|mp3|flac|ogg|oga|m4a|aac|aiff?)$/i.test(file.name);
}

function base64OfBytes(bytes) {
  let binary = '';
  const chunk = 0x8000;
  for (let index = 0; index < bytes.length; index += chunk) {
    binary += String.fromCharCode.apply(null, bytes.subarray(index, index + chunk));
  }
  return btoa(binary);
}

function videoMetadata(settings, result = {}) {
  const references = Array.isArray(settings.references) ? settings.references : [];
  const seed = result.seed ?? settings.seed ?? null;
  return {
    operationId: settings.operationId || '',
    backend: settings.backend || '',
    modelName: settings.modelName || 'Video',
    precision: settings.precision || '',
    fastMode: Boolean(settings.fastMode ?? settings.fast_mode),
    mode: settings.mode || 'generate',
    effect: settings.adapter || '',
    effectFile: settings.effectFile || '',
    effectStrength: settings.effectStrength ?? null,
    stage2: settings.stage2 ?? null,
    prompt: settings.prompt || '',
    pipeline: settings.pipeline || '',
    audio: settings.audioName || '',
    look: settings.look || '',
    width: Number(result.width ?? settings.width ?? 0),
    height: Number(result.height ?? settings.height ?? 0),
    numFrames: Number(result.num_frames ?? settings.numFrames ?? 0),
    frameRate: Number(result.frame_rate ?? settings.frameRate ?? 0),
    seed: Number.isInteger(seed) ? seed : null,
    elapsedSeconds: Number(settings.elapsedSeconds) || 0,
    references: references,
  };
}

async function createVideoThumbnail(sourceUrl) {
  const video = document.createElement('video');
  video.muted = true;
  video.preload = 'auto';
  const frameReady = new Promise(function (resolve, reject) {
    video.addEventListener('loadeddata', resolve, { once: true });
    video.addEventListener('error', function () {
      reject(new Error('The video could not be decoded for its thumbnail.'));
    }, { once: true });
  });
  let timeoutId;
  video.src = sourceUrl;
  video.load();
  try {
    const timeout = new Promise(function (resolve, reject) {
      timeoutId = window.setTimeout(function () {
        reject(new Error('The video thumbnail took too long to load.'));
      }, 10000);
    });
    await Promise.race([frameReady, timeout]);
    if (!video.videoWidth || !video.videoHeight) {
      throw new Error('The video has no frame for its thumbnail.');
    }
    await seekThumbnailFrame(video);
    const scale = Math.min(1, 240 / video.videoWidth, 320 / video.videoHeight);
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
    canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
    const context = canvas.getContext('2d');
    if (!context) throw new Error('The video thumbnail canvas is unavailable.');
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    const thumbnail = await new Promise(function (resolve, reject) {
      canvas.toBlob(function (blob) {
        if (blob) resolve(blob);
        else reject(new Error('The video thumbnail could not be saved.'));
      }, 'image/jpeg', 0.78);
    });
    return thumbnail;
  } finally {
    window.clearTimeout(timeoutId);
    video.pause();
    video.removeAttribute('src');
    video.load();
  }
}

function seekThumbnailFrame(video) {
  const targetTime = video.duration * 0.65;
  if (!Number.isFinite(targetTime) || targetTime < 0.05) return Promise.resolve();
  return new Promise(function (resolve) {
    let timeoutId;
    const finish = function () {
      window.clearTimeout(timeoutId);
      video.removeEventListener('seeked', finish);
      resolve();
    };
    video.addEventListener('seeked', finish, {once: true});
    timeoutId = window.setTimeout(finish, 1500);
    try {
      video.currentTime = targetTime;
    } catch {
      finish();
    }
  });
}

function releaseClipUrls(clip) {
  if (clip.objectUrl) URL.revokeObjectURL(clip.url);
  if (clip.thumbnailUrl) URL.revokeObjectURL(clip.thumbnailUrl);
}

function videoDownloadName(clip) {
  return mediaDownloadName({kind: 'video', text: clip.metadata?.prompt || clip.name,
    at: clip.createdAt, id: clip.id, extension: mediaExtension(clip.mp4Blob?.type, 'mp4')});
}

function saveFile(url, name) {
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
}

function waitBetweenDownloads() {
  return new Promise((resolve) => setTimeout(resolve, 300));
}

function videoExportMetadata(clip, file) {
  const metadata = clip.metadata || {};
  return {
    file: file,
    prompt: metadata.prompt || '',
    model: metadata.modelName || '',
    modelId: metadata.backend || '',
    precision: metadata.precision || '',
    mode: metadata.mode || '',
    effect: metadata.effect || '',
    effectFile: metadata.effectFile || '',
    effectStrength: metadata.effectStrength ?? null,
    stage2: metadata.stage2 ?? null,
    pipeline: metadata.pipeline || '',
    audio: metadata.audio || '',
    look: metadata.look || '',
    references: metadata.references || [],
    durationSeconds: clip.duration,
    width: metadata.width || clip.width || null,
    height: metadata.height || clip.height || null,
    frameRate: metadata.frameRate || null,
    frames: metadata.numFrames || null,
    seed: Number.isInteger(metadata.seed) ? metadata.seed : null,
    elapsedSeconds: metadata.elapsedSeconds || null,
  };
}

class VideoStudio extends LitElement {
  clips = [];
  imageReferences = [];
  // The track a generate run follows, as the file the person chose. The form keeps the file
  // rather than its bytes: a three minute track is read once, when the run is sent.
  audio = null;
  // Set by the page from the mode. An edit changes a clip and takes no image references, so
  // the media door refuses an image while it is on.
  needsClip = false;
  galleryStore = null;
  keepEnabled = true;
  // Whether the browser promised to keep the store. `null` is "not asked yet"; the gallery's
  // note says so only when the answer is a refusal and there is something saved.
  storagePersisted = null;
  generationProgress = null;
  generationEpoch = 0;
  pendingRender = null;
  // Whether a run in flight owns the screen. A new run takes it, and picking a clip
  // takes it back, so the render keeps going while an older clip is on the monitor.
  showRender = true;
  previewResume = null;
  sourcePanel = null;
  selectedReferenceId = null;
  // What the monitor shows, and, separately, the clip an edit would change. A finished run
  // moves the first and never the second: showing is not picking.
  selectedClipId = null;
  editTargetId = null;
  maxReferences = null;
  minReferenceStrength = null;
  maxReferenceStrength = null;
  referenceStrengthStep = null;
  defaultReferenceStrength = null;
  supportsSeed = false;
  currentTime = 0;
  duration = 0;
  frameLimit = null;
  outputWidth = 16;
  outputHeight = 9;
  outputFrameRate = 24;
  outputModelName = 'Video';
  previewResizeObserver = null;
  outputPromptResizeObserver = new ResizeObserver((observations) => {
    observations.forEach((observation) => this.markOutputPrompt(observation.target));
  });
  observedOutputPrompt = null;
  error = '';
  handleSourceClick = (event) => this.onComponentClick(event);
  handleSourceChange = (event) => this.onComponentChange(event);
  handleSourceInput = (event) => this.onComponentInput(event);
  handleSourceKeydown = (event) => this.onSourceKeydown(event);
  handleSourceDragOver = (event) => this.onSourceDragOver(event);
  handleSourceDragLeave = (event) => this.onSourceDragLeave(event);
  handleSourceDrop = (event) => this.onSourceDrop(event);
  handleDocumentPaste = (event) => this.onPaste(event);
  handleDocumentKeydown = (event) => this.onShortcutPaste(event);
  handleVideoFullscreenChange = () => this.onVideoFullscreenChange();

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    this.sourcePanel = document.getElementById('video-source-panel');
    this.addEventListener('click', this.onComponentClick);
    this.addEventListener('keydown', this.onOutputKeydown);
    document.addEventListener('fullscreenchange', this.handleVideoFullscreenChange);
    this.addEventListener('change', this.onComponentChange);
    this.addEventListener('input', this.onComponentInput);
    this.addEventListener('loadedmetadata', this.onMetadata, true);
    this.addEventListener('timeupdate', this.onTimeUpdate, true);
    document.addEventListener('paste', this.handleDocumentPaste);
    document.addEventListener('keydown', this.handleDocumentKeydown);
    if (this.sourcePanel) {
      this.sourcePanel.addEventListener('click', this.handleSourceClick);
      this.sourcePanel.addEventListener('change', this.handleSourceChange);
      this.sourcePanel.addEventListener('input', this.handleSourceInput);
      this.sourcePanel.addEventListener('keydown', this.handleSourceKeydown);
      this.sourcePanel.addEventListener('dragover', this.handleSourceDragOver);
      this.sourcePanel.addEventListener('dragleave', this.handleSourceDragLeave);
      this.sourcePanel.addEventListener('drop', this.handleSourceDrop);
    }
  }

  disconnectedCallback() {
    this.removeEventListener('click', this.onComponentClick);
    this.removeEventListener('keydown', this.onOutputKeydown);
    document.removeEventListener('fullscreenchange', this.handleVideoFullscreenChange);
    this.removeEventListener('change', this.onComponentChange);
    this.removeEventListener('input', this.onComponentInput);
    this.removeEventListener('loadedmetadata', this.onMetadata, true);
    this.removeEventListener('timeupdate', this.onTimeUpdate, true);
    document.removeEventListener('paste', this.handleDocumentPaste);
    document.removeEventListener('keydown', this.handleDocumentKeydown);
    if (this.sourcePanel) {
      this.sourcePanel.removeEventListener('click', this.handleSourceClick);
      this.sourcePanel.removeEventListener('change', this.handleSourceChange);
      this.sourcePanel.removeEventListener('input', this.handleSourceInput);
      this.sourcePanel.removeEventListener('keydown', this.handleSourceKeydown);
      this.sourcePanel.removeEventListener('dragover', this.handleSourceDragOver);
      this.sourcePanel.removeEventListener('dragleave', this.handleSourceDragLeave);
      this.sourcePanel.removeEventListener('drop', this.handleSourceDrop);
    }
    if (this.previewResizeObserver) this.previewResizeObserver.disconnect();
    this.outputPromptResizeObserver.disconnect();
    this.observedOutputPrompt = null;
    super.disconnectedCallback();
    this.clips.forEach(releaseClipUrls);
  }

  firstUpdated() {
    this.renderImageReferences();
    this.renderSourceVideos();
    this.renderSelectedClip();
    const preview = this.querySelector('#video-preview-root');
    if (preview) {
      this.previewResizeObserver = new ResizeObserver(() => this.fitVideoMonitor());
      this.previewResizeObserver.observe(preview);
    }
  }

  async setGalleryStore(store, keeping) {
    this.galleryStore = store;
    this.keepEnabled = keeping;
    if (!keeping) return;
    const restore = !this.galleryRestored && !this.clips.length;
    const preferred = restore ? galleryView('video').selected : null;
    this.galleryRestored = true;
    await this.updateComplete;
    const records = await store.loadVideos();
    records.forEach((record) => {
      if (store.videoWasRemoved?.(record)) return;
      const existing = this.clips.find((clip) => clip.id === record.id);
      if (existing) {
        if (record.nativeMetadata && !existing.nativeMetadata) {
          Object.assign(existing, {metadata: record.metadata, nativeMetadata: true, keptInBrowser: true});
          this.renderOutputDetails();
          this.renderVideoGallery();
        }
        return;
      }
      const clip = {
        id: record.id,
        kind: 'generated',
        name: record.name,
        url: URL.createObjectURL(record.mp4),
        objectUrl: true,
        mp4Blob: record.mp4,
        thumbnailUrl: record.thumbnail ? URL.createObjectURL(record.thumbnail) : null,
        thumbnailBlob: record.thumbnail,
        duration: record.duration,
        metadata: record.metadata,
        createdAt: record.createdAt,
        nativeMetadata: record.nativeMetadata,
        keptInBrowser: true,
      };
      this.addClip(clip);
      if (!clip.thumbnailBlob) this.createThumbnail(clip);
    });
    if (restore && this.clips.some(clip => clip.id === preferred)) this.selectClip(preferred);
  }

  setStoragePersisted(value) {
    this.storagePersisted = value;
    this.renderVideoGallery();
  }

  setKeeping(keeping) {
    this.keepEnabled = keeping;
    rememberGalleryView('video', {}, keeping);
    if (!keeping) {
      this.clips.forEach((clip) => { clip.keptInBrowser = false; });
      this.renderVideoGallery();
      return Promise.resolve();
    }
    return this.persistGeneratedVideos().then(() => this.renderVideoGallery());
  }

  persistGeneratedVideos() {
    const saves = this.clips.filter((clip) => clip.kind === 'generated' && !clip.stub)
      .map(async (clip) => { clip.keptInBrowser = await this.persistVideo(clip); });
    return Promise.all(saves);
  }

  persistVideo(clip) {
    if (!this.keepEnabled || !this.galleryStore) return Promise.resolve(false);
    return this.galleryStore.keepVideo(clip, clip.mp4Blob, clip.thumbnailBlob).then((kept) => {
      clip.keptInBrowser = kept;
      return kept;
    });
  }

  createThumbnail(clip) {
    // A source clip wants one too, and a redraw arrives per state change, so the flag
    // keeps a second capture off a clip whose first one is still running.
    if (clip.thumbnailPending) return;
    clip.thumbnailPending = true;
    createVideoThumbnail(clip.url).then((thumbnail) => {
      clip.thumbnailPending = false;
      if (!this.isConnected || !this.clips.includes(clip)) return;
      clip.thumbnailBlob = thumbnail;
      clip.thumbnailUrl = URL.createObjectURL(thumbnail);
      if (clip.kind === 'source') this.renderSourceVideos();
      else this.renderVideoGallery();
      // Only a generated clip is kept, so only it has a stored thumbnail to write.
      if (clip.kind === 'generated' && this.keepEnabled && this.galleryStore) {
        this.galleryStore.keepVideoThumbnail(clip.id, thumbnail);
      }
    }).catch((error) => {
      clip.thumbnailPending = false;
      clip.thumbnailError = error.message;
      if (clip.kind === 'source') this.renderSourceVideos();
      else this.renderVideoGallery();
    });
  }

  setGenerationProgress(state, elapsedSeconds, outputShape) {
    if (state?.running && !this.generationProgress) {
      this.generationEpoch += 1;
      this.showRender = true;
      const video = this.querySelector('#video-preview');
      if (video) this.previewResume = {clipId: this.selectedClipId, time: video.currentTime};
    }
    if (outputShape && outputShape.width > 0 && outputShape.height > 0) {
      this.outputWidth = outputShape.width;
      this.outputHeight = outputShape.height;
      this.outputModelName = outputShape.modelName || this.outputModelName;
    }
    if (!state) {
      this.generationProgress = null;
      this.pendingRender = null;
    } else if (state.running) {
      this.generationProgress = {
        stage: state.stage,
        step: state.step,
        total: state.total,
        phase: state.phase,
        stopping: Boolean(state.stopping),
        elapsedSeconds: elapsedSeconds,
      };
      this.pendingRender = {
        ...(this.pendingRender || {}),
        ...(outputShape || {}),
        elapsedSeconds: elapsedSeconds,
        modelName: this.outputModelName,
      };
    }
    this.renderPreview();
    this.renderVideoGallery();
    this.renderOutputDetails();
  }

  setCancelRequested(stopping) {
    if (!this.generationProgress) return;
    this.generationProgress.stopping = stopping;
    this.renderPreview();
    this.renderVideoGallery();
  }

  inputsChanged() {
    document.dispatchEvent(new CustomEvent('draft-change', {detail: 'video'}));
  }

  inputSnapshot() {
    const clip = this.clips.find(item => item.id === this.editTargetId);
    return {imageReferences: this.imageReferences, audio: this.audio,
      clip: clip ? {id: clip.id, kind: clip.kind, name: clip.name, duration: clip.duration,
        metadata: clip.metadata, createdAt: clip.createdAt, nativeMetadata: clip.nativeMetadata,
        stub: clip.stub, file: clip.file || clip.mp4Blob} : null};
  }

  restoreInputs(snapshot) {
    this.imageReferences = snapshot.imageReferences || [];
    this.selectedReferenceId = this.imageReferences[0]?.id || null;
    this.audio = snapshot.audio || null;
    const target = snapshot.clip;
    this.editTargetId = null;
    if (target && !this.galleryStore?.videoWasRemoved?.(target)) {
      const existing = this.clips.find(clip => clip.id === target.id);
      if (!existing) this.clips = this.clips.concat({...target,
        url: target.file ? URL.createObjectURL(target.file) : null, objectUrl: Boolean(target.file),
        mp4Blob: target.kind === 'generated' ? target.file : null});
      this.editTargetId = target.id;
      this.selectedClipId = target.id;
    }
    [...this.imageReferences, ...(target ? [target] : [])].forEach(item => {
      nextClipId = Math.max(nextClipId, Number(item.id.split('-').at(-1)) + 1 || 1);
    });
    this.renderImageReferences();
    this.renderAudio();
    this.renderSourceVideos();
    this.renderSelectedClip();
    this.announceSelection();
  }

  captureInputEpoch() {
    return this.generationProgress ? null : this.generationEpoch;
  }

  canCommitInput(epoch) {
    return epoch !== null && !this.generationProgress && epoch === this.generationEpoch;
  }

  addImageReference(reference, epoch = this.captureInputEpoch()) {
    if (!this.canCommitInput(epoch)) return;
    if (this.imageReferences.some(function (saved) { return saved.id === reference.id; })) return;
    // The same frame twice adds nothing, and a capture names its frame by clip and time, so a
    // repeated name is the same frame.
    if (this.imageReferences.some(function (saved) { return saved.name === reference.name; })) {
      this.setError('That frame is already a reference.');
      return;
    }
    if (this.maxReferences !== null && this.imageReferences.length >= this.maxReferences) {
      this.setError('This video model accepts at most ' + this.maxReferences + ' image references.');
      return;
    }
    this.clearError();
    this.imageReferences = this.imageReferences.concat({
      id: reference.id,
      name: reference.name,
      src: reference.src,
      base64: reference.base64,
      frameIndex: Number.isInteger(reference.frameIndex) ? reference.frameIndex : 0,
      strength: this.normalizeReferenceStrength(reference.strength),
    });
    if (!this.selectedReferenceId) this.selectedReferenceId = reference.id;
    this.renderImageReferences();
    this.inputsChanged();
  }

  removeImageReference(id) {
    this.imageReferences = this.imageReferences.filter(function (reference) { return reference.id !== id; });
    if (this.selectedReferenceId === id) {
      this.selectedReferenceId = this.imageReferences.length ? this.imageReferences[0].id : null;
    }
    this.renderImageReferences();
    this.inputsChanged();
  }

  clearImageReferences() {
    this.imageReferences = [];
    this.selectedReferenceId = null;
    this.renderImageReferences();
    this.inputsChanged();
  }

  addAudioFile(file, epoch = this.captureInputEpoch()) {
    if (!this.canCommitInput(epoch)) return false;
    // The track is a generate input: an edit's whole input is the clip it was handed.
    if (this.needsClip) {
      this.setError('An edit changes a clip. Audio is a Generate input.');
      return false;
    }
    // The same track twice is the same refusal, named by the file's own identity: a name
    // alone would refuse two different tracks that happen to share one.
    if (this.audio && this.audio.name === file.name && this.audio.size === file.size) {
      this.setError('That track is already here.');
      return false;
    }
    // One track is one timing, and a second would have to fight the first for it.
    if (this.audio) {
      this.setError('One audio track at a time. Remove the current track first.');
      return false;
    }
    this.audio = { name: file.name, size: file.size, file: file };
    this.clearError();
    this.renderAudio();
    this.renderMediaEmptyState();
    this.inputsChanged();
    return true;
  }

  clearAudio() {
    if (!this.audio) return;
    this.audio = null;
    this.renderAudio();
    this.renderMediaEmptyState();
    this.inputsChanged();
  }

  async audioPayload() {
    if (!this.audio) return undefined;
    const bytes = new Uint8Array(await this.audio.file.arrayBuffer());
    return { name: this.audio.name, data: base64OfBytes(bytes) };
  }

  renderAudio() {
    const tray = document.getElementById('video-audio-tray');
    const list = document.getElementById('video-audios');
    if (!tray || !list) return;
    tray.hidden = this.needsClip || !this.audio;
    list.replaceChildren();
    if (!this.audio) return;
    const row = document.createElement('div');
    row.className = 'video-audio';
    row.title = this.audio.name;
    const picture = document.createElement('div');
    picture.className = 'video-audio-picture';
    const badge = document.createElement('span');
    badge.className = 'video-audio-badge';
    badge.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-music"/></svg>';
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'video-audio-remove';
    remove.dataset.action = 'remove-audio';
    remove.setAttribute('aria-label', 'Remove audio ' + this.audio.name);
    remove.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-x"/></svg>';
    picture.append(badge, remove);
    const name = document.createElement('span');
    name.className = 'video-audio-name';
    name.textContent = this.audio.name;
    row.append(picture, name);
    list.append(row);
  }

  selectReference(id) {
    if (!this.imageReferences.some(function (reference) { return reference.id === id; })) return;
    this.selectedReferenceId = id;
    this.renderImageReferences();
  }

  setFrameLimit(frameCount) {
    if (!Number.isInteger(frameCount) || frameCount < 1) return 0;
    this.frameLimit = frameCount;
    const lastFrame = frameCount - 1;
    let movedReferences = 0;
    this.imageReferences = this.imageReferences.map((reference) => {
      const frameIndex = Number.isInteger(reference.frameIndex) ? reference.frameIndex : 0;
      const validFrame = Math.min(lastFrame, Math.max(0, frameIndex));
      if (frameIndex === validFrame) return reference;
      movedReferences += 1;
      return {...reference, frameIndex: validFrame};
    });
    if (movedReferences) this.renderImageReferences();
    return movedReferences;
  }

  setModelCapabilities(capabilities) {
    this.outputFrameRate = capabilities.frame_rate;
    this.maxReferences = capabilities.max_references;
    this.minReferenceStrength = capabilities.min_reference_strength;
    this.maxReferenceStrength = capabilities.max_reference_strength;
    this.referenceStrengthStep = capabilities.reference_strength_step;
    this.defaultReferenceStrength = capabilities.default_reference_strength;
    this.supportsSeed = capabilities.min_seed !== null && capabilities.max_seed !== null;
    this.imageReferences = this.imageReferences.map((reference) => ({
      ...reference,
      strength: this.normalizeReferenceStrength(reference.strength),
    }));
    this.renderImageReferences();
  }

  normalizeReferenceStrength(value) {
    const strength = Number.isFinite(value) ? value : this.defaultReferenceStrength;
    if (this.minReferenceStrength === null || this.maxReferenceStrength === null) return strength;
    return Math.min(this.maxReferenceStrength, Math.max(this.minReferenceStrength, strength));
  }

  setReferenceStrength(id, control) {
    const reference = this.imageReferences.find((item) => item.id === id);
    if (!reference) return;
    reference.strength = Number(control.value);
    control.nextElementSibling.textContent = reference.strength.toFixed(2);
  }

  renderImageReferences() {
    const list = document.getElementById('video-references');
    const count = document.getElementById('video-reference-count');
    if (!list || !count) return;
    count.textContent = this.imageReferences.length
      + (this.imageReferences.length === 1 ? ' image' : ' images');
    list.replaceChildren();
    if (!this.imageReferences.length) {
      this.renderMediaEmptyState();
      return;
    }
    this.imageReferences.forEach((reference) => {
      const card = document.createElement('div');
      card.className = 'video-reference';
      if (reference.id === this.selectedReferenceId) card.classList.add('selected');
      card.title = reference.name;
      const image = document.createElement('img');
      image.src = reference.src;
      image.alt = reference.name;
      const select = document.createElement('button');
      select.type = 'button';
      select.className = 'video-reference-select';
      select.dataset.action = 'select-reference';
      select.dataset.referenceId = reference.id;
      select.setAttribute('aria-label', 'Select reference ' + reference.name);
      select.setAttribute('aria-pressed', String(reference.id === this.selectedReferenceId));
      select.append(image);
      const remove = document.createElement('button');
      remove.className = 'video-reference-remove';
      remove.type = 'button';
      remove.dataset.action = 'remove-reference';
      remove.dataset.referenceId = reference.id;
      remove.setAttribute('aria-label', 'Remove video reference ' + reference.name);
      remove.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-x"/></svg>';
      // The print and its remove travel together, so the circle sits on the picture's own
      // corner however the row is padded.
      const picture = document.createElement('div');
      picture.className = 'video-reference-picture';
      picture.append(select, remove);
      const name = document.createElement('span');
      name.className = 'video-reference-name';
      name.textContent = reference.name;
      // No influence dial: every measured run used the model's own reference strength, and a
      // second knob on each reference read as a form inside a form.
      card.append(picture, name);
      list.append(card);
    });
    this.renderMediaEmptyState();
  }

  renderSourceVideos() {
    const list = document.getElementById('video-source-list');
    const count = document.getElementById('video-source-count');
    if (!list || !count) return;
    // An explicit edit target can be an upload or a generated clip from the gallery.
    const sources = this.shownClips();
    count.textContent = sources.length + (sources.length === 1 ? ' clip' : ' clips');
    list.replaceChildren();
    if (!sources.length) {
      this.renderMediaEmptyState();
      return;
    }
    sources.forEach((clip) => {
      const item = document.createElement('div');
      item.className = 'video-source-item';
      // The highlight covers the whole row, the delete button included. It sat on the
      // select alone, and that button is a column beside it, so the colour stopped short.
      if (clip.id === this.selectedClipId) item.classList.add('selected');
      const select = document.createElement('button');
      select.type = 'button';
      select.className = 'video-source';
      select.dataset.action = 'select-clip';
      select.dataset.clipId = clip.id;
      select.setAttribute('aria-label', 'Select source video ' + clip.name);
      select.setAttribute('aria-pressed', String(clip.id === this.selectedClipId));
      const thumbnail = document.createElement('span');
      thumbnail.className = 'video-source-thumb';
      if (clip.thumbnailUrl) {
        const picture = document.createElement('img');
        picture.src = clip.thumbnailUrl;
        picture.alt = '';
        thumbnail.append(picture);
      } else {
        thumbnail.textContent = 'VIDEO';
      }
      const name = document.createElement('span');
      name.className = 'video-source-name';
      name.textContent = clip.name;
      const duration = document.createElement('span');
      duration.className = 'video-source-duration';
      duration.textContent = clip.duration ? formatTime(clip.duration) : 'Loading';
      const picture = document.createElement('span');
      picture.className = 'video-source-picture';
      picture.append(thumbnail);
      select.append(picture, name, duration);
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'video-source-remove';
      remove.dataset.action = 'clear-edit-target';
      remove.dataset.clipId = clip.id;
      remove.setAttribute('aria-label', 'Remove source video ' + clip.name);
      remove.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-x"/></svg>';
      item.append(select, remove);
      list.append(item);
      // The first frame of an added video, once its metadata lets the element seek.
      if (!clip.thumbnailUrl && !clip.thumbnailError) this.createThumbnail(clip);
    });
    this.renderMediaEmptyState();
  }

  // What the slot lists: every source clip in Generate, and the edit's one target in Edit.
  // The empty state is drawn from this same list, because the two must agree: it used to ask
  // for a source clip, so an edit whose target was a generated clip drew its row into a group
  // this function then hid, and the panel said Add the clip to edit over a clip in hand.
  shownClips() {
    // Generate takes images; a clip is an edit input and nothing else. The clip panel exists
    // only where the mode reads it.
    if (!this.needsClip) return [];
    return this.clips.filter((clip) => clip.id === this.editTargetId);
  }

  renderMediaEmptyState() {
    const sourceGroup = document.getElementById('video-source-group');
    const referenceTray = document.getElementById('video-reference-tray');
    const emptyState = document.getElementById('video-media-empty');
    if (!sourceGroup || !referenceTray || !emptyState) return;
    const hasClips = this.shownClips().length > 0;
    // An edit takes no image references, so one left from Generate stays out of its panel.
    const hasReferences = (!this.needsClip || this.maxReferences > 0) && this.imageReferences.length > 0;
    const hasAudio = !this.needsClip && Boolean(this.audio);
    sourceGroup.hidden = !hasClips;
    referenceTray.hidden = !hasReferences;
    emptyState.hidden = hasClips || hasReferences || hasAudio;
  }

  requestPayload(settings) {
    return {
      // Which mode the form is in, and what an edit carries: the adapter, how hard it is
      // applied, and the clip it changes. A generate run sends the mode alone.
      mode: settings.mode || 'generate',
      adapter: settings.adapter || '',
      adapter_strength: settings.adapterStrength,
      clip: settings.clip,
      audio: settings.audio,
      prompt: settings.prompt,
      backend: settings.backend,
      request_id: settings.requestId,
      width: settings.width,
      height: settings.height,
      num_frames: settings.numFrames,
      frame_rate: settings.frameRate,
      seed: settings.seed,
      // The backend enhances new prompts and recognizes exact native Rewrite outputs.
      enhance: true,
      fast_mode: Boolean(settings.fastMode),
      // A mode that takes no image references sends none, whatever the generate form left
      // behind: references are a generate input, and the clip is the edit's.
      references: settings.maxReferences > 0 ? this.imageReferences.map(function (reference) {
        return {
          name: reference.name,
          image: reference.base64,
          frame_index: reference.frameIndex,
          strength: reference.strength,
        };
      }) : [],
    };
  }

  clearError() {
    this.error = '';
  }

  // A failure goes to the toast host, the page's one surface for it: the inline paragraph in
  // the strip was below the preview and behind the gallery, and nobody reads it there.
  setError(message) {
    this.error = message;
    this.dispatchEvent(new CustomEvent('video-error', { detail: { message }, bubbles: true, composed: true }));
  }

  async addGeneratedClip(blob, settings) {
    const id = settings.operationId ? 'video-operation-' + settings.operationId : 'video-' + crypto.randomUUID();
    const createdAt = settings.createdAt || Date.now();
    if (this.galleryStore?.videoWasRemoved?.({id, createdAt})) return false;
    const existing = this.clips.find((clip) => clip.id === id);
    if (existing) {
      if (settings.nativeMetadata && !existing.nativeMetadata) {
        Object.assign(existing, {metadata: videoMetadata(settings), nativeMetadata: true});
        await this.persistVideo(existing);
        this.renderOutputDetails();
      }
      return existing;
    }
    const metadata = videoMetadata(settings);
    const clip = {
      id,
      kind: 'generated',
      name: metadata.modelName + ' ' + Math.round(settings.duration) + 's',
      url: URL.createObjectURL(blob),
      objectUrl: true,
      mp4Blob: blob,
      thumbnailBlob: null,
      duration: metadata.numFrames / metadata.frameRate,
      metadata: metadata,
      createdAt,
      nativeMetadata: settings.nativeMetadata === true,
    };
    this.addClip(clip);
    const saved = await this.persistVideo(clip);
    this.renderVideoGallery();
    this.createThumbnail(clip);
    return saved;
  }

  addStubClip(result, settings) {
    const id = settings.operationId ? 'video-operation-' + settings.operationId : 'clip-' + nextClipId++;
    const createdAt = settings.createdAt || Date.now();
    if (this.galleryStore?.videoWasRemoved?.({id, createdAt})) return false;
    const existing = this.clips.find((clip) => clip.id === id);
    if (existing) {
      if (settings.nativeMetadata && !existing.nativeMetadata) {
        Object.assign(existing, {metadata: videoMetadata(settings, result), nativeMetadata: true});
        this.renderOutputDetails();
      }
      return existing;
    }
    const duration = result.num_frames / result.frame_rate;
    const metadata = videoMetadata(settings, result);
    this.addClip({
      id,
      kind: 'generated',
      name: metadata.modelName + ' stub ' + Math.round(duration) + 's',
      url: null,
      objectUrl: false,
      duration: duration,
      stub: true,
      metadata: metadata,
      createdAt,
      nativeMetadata: settings.nativeMetadata === true,
    });
  }

  addClip(clip) {
    this.clips = this.clips.concat(clip);
    this.selectedClipId = clip.id;
    this.previewResume = null;
    this.currentTime = 0;
    this.duration = clip.duration || 0;
    this.pendingRender = null;
    this.error = '';
    this.renderSourceVideos();
    this.renderSelectedClip();
    // No announcement: a finished run shows its clip, and showing is not picking. The edit
    // target comes from an upload or Edit this clip.
  }

  onComponentClick(event) {
    if (!(event.target instanceof Element)) return;
    const control = event.target.closest('[data-action]');
    if (!control) return;
    const action = control.dataset.action;
    if (action === 'open-output-prompt') this.openOutputPromptSheet();
    if (action === 'close-output-prompt') this.closeOutputPromptSheet();
    if (action === 'toggle-video-fullscreen') this.toggleVideoFullscreen();
    if (action === 'toggle-output-menu') {
      const menu = this.querySelector('#video-output-menu');
      if (menu) toggleMenu(menu);
    }
    if (action === 'add-media') this.openMediaChooser();
    if (action === 'remove-reference') this.removeImageReference(control.dataset.referenceId);
    if (action === 'select-reference') this.selectReference(control.dataset.referenceId);
    if (action === 'remove-clip') this.removeClip(control.dataset.clipId);
    if (action === 'clear-edit-target') this.clearEditTarget();
    if (action === 'remove-audio') this.clearAudio();
    if (action === 'download-all-videos') this.downloadAllVideos();
    if (action === 'clear-video-gallery') this.clearVideoGallery();
    if (action === 'select-clip') this.selectClip(control.dataset.clipId);
    if (action === 'show-render') this.showRenderMonitor();
    if (action === 'capture-video-frame') this.captureFrameForVideo();
    if (action === 'edit-this-clip') this.editThisClip(control.dataset.clipId);
    if (action === 'capture-image-frame') this.captureFrameForImage();
  }

  onOutputKeydown(event) {
    if (event.key === 'Escape' && this.querySelector('#video-prompt-sheet')) {
      event.preventDefault();
      event.stopPropagation();
      this.closeOutputPromptSheet();
      return;
    }
    const prompt = event.target instanceof Element
      ? event.target.closest('.video-output-prompt[role="button"]') : null;
    if (!prompt || (event.key !== 'Enter' && event.key !== ' ')) return;
    event.preventDefault();
    this.openOutputPromptSheet();
  }

  openOutputPromptSheet() {
    const prompt = this.querySelector('.video-output-prompt');
    const preview = this.querySelector('#video-preview-root');
    if (!prompt || !prompt.hasAttribute('role') || !preview || this.querySelector('#video-prompt-sheet')) return;
    const sheet = document.createElement('div');
    sheet.id = 'video-prompt-sheet';
    sheet.className = 'sheet';
    sheet.setAttribute('role', 'region');
    sheet.setAttribute('aria-label', 'The whole prompt');
    const list = document.createElement('dl');
    const label = document.createElement('dt');
    label.textContent = 'Prompt';
    const fullPrompt = document.createElement('dd');
    fullPrompt.textContent = prompt.textContent;
    list.append(label, fullPrompt);
    const close = document.createElement('button');
    close.className = 'icon-btn close';
    close.type = 'button';
    close.dataset.action = 'close-output-prompt';
    close.setAttribute('aria-label', 'Close');
    close.title = 'Close';
    close.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-x"></use></svg>';
    sheet.append(list, close);
    preview.append(sheet);
    prompt.setAttribute('aria-controls', sheet.id);
    this.markOutputPrompt(prompt);
    close.focus();
  }

  closeOutputPromptSheet(restoreFocus = true) {
    this.querySelector('#video-prompt-sheet')?.remove();
    const prompt = this.querySelector('.video-output-prompt');
    if (!prompt) return;
    prompt.removeAttribute('aria-controls');
    this.markOutputPrompt(prompt);
    if (restoreFocus) prompt.focus();
  }

  observeOutputPrompt(prompt) {
    if (this.observedOutputPrompt && this.observedOutputPrompt !== prompt) {
      this.outputPromptResizeObserver.unobserve(this.observedOutputPrompt);
    }
    this.observedOutputPrompt = prompt;
    if (!prompt) return;
    this.outputPromptResizeObserver.observe(prompt);
    this.markOutputPrompt(prompt);
  }

  markOutputPrompt(prompt) {
    const open = Boolean(this.querySelector('#video-prompt-sheet'));
    const cut = prompt.scrollHeight > prompt.clientHeight + 1;
    if (open || cut) {
      prompt.dataset.action = 'open-output-prompt';
      prompt.setAttribute('role', 'button');
      prompt.tabIndex = 0;
      prompt.setAttribute('aria-expanded', String(open));
      return;
    }
    prompt.removeAttribute('data-action');
    prompt.removeAttribute('role');
    prompt.removeAttribute('tabindex');
    prompt.removeAttribute('aria-expanded');
    prompt.removeAttribute('aria-controls');
  }

  async toggleVideoFullscreen() {
    if (!this.querySelector('.video-tv-frame') || !document.fullscreenEnabled) return;
    try {
      if (document.fullscreenElement === this) await document.exitFullscreen();
      else await this.requestFullscreen();
    } catch (error) {
      this.setError('Full screen failed: ' + error.message);
    }
  }

  onVideoFullscreenChange() {
    this.renderOutputDetails();
  }

  onComponentChange(event) {
    const control = event.target;
    if (!(control instanceof HTMLInputElement)) return;
    if (control.id === 'video-media-upload') {
      // The chooser takes both kinds, so it is emptied here: picking the same file twice
      // raises no change event while the input still holds it.
      const files = Array.from(control.files || []);
      control.value = '';
      this.addMediaFiles(files);
    }
  }

  // The zone's own door, beside the drop the panel already takes and the paste the document
  // takes. All three hand their files to `addMediaFiles`, which reads the type of each one.
  openMediaChooser() {
    const chooser = document.getElementById('video-media-upload');
    if (chooser) chooser.click();
  }

  // A role of button answers a key as well as a press, the way the image form's zone does.
  onSourceKeydown(event) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    if (!event.target.closest('#video-media-empty')) return;
    event.preventDefault();
    this.openMediaChooser();
  }

  onComponentInput(event) {
    const control = event.target;
    if (!(control instanceof HTMLInputElement)) return;
    if (control.dataset.action === 'reference-strength') {
      this.setReferenceStrength(control.dataset.referenceId, control);
    }
  }

  addVideoFiles(files, epoch = this.captureInputEpoch()) {
    if (!this.canCommitInput(epoch)) return;
    // An edit changes one clip. A second one would sit in a list the mode does not use as a
    // list, so it is refused with the way out named: the row's own remove button.
    if (!this.needsClip) {
      this.setError('Generate takes images and audio. Add a clip in Edit to change one.');
      return false;
    }
    const chosen = Array.from(files).filter(isVideoFile);
    // The same file twice is a mistake in both modes, and its own identity says so: a name
    // alone would refuse two different clips that happen to share one.
    const duplicate = chosen.find((file) => this.clips.some((clip) =>
      clip.kind === 'source' && clip.name === file.name && clip.size === file.size));
    if (duplicate) {
      this.setError('That clip is already here.');
      return false;
    }
    // An edit changes one clip. Generate may hold several, because a source clip is also how a
    // frame is picked there.
    if (this.needsClip) {
      if (this.editTargetId) {
        this.setError('An edit uses one clip. Remove the current clip first.');
        return false;
      }
      if (chosen.length > 1) {
        this.setError('An edit uses one clip. Choose one video.');
        return false;
      }
    }
    const videos = chosen;
    const hasUnsupported = videos.length !== files.length;
    if (!videos.length) {
      this.setError('Choose a video file.');
      return;
    }
    videos.forEach((file, index) => {
      const clip = {
        id: 'clip-' + nextClipId++,
        kind: 'source',
        name: file.name,
        size: file.size,
        file: file,
        url: URL.createObjectURL(file),
        objectUrl: true,
        duration: 0,
        // An added clip downloads under its own name too, so it carries its moment.
        createdAt: Date.now(),
      };
      this.clips = this.clips.concat(clip);
      if (index === 0) this.selectedClipId = clip.id;
    });
    if (hasUnsupported) this.setError('Choose a video file.');
    else this.clearError();
    // An upload is a choice, so it becomes the edit's target too. Without this the form
    // stayed dead until the row was clicked, which read as a clip that had not landed.
    this.editTargetId = this.selectedClipId;
    this.renderSourceVideos();
    this.renderSelectedClip();
    this.announceSelection();
    return true;
  }

  async addImageFiles(files, epoch = this.captureInputEpoch()) {
    if (!this.canCommitInput(epoch)) return;
    for (const file of files) {
      if (!this.canCommitInput(epoch)) return;
      if (!isImageFile(file)) {
        this.setError('Choose an image file.');
        continue;
      }
      try {
        const src = await readDataUrl(file);
        if (!this.canCommitInput(epoch)) return;
        this.addImageReference({
          id: 'video-ref-' + nextClipId++,
          name: file.name,
          src: src,
          base64: src.slice(src.indexOf(',') + 1),
        });
      } catch (error) {
        if (!this.canCommitInput(epoch)) return;
        this.setError('The image could not be added: ' + error.message);
      }
    }
  }

  async addMediaFiles(files, epoch = this.captureInputEpoch()) {
    if (!this.canCommitInput(epoch)) return;
    // An edit changes one clip. The page sets this from the mode, and it covers the chooser,
    // a drop and a paste: an image is not an edit input, and taking none of the batch is the
    // honest answer when one arrives beside a clip.
    if (this.needsClip && Array.from(files).some((file) => (isImageFile(file) && !this.maxReferences) || isAudioFile(file))) {
      this.setError('An edit changes a clip. Choose a video file.');
      return;
    }
    const images = Array.from(files).filter(isImageFile);
    const videos = Array.from(files).filter(isVideoFile);
    const audios = Array.from(files).filter(isAudioFile);
    const unsupported = Array.from(files).filter((file) =>
      !isImageFile(file) && !isVideoFile(file) && !isAudioFile(file));
    if (images.length) await this.addImageFiles(images, epoch);
    if (!this.canCommitInput(epoch)) return;
    // A refused intake keeps its own message: clearing it here made the refusal silent.
    if (videos.length && !this.addVideoFiles(videos, epoch)) return;
    if (audios.length > 1) {
      this.setError('One audio track at a time.');
      return;
    }
    if (audios.length && !this.addAudioFile(audios[0], epoch)) return;
    if (unsupported.length) this.setError('Choose an image, a video or an audio file.');
    else if (images.length || videos.length || audios.length) this.clearError();
  }

  clipboardFiles(event) {
    const clipboard = event.clipboardData;
    if (!clipboard) return [];
    const files = Array.from(clipboard.files || []);
    if (files.length) return files;
    return Array.from(clipboard.items || []).filter((item) => item.kind === 'file')
      .map((item) => item.getAsFile()).filter(Boolean);
  }

  onPaste(event) {
    if (this.hidden) return;
    const files = this.clipboardFiles(event);
    const media = files.filter((file) => isImageFile(file) || isVideoFile(file));
    if (!media.length) return;
    event.preventDefault();
    if (this.generationProgress) return;
    this.addMediaFiles(media);
  }

  onShortcutPaste(event) {
    if (this.hidden || event.defaultPrevented || event.altKey
        || !(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 'p') return;
    event.preventDefault();
    if (this.generationProgress) return;
    this.pasteMediaFromClipboard();
  }

  async pasteMediaFromClipboard() {
    const epoch = this.captureInputEpoch();
    if (!this.canCommitInput(epoch)) return;
    if (!navigator.clipboard || typeof navigator.clipboard.read !== 'function') {
      this.setError('Clipboard file access is unavailable. Use Paste or choose a file.');
      return;
    }
    try {
      const items = await navigator.clipboard.read();
      if (!this.canCommitInput(epoch)) return;
      const files = [];
      for (const item of items) {
        const mediaType = item.types.find((type) => type.startsWith('image/') || type.startsWith('video/'));
        if (!mediaType) continue;
        const blob = await item.getType(mediaType);
        if (!this.canCommitInput(epoch)) return;
        const extension = mediaType.split('/')[1].replace('jpeg', 'jpg');
        const name = item.name || 'pasted-' + (mediaType.startsWith('image/') ? 'image' : 'video') + '.' + extension;
        files.push(new File([blob], name, {type: mediaType}));
      }
      if (!files.length) {
        this.setError('The clipboard has no image or video file. Copy media, then paste again.');
        return;
      }
      await this.addMediaFiles(files, epoch);
    } catch (error) {
      if (!this.canCommitInput(epoch)) return;
      this.setError('The clipboard media could not be read: ' + error.message);
    }
  }

  onSourceDragOver(event) {
    if (!Array.from(event.dataTransfer?.types || []).includes('Files')) return;
    event.preventDefault();
    this.sourcePanel.classList.add('drop-over');
  }

  onSourceDragLeave(event) {
    if (event.relatedTarget instanceof Node && this.sourcePanel.contains(event.relatedTarget)) return;
    this.sourcePanel.classList.remove('drop-over');
  }

  onSourceDrop(event) {
    event.preventDefault();
    this.sourcePanel.classList.remove('drop-over');
    const files = Array.from(event.dataTransfer?.files || []);
    if (files.length) this.addMediaFiles(files);
  }

  selectedClip() {
    return this.clips.find((clip) => clip.id === this.selectedClipId) || null;
  }

  videoSerial(clip) {
    const videos = this.clips.filter((item) => item.kind === clip.kind);
    const index = videos.findIndex((item) => item.id === clip.id);
    const prefix = clip.kind === 'source' ? 'S' : '';
    return prefix + String(Math.max(0, index + 1)).padStart(2, '0');
  }

  nextVideoSerial() {
    const count = this.clips.filter((clip) => clip.kind === 'generated').length + 1;
    return String(count).padStart(2, '0');
  }

  renderMonitor(content, modelName, serial, ratio, elapsed = '') {
    const mediaRatio = Number.isFinite(ratio) && ratio > 0 ? ratio : 16 / 9;
    return html`
      <div class="video-tv-frame" data-media-ratio=${mediaRatio}>
        <div class="video-tv-screen">${content}</div>
        <div class="video-tv-edge" role="group" aria-label=${modelName + ', video ' + serial
          + (elapsed ? ', ' + elapsed : '')}>
          <span class="video-tv-model">${modelName}</span>
          <span class="video-tv-readout">
            ${elapsed ? html`<span class="video-tv-elapsed">${elapsed}</span>` : nothing}
            <span class="video-tv-serial">${serial}</span>
          </span>
        </div>
      </div>`;
  }

  // The form needs to know which clip is in hand: an edit changes its explicit target, and the
  // run button is dead until there is one.
  announceSelection() {
    const clip = this.clips.find((one) => one.id === this.editTargetId) || null;
    this.dispatchEvent(
      new CustomEvent('video-clip-selected', {
        detail: {
          id: clip ? clip.id : '',
          name: clip ? clip.name : '',
          stub: clip ? Boolean(clip.stub) : false,
          kind: clip ? clip.kind : '',
        },
        bubbles: true,
        composed: true,
      }),
    );
    this.inputsChanged();
  }

  selectClip(id) {
    this.closeOutputPromptSheet(false);
    // Preview navigation must preserve the input selected for an edit.
    this.selectedClipId = id;
    this.showRender = false;
    this.previewResume = null;
    this.currentTime = 0;
    const clip = this.selectedClip();
    this.duration = clip ? clip.duration || 0 : 0;
    this.error = '';
    this.renderSourceVideos();
    this.renderSelectedClip();
    this.announceSelection();
  }

  clearEditTarget() {
    const target = this.clips.find((clip) => clip.id === this.editTargetId);
    this.editTargetId = null;
    if (target?.kind === 'source') {
      this.removeClip(target.id);
      return;
    }
    this.renderSourceVideos();
    this.announceSelection();
  }

  showRenderMonitor() {
    if (!this.generationProgress) return;
    this.closeOutputPromptSheet(false);
    this.showRender = true;
    this.currentTime = 0;
    this.duration = 0;
    this.renderPreview();
    this.renderVideoGallery();
    this.renderOutputDetails();
  }

  stepClip(delta) {
    const gallery = this.querySelector('#video-gallery');
    // The strip draws newest first, and this walks it in the order it draws, so the
    // arrow keys move the way the frames do.
    const outputs = this.clips.filter((clip) => clip.kind === 'generated').reverse();
    const current = outputs.findIndex((clip) => clip.id === this.selectedClipId);
    const next = outputs[current + delta];
    if (!next) return false;
    const keepFocus = Boolean(gallery?.contains(document.activeElement));
    this.selectClip(next.id);
    const selected = this.querySelector('#video-gallery .video-clip.selected');
    if (selected) {
      selected.scrollIntoView({block: 'nearest', inline: 'nearest'});
      if (keepFocus) selected.focus();
    }
    return true;
  }

  async togglePlayback() {
    const video = this.querySelector('#video-preview-root video');
    if (!video) return;
    if (!video.paused) video.pause();
    else {
      try { await video.play(); }
      catch (error) {
        if (error.name !== 'AbortError' && video.isConnected && video === this.querySelector('#video-preview-root video')) {
          this.setError('Playback failed: ' + error.message);
        }
      }
    }
  }

  // Gallery deletion removes the media. Clearing an edit input uses clearEditTarget instead.
  async removeClip(id, persist = true) {
    const removed = this.clips.find(function (clip) { return clip.id === id; });
    if (!removed) return;
    if (this.selectedClipId === id) this.closeOutputPromptSheet(false);
    if (persist && removed.kind === 'generated' && this.galleryStore) {
      const deleted = await this.galleryStore.removeVideo(id);
      if (!deleted) return;
    }
    if (removed) releaseClipUrls(removed);
    this.clips = this.clips.filter(function (clip) { return clip.id !== id; });
    if (this.editTargetId === id) {
      // Removing the target leaves no target. The monitor may show another clip, and showing
      // is not picking.
      this.editTargetId = null;
    }
    if (this.selectedClipId === id) {
      this.selectedClipId = this.clips.length ? this.clips[0].id : null;
      this.previewResume = null;
      this.currentTime = 0;
      const selected = this.selectedClip();
      this.duration = selected ? selected.duration || 0 : 0;
      this.renderSelectedClip();
    }
    this.renderSourceVideos();
    this.renderVideoGallery();
    this.announceSelection();
  }

  async downloadAllVideos(ids = null) {
    const outputs = this.clips.filter((clip) => clip.kind === 'generated' && !clip.stub && clip.url
      && (!ids || ids.includes(clip.id))).reverse();
    if (!outputs.length) return;
    const details = [];
    try {
      for (const clip of outputs) {
        const file = videoDownloadName(clip);
        saveFile(clip.url, file);
        details.push(videoExportMetadata(clip, file));
        await waitBetweenDownloads();
      }
      const metadataUrl = URL.createObjectURL(new Blob([JSON.stringify(details, null, 2)], {
        type: 'application/json',
      }));
      saveFile(metadataUrl, mediaDownloadName({kind: 'video', text: 'metadata', at: Date.now(), extension: 'json'}));
      setTimeout(() => URL.revokeObjectURL(metadataUrl), 10000);
    } catch (error) {
      this.setError((ids ? 'Download selected stopped: ' : 'Download all stopped: ') + error.message);
    }
  }

  async clearVideoGallery(persist = true) {
    const outputs = this.clips.filter((clip) => clip.kind === 'generated'
      && (persist || !this.galleryStore?.videoWasRemoved || this.galleryStore.videoWasRemoved(clip)));
    if (!outputs.length) return;
    if (persist && this.galleryStore) {
      const cleared = await this.galleryStore.clearVideos(outputs.map(clip => clip.id));
      if (!cleared) return;
    }
    const selectedWasRemoved = outputs.some((clip) => clip.id === this.selectedClipId);
    this.clips = this.clips.filter((clip) => !outputs.includes(clip));
    if (outputs.some((clip) => clip.id === this.editTargetId)) this.editTargetId = null;
    outputs.forEach(releaseClipUrls);
    if (selectedWasRemoved) {
      this.closeOutputPromptSheet(false);
      this.selectedClipId = this.clips.find((clip) => clip.kind === 'source')?.id || null;
      this.previewResume = null;
      this.currentTime = 0;
      const selected = this.selectedClip();
      this.duration = selected ? selected.duration || 0 : 0;
      this.renderSelectedClip();
    }
    this.renderSourceVideos();
    this.renderVideoGallery();
    this.announceSelection();
  }

  onMetadata(event) {
    const clip = this.selectedClip();
    if (!clip) return;
    const video = event.target;
    clip.duration = Number.isFinite(video.duration) ? video.duration : 0;
    clip.width = video.videoWidth;
    clip.height = video.videoHeight;
    if (this.previewResume?.clipId === clip.id) {
      video.currentTime = Math.min(this.previewResume.time, clip.duration);
      this.previewResume = null;
    }
    this.duration = clip.duration;
    this.currentTime = video.currentTime || 0;
    this.renderSourceVideos();
    this.renderVideoGallery();
    this.renderOutputDetails();
    const monitor = this.querySelector('.video-tv-frame');
    if (monitor && video.videoWidth && video.videoHeight) {
      monitor.dataset.mediaRatio = String(video.videoWidth / video.videoHeight);
      this.fitVideoMonitor();
    }
  }

  onTimeUpdate(event) {
    this.currentTime = event.target.currentTime || 0;
  }

  captureFrameForImage() {
    return this.captureFrame('image');
  }

  captureFrameForVideo() {
    return this.captureFrame('video');
  }

  async captureFrame(target) {
    const epoch = this.captureInputEpoch();
    if (!this.canCommitInput(epoch)) return;
    const video = this.querySelector('#video-preview');
    const clip = this.selectedClip();
    if (!video || !clip || video.readyState < 2 || !video.videoWidth || !video.videoHeight) {
      this.setError('Wait for the video frame to load, then try again.');
      return;
    }
    try {
      const frameTime = video.currentTime;
      const canvas = document.createElement('canvas');
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
      const blob = await new Promise(function (resolve, reject) {
        canvas.toBlob(function (image) {
          if (image) resolve(image);
          else reject(new Error('The frame could not be captured.'));
        }, 'image/png');
      });
      if (!this.canCommitInput(epoch)) return;
      this.dispatchEvent(new CustomEvent('video-frame-captured', {
        detail: {
          blob: blob,
          name: clip.name + ' frame ' + formatTime(frameTime),
          target: target,
          epoch: epoch,
          frameIndex: target === 'video'
            ? Math.round(frameTime / Math.max(video.duration, 0.01) * Math.max(0, (this.frameLimit || 1) - 1))
            : Math.round(frameTime * this.outputFrameRate),
        },
        bubbles: true,
        composed: true,
      }));
      this.clearError();
    } catch (error) {
      if (!this.canCommitInput(epoch)) return;
      this.setError('The frame could not be captured: ' + error.message);
    }
  }

  renderSelectedClip() {
    const clip = this.selectedClip();
    if (clip?.kind === 'generated') rememberGalleryView('video', {selected: clip.id}, this.keepEnabled);
    this.renderPreview();
    this.renderVideoGallery();
    this.renderOutputDetails();
  }

  renderOutputDetails() {
    const root = this.querySelector('#video-output-details-root');
    if (!root) return;
    const clip = this.selectedClip();
    const pending = Boolean(this.generationProgress && this.pendingRender && this.showRender);
    const metadata = pending ? videoMetadata(this.pendingRender) : clip?.metadata;
    if (!pending && !clip) {
      renderTemplate('', root);
      this.observeOutputPrompt(null);
      return;
    }
    const isSource = !pending && clip.kind === 'source';
    const generated = pending || (!isSource && clip?.kind === 'generated');
    const references = metadata?.references || [];
    const duration = metadata?.numFrames && metadata?.frameRate
      ? metadata.numFrames / metadata.frameRate : Number(clip?.duration) || 0;
    const seed = Number.isInteger(metadata?.seed) ? metadata.seed : null;
    const timeLabel = pending ? ''
      : clip.stub ? 'Request time ' + formatTime(metadata.elapsedSeconds)
        : metadata ? 'Took ' + formatTime(metadata.elapsedSeconds) : '';
    const preview = this.querySelector('#video-preview');
    const facts = [];
    if (metadata) {
      if (duration) facts.push(duration.toFixed(1) + ' sec');
      if (metadata.width && metadata.height) facts.push(metadata.width + ' × ' + metadata.height);
      if (metadata.numFrames) facts.push(metadata.numFrames + ' frames');
      if (metadata.fastMode) facts.push('Fast mode');
      facts.push(seed === null ? 'Random seed' : 'Seed ' + seed);
      if (timeLabel) facts.push(timeLabel);
      if (references.length) {
        facts.push(references.length + (references.length === 1 ? ' image reference' : ' image references'));
      }
    } else {
      facts.push('Source clip');
      if (duration) facts.push('Duration ' + formatTime(duration));
      if (preview?.videoWidth && preview?.videoHeight) {
        facts.push(preview.videoWidth + ' × ' + preview.videoHeight);
      }
    }
    const prompt = metadata?.prompt || clip?.name || 'Rendering video';
    const canCapture = Boolean(!pending && clip && !clip.stub);
    const canDownload = Boolean(!pending && generated && clip && !clip.stub && clip.url);
    const canRemove = Boolean(!pending && clip);
    const canShowMore = Boolean(!pending && (generated || canCapture));
    const renderLabel = isSource ? 'Source clip' : '';
    const fullscreen = document.fullscreenElement === this;
    renderTemplate(html`
      <section class="stage-bar video-stage-bar video-output-details" id="video-output-details"
        aria-label="Video preview details">
        <div class="about">
          <p class="prompt-line video-output-prompt" title=${prompt}>${prompt}</p>
          <div class="facts num video-output-facts" aria-label="Video metadata">
            ${renderLabel ? html`<span class="made">${renderLabel}</span>` : nothing}
            ${facts.map((fact) => html`<span>${fact}</span>`)}
          </div>
        </div>
        <div class="actions video-output-actions">
          ${canCapture && !this.needsClip ? html`
            <button class="btn quiet" type="button" data-action="capture-video-frame"
              aria-label="Add reference" title="Add this frame as an image reference">
              <svg class="icon" aria-hidden="true"><use href="#i-image-in"></use></svg>Add reference</button>` : nothing}
          ${canCapture && this.needsClip ? html`
            <button class="btn quiet" type="button" data-action="edit-this-clip" data-clip-id=${clip.id}
              aria-label="Edit this clip" title="Change this clip in Edit">
              <svg class="icon" aria-hidden="true"><use href="#i-brush"></use></svg>Edit this clip</button>` : nothing}
          ${canShowMore ? html`
            <div class="menu-anchor">
              <button class="icon-btn" type="button" data-action="toggle-output-menu"
                aria-label="More actions" aria-controls="video-output-menu" aria-expanded="false" title="More actions">
                <svg class="icon" aria-hidden="true"><use href="#i-more"></use></svg>
              </button>
              <div class="menu up" id="video-output-menu" role="menu" hidden></div>
            </div>` : nothing}
          ${canShowMore ? html`<span class="rule" aria-hidden="true"></span>` : nothing}
          ${canDownload ? html`
            <a class="icon-btn" href=${clip.url} download=${videoDownloadName(clip)}
              aria-label="Download video" title="Download">
              <svg class="icon" aria-hidden="true"><use href="#i-download"></use></svg>
            </a>` : nothing}
          ${canRemove ? html`
            <button class="icon-btn danger" type="button" data-action="remove-clip" data-clip-id=${clip.id}
              aria-label=${'Remove video ' + clip.name} title="Remove">
              <svg class="icon" aria-hidden="true"><use href="#i-trash"></use></svg>
            </button>` : nothing}
          ${document.fullscreenEnabled ? html`
            <button class="icon-btn" type="button" data-action="toggle-video-fullscreen"
              aria-label=${fullscreen ? 'Exit full screen' : 'Full screen'}
              title=${fullscreen ? 'Exit full screen' : 'Full screen'}>
              <svg class="icon" aria-hidden="true"><use href=${fullscreen ? '#i-shrink' : '#i-expand'}></use></svg>
            </button>` : nothing}
        </div>
      </section>`, root);
    this.observeOutputPrompt(root.querySelector('.video-output-prompt'));
    const menu = root.querySelector('#video-output-menu');
    if (!menu || !clip) return;
    menu.replaceChildren();
    // Generate keeps its frame actions: Add reference sits on the bar, and the menu offers the
    // image workspace and the door into Edit. Edit's menu carries neither, because an edit
    // takes no references and its bar is already the edit door.
    if (canCapture) {
      // The clip lives in Edit now, so the actions that read its frame live there too. Edit's
      // bar carries Edit this clip, so the frame capture sits in this menu.
      menu.append(menuItem('image-in', 'Use current frame in Image', () => this.captureFrameForImage()));
      if (this.needsClip) {
        menu.append(menuItem('image-in', 'Add this frame as a reference', () => this.captureFrameForVideo()));
      } else {
        menu.append(menuItem('brush', 'Edit this clip', () => this.editThisClip(clip.id)));
      }
    }
    if (this.supportsSeed && seed !== null) {
      menu.append(menuItem('hash', 'Reuse seed ' + seed, () => this.reuseOutput({seed})));
    }
    if (metadata?.prompt) {
      menu.append(menuItem('text', 'Reuse prompt', () => this.reuseOutput({prompt: metadata.prompt})));
    }
  }

  // The menu's door into Edit: the clip is in hand, and the page owns the mode switch.
  editThisClip(clipId) {
    const previous = this.clips.find((clip) => clip.id === this.editTargetId);
    this.selectClip(clipId);
    this.editTargetId = clipId;
    if (previous?.kind === 'source' && previous.id !== clipId) this.removeClip(previous.id);
    this.renderSourceVideos();
    this.announceSelection();
    this.dispatchEvent(new CustomEvent('video-edit-clip', { bubbles: true, composed: true }));
  }

  reuseOutput(detail) {
    closeMenus();
    this.dispatchEvent(new CustomEvent('video-output-reuse', {
      detail: detail,
      bubbles: true,
      composed: true,
    }));
  }

  renderPreview() {
    const preview = this.querySelector('#video-preview-content-root');
    if (!preview) return;
    const content = this.generationProgress && this.showRender
      ? this.renderProgressPlaceholder(this.generationProgress)
      : this.renderClip(this.selectedClip());
    renderTemplate(content, preview);
    this.fitVideoMonitor();
  }

  fitVideoMonitor() {
    const monitor = this.querySelector('.video-tv-frame');
    const preview = this.querySelector('#video-preview-content-root');
    if (!monitor || !preview || !preview.clientWidth || !preview.clientHeight) return;
    if (document.fullscreenElement === monitor) return;
    const ratio = Number(monitor.dataset.mediaRatio) || 16 / 9;
    const screenWidth = Math.min(1180, preview.clientWidth - 20, (preview.clientHeight - 38) * ratio);
    if (screenWidth <= 0) return;
    monitor.style.width = Math.floor(screenWidth + 20) + 'px';
    monitor.style.height = Math.floor(screenWidth / ratio + 38) + 'px';
  }

  // Sampler steps cover denoising. Decoding and saving still follow the last step,
  // so an active render cannot claim 100%. The returned clip replaces this status.
  generationProgressDetails(progress) {
    const elapsed = formatTime(progress.elapsedSeconds);
    const total = Number(progress.total) || 0;
    const step = Number(progress.step) || 0;
    const percent = total > 0 ? Math.max(0, Math.min(99, Math.round(step / total * 100))) : null;
    // The progress bar keeps one name for the whole render: a name that changes under a
    // screen reader is read twice. The headline under it names the moment instead.
    const name = progress.stopping ? 'Stopping video' : 'Generating video';
    return {
      name,
      label: this.progressHeadline(progress, step, total),
      elapsed: elapsed + ' elapsed',
      percent,
      readout: percent === null ? elapsed + ' elapsed' : percent + '%, ' + elapsed + ' elapsed',
    };
  }

  progressHeadline(progress, step, total) {
    if (progress.stopping) return 'Stopping video';
    if (!step) return 'Preparing the clip';
    if (total > 0 && step >= total) return 'Finishing the clip';
    return total > 0 ? 'Denoising, step ' + step + ' of ' + total : 'Denoising, step ' + step;
  }

  renderProgressPlaceholder(progress) {
    const details = this.generationProgressDetails(progress);
    const status = html`
      <section id="video-render-status" class="video-render-placeholder" role="status"
        aria-label=${details.name} aria-atomic="true">
        <div class="video-render-content">
          <strong>${details.label}</strong>
          <div id="video-render-progress"
            class=${details.percent === null ? 'video-render-progress is-indeterminate' : 'video-render-progress'}
            role="progressbar" aria-label=${details.name} aria-valuemin="0" aria-valuemax="100"
            aria-valuenow=${details.percent === null ? nothing : details.percent}
            aria-valuetext=${details.readout}
            style=${details.percent === null ? nothing : '--rendered: ' + details.percent + '%'}></div>
          ${details.percent === null ? nothing : html`
            <span id="video-render-percent" class="video-render-percent">${details.percent}%</span>`}
        </div>
      </section>`;
    return this.renderMonitor(
      status,
      this.outputModelName,
      this.nextVideoSerial(),
      this.outputWidth / this.outputHeight,
      details.elapsed,
    );
  }

  renderVideoGallery() {
    const gallery = this.querySelector('#video-gallery-root');
    if (!gallery) return;
    const outputs = this.clips.filter((clip) => clip.kind === 'generated');
    this.classList.toggle('has-video-gallery', Boolean(outputs.length || this.pendingRender));
    renderTemplate(this.renderGallery(), gallery);
  }

  renderGallery() {
    const outputs = this.clips.filter((clip) => clip.kind === 'generated');
    // One thing is current: the render while it owns the screen, and a clip otherwise.
    // That is the same rule the image strip draws with, where the waiting frame and the
    // image frames cannot both read as selected.
    const renderOnScreen = Boolean(this.pendingRender && this.showRender);
    // The strip reads newest first, so this is the order it draws in, and the order the
    // arrow keys walk. The number stays the clip's own: it counts from the first clip of
    // the session and it is the one the preview edge carries.
    const newestFirst = outputs.slice().reverse();
    const downloadable = outputs.filter((clip) => !clip.stub && clip.url);
    const kept = outputs.filter((clip) => clip.keptInBrowser).length;
    const videoCount = outputs.length + (outputs.length === 1 ? ' video' : ' videos');
    const note = !outputs.length
      ? this.keepEnabled ? 'Videos are kept in this browser.' : 'Videos stay in this tab only.'
      : kept === outputs.length
        ? videoCount + ', kept in this browser.'
          + (this.storagePersisted === false ? ' The browser may clear them when space is low.' : '')
        : downloadable.length ? videoCount + ' in this tab. Download the ones you want to keep.'
          : (outputs.length === 1 ? 'A stub result' : outputs.length + ' stub results') + ' in this tab.';
    return html`
      <section class="video-gallery strip-wrap" id="video-gallery" aria-label="Video gallery"
        ?hidden=${!outputs.length && !this.pendingRender}>
        <div class="strip-head video-gallery-head">
          <span id="video-gallery-note">${note}</span>
          <gallery-browser workspace="video" .items=${newestFirst.map(clip => ({id: clip.id,
            number: outputs.indexOf(clip) + 1, text: clip.metadata?.prompt, name: clip.name,
            model: clip.metadata?.modelName, mode: clip.metadata?.mode, seed: clip.metadata?.seed,
            at: clip.createdAt, batch: galleryBatch(clip.metadata?.operationId, true),
            thumbnail: clip.thumbnailUrl, video: clip.stub ? null : clip.url, duration: clip.duration, downloadable: !clip.stub && Boolean(clip.url)}))}
            .selectedId=${this.selectedClipId} .keeping=${this.keepEnabled}
            .pending=${Boolean(this.pendingRender)} .pendingSelected=${renderOnScreen}
            .showPending=${() => this.showRenderMonitor()} .choose=${id => this.selectClip(id)}
            .removeItem=${async id => { await this.removeClip(id); return !this.clips.some(clip => clip.id === id); }}
            .download=${ids => this.downloadAllVideos(ids)} .playback=${() => this.togglePlayback()}></gallery-browser>
          <span class="strip-actions">
            <button class="text-btn" type="button" id="video-gallery-download"
              data-action="download-all-videos" ?hidden=${!downloadable.length}>Download all</button>
            <button class="text-btn" type="button" id="video-gallery-clear"
              data-action="clear-video-gallery" ?hidden=${!outputs.length}>Clear all</button>
          </span>
        </div>
        <div class="strip video-clips" role="group" aria-label="Generated videos">
          ${this.pendingRender ? html`
            <button class="video-gallery-item video-gallery-pending frame pending${renderOnScreen ? ' selected' : ''}"
              type="button" aria-label="Show the render in progress" aria-pressed=${renderOnScreen}
              data-action="show-render">
              <span class="still video-clip-thumb pending-thumb">
                <span class="video-pending-indicator" aria-hidden="true"></span>
                <span>Rendering</span>
              </span>
              <span class="no">${String(outputs.length + 1).padStart(2, '0')}</span>
              ${renderOnScreen ? pencilLoop() : nothing}
            </button>` : ''}
          ${outputs.length ? newestFirst.map((clip, position) => html`
            <div class="video-gallery-item">
              <button class="frame video-clip${clip.id === this.selectedClipId && !renderOnScreen ? ' selected' : ''}"
                type="button" aria-label=${'Select video ' + clip.name}
                aria-pressed=${clip.id === this.selectedClipId && !renderOnScreen}
                data-action="select-clip" data-clip-id=${clip.id}>
                <span class="still video-clip-thumb">
                  ${clip.url && !clip.stub
                    ? html`<video-gallery-preview .source=${clip.url} .poster=${clip.thumbnailUrl}
                      .blocked=${Boolean(this.pendingRender)}></video-gallery-preview>`
                    : clip.thumbnailUrl
                    ? html`<img src=${clip.thumbnailUrl} alt="">`
                    : html`<span class="video-clip-placeholder" title=${clip.thumbnailError || ''}>
                      ${clip.stub ? 'STUB' : clip.thumbnailError ? 'NO PREVIEW' : 'PREVIEW'}
                    </span>`}
                  <span class="video-clip-duration">${formatTime(clip.duration || 0)}</span>
                </span>
                <span class="no">${String(outputs.length - position).padStart(2, '0')}</span>
                ${clip.id === this.selectedClipId && !renderOnScreen ? pencilLoop(true) : nothing}
              </button>
            </div>`) : ''}
        </div>
      </section>`;
  }

  renderClip(clip) {
    if (!clip) {
      return html`<div class="video-empty">
        <div class="video-empty-mark">VIDEO</div>
        <strong>Preview a video</strong>
        <span>Select a source video or generated clip.</span>
      </div>`;
    }
    const preview = html`<div class="video-preview-pane">
      <video id="video-preview" src=${clip.url} ?hidden=${clip.stub} controls playsinline preload="metadata"></video>
      <div class="video-preview-stub" ?hidden=${!clip.stub}>
        <div class="video-empty-mark">STUB</div>
        <strong>Request flow verified</strong>
        <span>The stub returns metadata only. It does not create a video file.</span>
      </div>
    </div>`;
    const width = Number(clip.metadata?.width || clip.width) || 16;
    const height = Number(clip.metadata?.height || clip.height) || 9;
    const modelName = clip.kind === 'generated' ? clip.metadata?.modelName || 'Video' : 'SOURCE VIDEO';
    return this.renderMonitor(preview, modelName, this.videoSerial(clip), width / height);
  }

  render() {
    return html`
      <div class="video-studio-shell">
        <div class="video-preview-area stage" id="video-preview-root">
          <div id="video-preview-content-root"></div>
          <div id="video-output-details-root"></div>
        </div>
        <div class="video-editing-area">
          <div id="video-gallery-root"></div>
        </div>
      </div>
    `;
  }
}

customElements.define('video-studio', VideoStudio);
