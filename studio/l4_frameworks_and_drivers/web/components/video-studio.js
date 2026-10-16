import { LitElement, html, nothing, render as renderTemplate } from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import { closeMenus, menuItem, toggleMenu } from './popup-menu.js';

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

function videoMetadata(settings, result = {}) {
  const references = Array.isArray(settings.references) ? settings.references : [];
  const seed = result.seed ?? settings.seed ?? null;
  return {
    backend: settings.backend || '',
    modelName: settings.modelName || 'Video',
    prompt: settings.prompt || '',
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
  const extension = clip.mp4Blob?.type.includes('webm') ? 'webm' : 'mp4';
  return clip.name.replace(/\.(mp4|webm)$/i, '') + '.' + extension;
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
  galleryStore = null;
  keepEnabled = true;
  generationProgress = null;
  generationEpoch = 0;
  pendingRender = null;
  previewResume = null;
  sourcePanel = null;
  selectedReferenceId = null;
  selectedClipId = null;
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
    this.renderError();
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
    await this.updateComplete;
    const records = await store.loadVideos();
    records.forEach((record) => {
      if (this.clips.some((clip) => clip.id === record.id)) return;
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
        keptInBrowser: true,
      };
      this.addClip(clip);
      if (!clip.thumbnailBlob) this.createThumbnail(clip);
    });
  }

  setKeeping(keeping) {
    this.keepEnabled = keeping;
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
    createVideoThumbnail(clip.url).then((thumbnail) => {
      if (!this.isConnected || !this.clips.includes(clip)) return;
      clip.thumbnailBlob = thumbnail;
      clip.thumbnailUrl = URL.createObjectURL(thumbnail);
      this.renderVideoGallery();
      if (this.keepEnabled && this.galleryStore) {
        this.galleryStore.keepVideoThumbnail(clip.id, thumbnail);
      }
    }).catch((error) => {
      clip.thumbnailError = error.message;
      this.renderVideoGallery();
    });
  }

  setGenerationProgress(state, elapsedSeconds, outputShape) {
    if (state?.running && !this.generationProgress) {
      this.generationEpoch += 1;
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

  captureInputEpoch() {
    return this.generationProgress ? null : this.generationEpoch;
  }

  canCommitInput(epoch) {
    return epoch !== null && !this.generationProgress && epoch === this.generationEpoch;
  }

  addImageReference(reference, epoch = this.captureInputEpoch()) {
    if (!this.canCommitInput(epoch)) return;
    if (this.imageReferences.some(function (saved) { return saved.id === reference.id; })) return;
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
  }

  removeImageReference(id) {
    this.imageReferences = this.imageReferences.filter(function (reference) { return reference.id !== id; });
    if (this.selectedReferenceId === id) {
      this.selectedReferenceId = this.imageReferences.length ? this.imageReferences[0].id : null;
    }
    this.renderImageReferences();
  }

  clearImageReferences() {
    this.imageReferences = [];
    this.selectedReferenceId = null;
    this.renderImageReferences();
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
      remove.textContent = '×';
      const name = document.createElement('span');
      name.className = 'video-reference-name';
      name.textContent = reference.name;
      const settings = document.createElement('details');
      settings.className = 'video-reference-options';
      const summary = document.createElement('summary');
      summary.textContent = 'Reference options';
      const strengthLabel = document.createElement('label');
      strengthLabel.className = 'video-reference-strength';
      const strengthName = document.createElement('span');
      strengthName.textContent = 'Reference influence';
      const strength = document.createElement('input');
      strength.type = 'range';
      strength.min = String(this.minReferenceStrength);
      strength.max = String(this.maxReferenceStrength);
      strength.step = String(this.referenceStrengthStep);
      strength.value = String(reference.strength);
      strength.dataset.action = 'reference-strength';
      strength.dataset.referenceId = reference.id;
      strength.setAttribute('aria-label', 'Reference influence for ' + reference.name);
      const strengthValue = document.createElement('output');
      strengthValue.textContent = Number(reference.strength).toFixed(2);
      const explanation = document.createElement('span');
      explanation.className = 'caption';
      explanation.textContent = 'Adjust only when an image needs more or less influence.';
      strengthLabel.append(strengthName, strength, strengthValue);
      settings.append(summary, strengthLabel, explanation);
      card.append(select, name, remove, settings);
      list.append(card);
    });
    this.renderMediaEmptyState();
  }

  renderSourceVideos() {
    const list = document.getElementById('video-source-list');
    const count = document.getElementById('video-source-count');
    if (!list || !count) return;
    const sources = this.clips.filter((clip) => clip.kind === 'source');
    count.textContent = sources.length + (sources.length === 1 ? ' clip' : ' clips');
    list.replaceChildren();
    if (!sources.length) {
      this.renderMediaEmptyState();
      return;
    }
    sources.forEach((clip) => {
      const item = document.createElement('div');
      item.className = 'video-source-item';
      const select = document.createElement('button');
      select.type = 'button';
      select.className = 'video-source';
      if (clip.id === this.selectedClipId) select.classList.add('selected');
      select.dataset.action = 'select-clip';
      select.dataset.clipId = clip.id;
      select.setAttribute('aria-label', 'Select source video ' + clip.name);
      select.setAttribute('aria-pressed', String(clip.id === this.selectedClipId));
      const thumbnail = document.createElement('span');
      thumbnail.className = 'video-source-thumb';
      thumbnail.textContent = 'VIDEO';
      const name = document.createElement('span');
      name.className = 'video-source-name';
      name.textContent = clip.name;
      const duration = document.createElement('span');
      duration.className = 'video-source-duration';
      duration.textContent = clip.duration ? formatTime(clip.duration) : 'Loading';
      select.append(thumbnail, name, duration);
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'video-source-remove';
      remove.dataset.action = 'remove-clip';
      remove.dataset.clipId = clip.id;
      remove.setAttribute('aria-label', 'Remove source video ' + clip.name);
      remove.textContent = '×';
      item.append(select, remove);
      list.append(item);
    });
    this.renderMediaEmptyState();
  }

  renderMediaEmptyState() {
    const sourceGroup = document.getElementById('video-source-group');
    const referenceTray = document.getElementById('video-reference-tray');
    const emptyState = document.getElementById('video-media-empty');
    if (!sourceGroup || !referenceTray || !emptyState) return;
    const hasSources = this.clips.some((clip) => clip.kind === 'source');
    const hasReferences = this.imageReferences.length > 0;
    sourceGroup.hidden = !hasSources;
    referenceTray.hidden = !hasReferences;
    emptyState.hidden = hasSources || hasReferences;
  }

  requestPayload(settings) {
    return {
      prompt: settings.prompt,
      backend: settings.backend,
      request_id: settings.requestId,
      width: settings.width,
      height: settings.height,
      num_frames: settings.numFrames,
      frame_rate: settings.frameRate,
      seed: settings.seed,
      references: this.imageReferences.map(function (reference) {
        return {
          name: reference.name,
          image: reference.base64,
          frame_index: reference.frameIndex,
          strength: reference.strength,
        };
      }),
    };
  }

  clearError() {
    this.error = '';
    this.renderError();
  }

  setError(message) {
    this.error = message;
    this.renderError();
  }

  async addGeneratedClip(blob, settings) {
    const metadata = videoMetadata(settings);
    const clip = {
      id: 'video-' + crypto.randomUUID(),
      kind: 'generated',
      name: metadata.modelName + ' ' + Math.round(settings.duration) + 's',
      url: URL.createObjectURL(blob),
      objectUrl: true,
      mp4Blob: blob,
      thumbnailBlob: null,
      duration: metadata.numFrames / metadata.frameRate,
      metadata: metadata,
      createdAt: Date.now(),
    };
    this.addClip(clip);
    const saved = await this.persistVideo(clip);
    this.renderVideoGallery();
    this.createThumbnail(clip);
    return saved;
  }

  addStubClip(result, settings) {
    const duration = result.num_frames / result.frame_rate;
    const metadata = videoMetadata(settings, result);
    this.addClip({
      id: 'clip-' + nextClipId++,
      kind: 'generated',
      name: metadata.modelName + ' stub ' + Math.round(duration) + 's',
      url: null,
      objectUrl: false,
      duration: duration,
      stub: true,
      metadata: metadata,
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
    this.renderError();
    this.renderSourceVideos();
    this.renderSelectedClip();
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
    if (action === 'add-video') document.getElementById('video-upload').click();
    if (action === 'add-image') document.getElementById('video-image-upload').click();
    if (action === 'remove-reference') this.removeImageReference(control.dataset.referenceId);
    if (action === 'select-reference') this.selectReference(control.dataset.referenceId);
    if (action === 'remove-clip') this.removeClip(control.dataset.clipId);
    if (action === 'download-all-videos') this.downloadAllVideos();
    if (action === 'clear-video-gallery') this.clearVideoGallery();
    if (action === 'select-clip') this.selectClip(control.dataset.clipId);
    if (action === 'capture-video-frame') this.captureFrameForVideo();
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
    if (control.id === 'video-upload') this.onVideoFiles(event);
    if (control.id === 'video-image-upload') this.onImageFiles(event);
  }

  onComponentInput(event) {
    const control = event.target;
    if (!(control instanceof HTMLInputElement)) return;
    if (control.dataset.action === 'reference-strength') {
      this.setReferenceStrength(control.dataset.referenceId, control);
    }
  }

  onVideoFiles(event) {
    const input = event.target;
    const files = Array.from(input.files || []);
    input.value = '';
    this.addVideoFiles(files, this.captureInputEpoch());
  }

  addVideoFiles(files, epoch = this.captureInputEpoch()) {
    if (!this.canCommitInput(epoch)) return;
    const videos = Array.from(files).filter(isVideoFile);
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
        url: URL.createObjectURL(file),
        objectUrl: true,
        duration: 0,
      };
      this.clips = this.clips.concat(clip);
      if (index === 0) this.selectedClipId = clip.id;
    });
    if (hasUnsupported) this.setError('Choose a video file.');
    else this.clearError();
    this.renderSourceVideos();
    this.renderSelectedClip();
  }

  async onImageFiles(event) {
    const input = event.target;
    const files = Array.from(input.files || []);
    input.value = '';
    await this.addImageFiles(files, this.captureInputEpoch());
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
    const images = Array.from(files).filter(isImageFile);
    const videos = Array.from(files).filter(isVideoFile);
    const unsupported = Array.from(files).filter((file) => !isImageFile(file) && !isVideoFile(file));
    if (images.length) await this.addImageFiles(images, epoch);
    if (!this.canCommitInput(epoch)) return;
    if (videos.length) this.addVideoFiles(videos, epoch);
    if (unsupported.length) this.setError('Choose image or video files.');
    else if (images.length || videos.length) this.clearError();
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

  selectClip(id) {
    this.closeOutputPromptSheet(false);
    this.selectedClipId = id;
    this.previewResume = null;
    this.currentTime = 0;
    const clip = this.selectedClip();
    this.duration = clip ? clip.duration || 0 : 0;
    this.error = '';
    this.renderError();
    this.renderSourceVideos();
    this.renderSelectedClip();
  }

  stepClip(delta) {
    const gallery = this.querySelector('#video-gallery');
    const outputs = this.clips.filter((clip) => clip.kind === 'generated');
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

  async removeClip(id) {
    const removed = this.clips.find(function (clip) { return clip.id === id; });
    if (!removed) return;
    if (this.selectedClipId === id) this.closeOutputPromptSheet(false);
    if (removed.kind === 'generated' && !removed.stub && this.galleryStore && this.keepEnabled) {
      const deleted = await this.galleryStore.removeVideo(id);
      if (!deleted) return;
    }
    if (removed) releaseClipUrls(removed);
    this.clips = this.clips.filter(function (clip) { return clip.id !== id; });
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
  }

  async downloadAllVideos() {
    const outputs = this.clips.filter((clip) => clip.kind === 'generated' && !clip.stub && clip.url).reverse();
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
      saveFile(metadataUrl, 'studio-video-metadata.json');
      setTimeout(() => URL.revokeObjectURL(metadataUrl), 10000);
    } catch (error) {
      this.setError('Download all stopped: ' + error.message);
    }
  }

  async clearVideoGallery() {
    const outputs = this.clips.filter((clip) => clip.kind === 'generated');
    if (!outputs.length) return;
    if (this.keepEnabled && this.galleryStore) {
      const cleared = await this.galleryStore.clearVideos();
      if (!cleared) return;
    }
    const selectedWasRemoved = outputs.some((clip) => clip.id === this.selectedClipId);
    this.clips = this.clips.filter((clip) => clip.kind !== 'generated');
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
    this.renderPreview();
    this.renderVideoGallery();
    this.renderOutputDetails();
  }

  renderOutputDetails() {
    const root = this.querySelector('#video-output-details-root');
    if (!root) return;
    const clip = this.selectedClip();
    const pending = Boolean(this.generationProgress && this.pendingRender);
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
      if (duration) facts.push(duration.toFixed(2) + ' sec');
      if (metadata.width && metadata.height) facts.push(metadata.width + ' × ' + metadata.height);
      if (metadata.frameRate) facts.push(metadata.frameRate + ' fps');
      if (metadata.numFrames) facts.push(metadata.numFrames + ' frames');
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
          ${canCapture ? html`
            <button class="icon-btn" type="button" data-action="capture-video-frame"
              aria-label="Add this frame as an image reference" title="Add this frame as an image reference">
              <svg class="icon" aria-hidden="true"><use href="#i-image-in"></use></svg>
            </button>` : nothing}
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
    if (canCapture) {
      menu.append(menuItem('image-in', 'Use current frame in Image', () => this.captureFrameForImage()));
    }
    if (this.supportsSeed && seed !== null) {
      menu.append(menuItem('hash', 'Reuse seed ' + seed, () => this.reuseOutput({seed})));
    }
    if (metadata?.prompt) {
      menu.append(menuItem('text', 'Reuse prompt', () => this.reuseOutput({prompt: metadata.prompt})));
    }
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
    const content = this.generationProgress
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

  // The run reports the whole render's steps, not one stage's, because the
  // distilled pipeline denoises the clip in two stages and a number that reset
  // between them read as if the render were about to finish. So the bar fills to
  // the share of the whole render that is done, and the page shows that share as
  // one percentage. A step arrives as it starts, so the count reads as the step
  // the engine is on. Before the engine reports a step there is nothing to fill
  // to, and the bar sweeps instead.
  generationProgressDetails(progress) {
    const label = progress.stopping ? 'Stopping video' : 'Generating video';
    const elapsed = formatTime(progress.elapsedSeconds);
    const total = Number(progress.total) || 0;
    const step = Number(progress.step) || 0;
    const percent = total > 0 ? Math.max(0, Math.min(100, Math.round(step / total * 100))) : null;
    return {
      label,
      elapsed: elapsed + ' elapsed',
      percent,
      readout: percent === null ? elapsed + ' elapsed' : percent + '%, ' + elapsed + ' elapsed',
    };
  }

  renderProgressPlaceholder(progress) {
    const details = this.generationProgressDetails(progress);
    const status = html`
      <section id="video-render-status" class="video-render-placeholder" role="status"
        aria-label=${details.label} aria-atomic="true">
        <div class="video-render-content">
          <strong>${details.label}</strong>
          <div id="video-render-progress"
            class=${details.percent === null ? 'video-render-progress is-indeterminate' : 'video-render-progress'}
            role="progressbar" aria-label=${details.label} aria-valuemin="0" aria-valuemax="100"
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

  renderError() {
    const errorRoot = this.querySelector('#video-error-root');
    if (errorRoot) renderTemplate(this.error ? html`<p class="video-error" role="alert">${this.error}</p>` : '', errorRoot);
  }

  renderGallery() {
    const outputs = this.clips.filter((clip) => clip.kind === 'generated');
    const downloadable = outputs.filter((clip) => !clip.stub && clip.url);
    const kept = outputs.filter((clip) => clip.keptInBrowser).length;
    const videoCount = outputs.length + (outputs.length === 1 ? ' video' : ' videos');
    const note = !outputs.length
      ? this.keepEnabled ? 'Videos are kept in this browser.' : 'Videos stay in this tab only.'
      : kept === outputs.length ? videoCount + ', kept in this browser.'
        : downloadable.length ? videoCount + ' in this tab. Download the ones you want to keep.'
          : (outputs.length === 1 ? 'A stub result' : outputs.length + ' stub results') + ' in this tab.';
    return html`
      <section class="video-gallery strip-wrap" id="video-gallery" aria-label="Video gallery"
        ?hidden=${!outputs.length && !this.pendingRender}>
        <div class="strip-head video-gallery-head">
          <span id="video-gallery-note">${note}</span>
          <span class="strip-actions">
            <button class="text-btn" type="button" id="video-gallery-download"
              data-action="download-all-videos" ?hidden=${!downloadable.length}>Download all</button>
            <button class="text-btn" type="button" id="video-gallery-clear"
              data-action="clear-video-gallery" ?hidden=${!outputs.length}>Clear all</button>
          </span>
        </div>
        <div class="strip video-clips" role="group" aria-label="Generated videos">
          ${this.pendingRender ? html`
            <div class="video-gallery-item video-gallery-pending frame pending" role="status" aria-label="Video render pending">
              <span class="still video-clip-thumb pending-thumb">
                <span class="video-pending-indicator" aria-hidden="true"></span>
                <span>Rendering</span>
              </span>
              <span class="no">${String(outputs.length + 1).padStart(2, '0')}</span>
            </div>` : ''}
          ${outputs.length ? outputs.map((clip, index) => html`
            <div class="video-gallery-item">
              <button class="frame video-clip${clip.id === this.selectedClipId ? ' selected' : ''}"
                type="button" aria-label=${'Select video ' + clip.name} aria-pressed=${clip.id === this.selectedClipId}
                data-action="select-clip" data-clip-id=${clip.id}>
                <span class="still video-clip-thumb">
                  ${clip.thumbnailUrl
                    ? html`<img src=${clip.thumbnailUrl} alt="">`
                    : html`<span class="video-clip-placeholder" title=${clip.thumbnailError || ''}>
                      ${clip.stub ? 'STUB' : clip.thumbnailError ? 'NO PREVIEW' : 'PREVIEW'}
                    </span>`}
                  <span class="video-clip-duration">${formatTime(clip.duration || 0)}</span>
                </span>
                <span class="no">${String(index + 1).padStart(2, '0')}</span>
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
          <div id="video-error-root"></div>
          <div id="video-gallery-root"></div>
        </div>
      </div>
    `;
  }
}

customElements.define('video-studio', VideoStudio);
