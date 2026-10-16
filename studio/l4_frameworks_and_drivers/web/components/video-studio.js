import { LitElement, html, nothing, render as renderTemplate } from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';

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

function releaseClipUrls(clip) {
  if (clip.objectUrl) URL.revokeObjectURL(clip.url);
  if (clip.thumbnailUrl) URL.revokeObjectURL(clip.thumbnailUrl);
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
  currentTime = 0;
  duration = 0;
  frameLimit = null;
  outputWidth = 16;
  outputHeight = 9;
  outputFrameRate = 24;
  outputModelName = 'Video';
  draggedReferenceId = null;
  previewResizeObserver = null;
  error = '';
  handleSourceClick = (event) => this.onComponentClick(event);
  handleSourceChange = (event) => this.onComponentChange(event);
  handleSourceInput = (event) => this.onComponentInput(event);
  handleSourceDragOver = (event) => this.onSourceDragOver(event);
  handleSourceDragLeave = (event) => this.onSourceDragLeave(event);
  handleSourceDrop = (event) => this.onSourceDrop(event);
  handleDocumentPaste = (event) => this.onPaste(event);
  handleDocumentKeydown = (event) => this.onShortcutPaste(event);
  handleTimelinePointerDown = (event) => this.onTimelinePointerDown(event);
  handleTimelinePointerMove = (event) => this.onTimelinePointerMove(event);
  handleTimelinePointerUp = (event) => this.onTimelinePointerUp(event);
  handleTimelineKeydown = (event) => this.onTimelineKeydown(event);

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    this.sourcePanel = document.getElementById('video-source-panel');
    this.addEventListener('click', this.onComponentClick);
    this.addEventListener('change', this.onComponentChange);
    this.addEventListener('input', this.onComponentInput);
    this.addEventListener('loadedmetadata', this.onMetadata, true);
    this.addEventListener('timeupdate', this.onTimeUpdate, true);
    document.addEventListener('paste', this.handleDocumentPaste);
    document.addEventListener('keydown', this.handleDocumentKeydown);
    this.addEventListener('pointerdown', this.handleTimelinePointerDown);
    this.addEventListener('pointermove', this.handleTimelinePointerMove);
    this.addEventListener('pointerup', this.handleTimelinePointerUp);
    this.addEventListener('pointercancel', this.handleTimelinePointerUp);
    this.addEventListener('keydown', this.handleTimelineKeydown);
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
    this.removeEventListener('change', this.onComponentChange);
    this.removeEventListener('input', this.onComponentInput);
    this.removeEventListener('loadedmetadata', this.onMetadata, true);
    this.removeEventListener('timeupdate', this.onTimeUpdate, true);
    document.removeEventListener('paste', this.handleDocumentPaste);
    document.removeEventListener('keydown', this.handleDocumentKeydown);
    this.removeEventListener('pointerdown', this.handleTimelinePointerDown);
    this.removeEventListener('pointermove', this.handleTimelinePointerMove);
    this.removeEventListener('pointerup', this.handleTimelinePointerUp);
    this.removeEventListener('pointercancel', this.handleTimelinePointerUp);
    this.removeEventListener('keydown', this.handleTimelineKeydown);
    if (this.sourcePanel) {
      this.sourcePanel.removeEventListener('click', this.handleSourceClick);
      this.sourcePanel.removeEventListener('change', this.handleSourceChange);
      this.sourcePanel.removeEventListener('input', this.handleSourceInput);
      this.sourcePanel.removeEventListener('dragover', this.handleSourceDragOver);
      this.sourcePanel.removeEventListener('dragleave', this.handleSourceDragLeave);
      this.sourcePanel.removeEventListener('drop', this.handleSourceDrop);
    }
    if (this.previewResizeObserver) this.previewResizeObserver.disconnect();
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
      this.previewResizeObserver = new ResizeObserver(() => this.fitProgressPlaceholder());
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
      };
      this.addClip(clip);
      if (!clip.thumbnailBlob) this.createThumbnail(clip);
    });
  }

  setKeeping(keeping) {
    this.keepEnabled = keeping;
    if (keeping) return this.persistGeneratedVideos();
    return Promise.resolve();
  }

  persistGeneratedVideos() {
    const saves = this.clips.filter((clip) => clip.kind === 'generated' && !clip.stub)
      .map((clip) => this.persistVideo(clip));
    return Promise.all(saves);
  }

  persistVideo(clip) {
    if (!this.keepEnabled || !this.galleryStore) return Promise.resolve(false);
    return this.galleryStore.keepVideo(clip, clip.mp4Blob, clip.thumbnailBlob);
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
    this.renderTimelineView(this.selectedClip());
  }

  removeImageReference(id) {
    this.imageReferences = this.imageReferences.filter(function (reference) { return reference.id !== id; });
    if (this.selectedReferenceId === id) {
      this.selectedReferenceId = this.imageReferences.length ? this.imageReferences[0].id : null;
    }
    this.renderImageReferences();
    this.renderTimelineView(this.selectedClip());
  }

  clearImageReferences() {
    this.imageReferences = [];
    this.selectedReferenceId = null;
    this.renderImageReferences();
    this.renderTimelineView(this.selectedClip());
  }

  selectReference(id) {
    if (!this.imageReferences.some(function (reference) { return reference.id === id; })) return;
    this.selectedReferenceId = id;
    this.renderImageReferences();
    this.renderTimelineView(this.selectedClip());
  }

  setReferenceFrame(id, value) {
    const reference = this.imageReferences.find((item) => item.id === id);
    if (!reference) return;
    const focusedMarker = document.activeElement?.dataset.referenceId === id
      && document.activeElement.classList.contains('timeline-reference-marker');
    reference.frameIndex = Number(value);
    this.renderImageReferences();
    this.renderTimelineView(this.selectedClip());
    if (focusedMarker) {
      const marker = Array.from(this.querySelectorAll('.timeline-reference-marker'))
        .find((item) => item.dataset.referenceId === id);
      if (marker) marker.focus();
    }
  }

  setFrameLimit(frameCount) {
    this.frameLimit = frameCount;
    document.querySelectorAll('#video-source-panel [data-action="reference-frame"]').forEach((control) => {
      control.max = String(frameCount - 1);
    });
    this.renderTimelineView(this.selectedClip());
  }

  setModelCapabilities(capabilities) {
    this.outputFrameRate = capabilities.frame_rate;
    this.maxReferences = capabilities.max_references;
    this.minReferenceStrength = capabilities.min_reference_strength;
    this.maxReferenceStrength = capabilities.max_reference_strength;
    this.referenceStrengthStep = capabilities.reference_strength_step;
    this.defaultReferenceStrength = capabilities.default_reference_strength;
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
      const empty = document.createElement('span');
      empty.className = 'video-ref-empty';
      empty.textContent = 'Add an image or capture a source frame.';
      list.append(empty);
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
      const settings = document.createElement('div');
      settings.className = 'video-reference-settings';
      const name = document.createElement('span');
      name.className = 'video-reference-name';
      name.textContent = reference.name;
      const frameLabel = document.createElement('label');
      frameLabel.textContent = 'Output frame';
      const frameIndex = document.createElement('input');
      frameIndex.type = 'number';
      frameIndex.min = '0';
      frameIndex.max = String(Math.max(0, (this.frameLimit || 1) - 1));
      frameIndex.step = '1';
      frameIndex.value = String(reference.frameIndex);
      frameIndex.dataset.action = 'reference-frame';
      frameIndex.dataset.referenceId = reference.id;
        frameIndex.setAttribute('aria-label', 'Output frame for ' + reference.name);
      frameLabel.append(frameIndex);
      const strengthLabel = document.createElement('label');
      strengthLabel.textContent = 'Strength';
      const strength = document.createElement('input');
      strength.type = 'range';
      strength.min = String(this.minReferenceStrength);
      strength.max = String(this.maxReferenceStrength);
      strength.step = String(this.referenceStrengthStep);
      strength.value = String(reference.strength);
      strength.dataset.action = 'reference-strength';
      strength.dataset.referenceId = reference.id;
      strength.setAttribute('aria-label', 'Reference strength for ' + reference.name);
      const strengthValue = document.createElement('output');
      strengthValue.textContent = Number(reference.strength).toFixed(2);
      strengthLabel.append(strength, strengthValue);
      settings.append(frameLabel, strengthLabel);
      card.append(select, name, remove, settings);
      list.append(card);
    });
  }

  renderSourceVideos() {
    const list = document.getElementById('video-source-list');
    const count = document.getElementById('video-source-count');
    if (!list || !count) return;
    const sources = this.clips.filter((clip) => clip.kind === 'source');
    count.textContent = sources.length + (sources.length === 1 ? ' clip' : ' clips');
    list.replaceChildren();
    if (!sources.length) {
      const empty = document.createElement('span');
      empty.className = 'video-source-empty';
      empty.textContent = 'Add a clip to choose frames from it.';
      list.append(empty);
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
    if (action === 'add-video') document.getElementById('video-upload').click();
    if (action === 'add-image') document.getElementById('video-image-upload').click();
    if (action === 'remove-reference') this.removeImageReference(control.dataset.referenceId);
    if (action === 'select-reference') this.selectReference(control.dataset.referenceId);
    if (action === 'remove-clip') this.removeClip(control.dataset.clipId);
    if (action === 'select-clip') this.selectClip(control.dataset.clipId);
    if (action === 'capture-video-frame') this.captureFrameForVideo();
    if (action === 'capture-image-frame') this.captureFrameForImage();
  }

  onComponentChange(event) {
    const control = event.target;
    if (!(control instanceof HTMLInputElement)) return;
    if (control.id === 'video-upload') this.onVideoFiles(event);
    if (control.id === 'video-image-upload') this.onImageFiles(event);
    if (control.dataset.action === 'reference-frame') {
      this.setReferenceFrame(control.dataset.referenceId, control.value);
    }
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

  onTimelinePointerDown(event) {
    const marker = event.target.closest('.timeline-reference-marker');
    if (!marker || event.button !== 0) return;
    this.draggedReferenceId = marker.dataset.referenceId;
    this.selectedReferenceId = this.draggedReferenceId;
    this.renderImageReferences();
    marker.classList.add('selected');
    marker.setPointerCapture(event.pointerId);
    this.moveTimelineReference(marker, event.clientX);
    event.preventDefault();
  }

  onTimelinePointerMove(event) {
    if (!this.draggedReferenceId) return;
    const marker = Array.from(this.querySelectorAll('.timeline-reference-marker'))
      .find((item) => item.dataset.referenceId === this.draggedReferenceId);
    if (marker) this.moveTimelineReference(marker, event.clientX);
  }

  onTimelinePointerUp() {
    if (!this.draggedReferenceId) return;
    this.draggedReferenceId = null;
    this.renderTimelineView(this.selectedClip());
  }

  onTimelineKeydown(event) {
    const marker = event.target.closest('.timeline-reference-marker');
    if (!marker) return;
    const reference = this.imageReferences.find((item) => item.id === marker.dataset.referenceId);
    if (!reference) return;
    const lastFrame = Math.max(0, (this.frameLimit || 1) - 1);
    const increment = event.shiftKey ? 10 : 1;
    let frameIndex = reference.frameIndex;
    if (event.key === 'ArrowLeft') frameIndex -= increment;
    else if (event.key === 'ArrowRight') frameIndex += increment;
    else if (event.key === 'Home') frameIndex = 0;
    else if (event.key === 'End') frameIndex = lastFrame;
    else return;
    event.preventDefault();
    this.selectedReferenceId = reference.id;
    this.setReferenceFrame(reference.id, Math.max(0, Math.min(lastFrame, frameIndex)));
  }

  moveTimelineReference(marker, clientX) {
    const reference = this.imageReferences.find((item) => item.id === marker.dataset.referenceId);
    const rail = marker.closest('.timeline-rail');
    if (!reference || !rail) return;
    const bounds = rail.getBoundingClientRect();
    const fraction = Math.min(1, Math.max(0, (clientX - bounds.left) / bounds.width));
    const lastFrame = Math.max(0, (this.frameLimit || 1) - 1);
    reference.frameIndex = Math.round(fraction * lastFrame);
    this.updateTimelineReference(marker, reference, lastFrame);
  }

  updateTimelineReference(marker, reference, lastFrame) {
    const frameIndex = reference.frameIndex;
    const position = frameIndex / Math.max(1, lastFrame) * 100;
    marker.style.left = position + '%';
    marker.setAttribute('aria-valuetext', 'Frame ' + frameIndex + ' of ' + lastFrame);
    marker.setAttribute('aria-label', reference.name + ', output frame ' + frameIndex);
    const frameLabel = marker.querySelector('span');
    if (frameLabel) frameLabel.textContent = 'F' + String(frameIndex).padStart(3, '0');
    const field = Array.from(this.sourcePanel.querySelectorAll('[data-action="reference-frame"]'))
      .find((input) => input.dataset.referenceId === reference.id);
    if (field) field.value = String(frameIndex);
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

  selectClip(id) {
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

  async removeClip(id) {
    const removed = this.clips.find(function (clip) { return clip.id === id; });
    if (!removed) return;
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

  onMetadata(event) {
    const clip = this.selectedClip();
    if (!clip) return;
    const video = event.target;
    clip.duration = Number.isFinite(video.duration) ? video.duration : 0;
    if (this.previewResume?.clipId === clip.id) {
      video.currentTime = Math.min(this.previewResume.time, clip.duration);
      this.previewResume = null;
    }
    this.duration = clip.duration;
    this.currentTime = video.currentTime || 0;
    this.renderTimelineView(clip);
    this.renderSourceVideos();
    this.renderVideoGallery();
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

  renderTimeline() {
    const frameCount = Math.max(1, this.frameLimit || 1);
    const lastFrame = frameCount - 1;
    const duration = frameCount / this.outputFrameRate;
    const clip = this.selectedClip();
    const canCapture = Boolean(clip && !clip.stub);
    return html`
      <section class="video-timeline" id="video-timeline" aria-label="Keyframes">
        <header class="timeline-head">
          <div><strong>Keyframes</strong><span>${this.imageReferences.length} ${this.imageReferences.length === 1 ? 'image' : 'images'}, ${frameCount} frames, ${this.outputFrameRate} fps</span></div>
          <div class="timeline-actions">
            ${canCapture ? html`
              <button class="text-btn" type="button" data-action="capture-video-frame">Add frame as keyframe</button>
              <button class="text-btn" type="button" data-action="capture-image-frame">Use current frame in Image</button>
            ` : ''}
          </div>
        </header>
        ${this.imageReferences.length ? html`
          <p class="timeline-purpose">Image anchors set the look at key moments. LTX creates motion between them.</p>
          <div class="timeline-ruler" aria-hidden="true">
            ${[0, 0.25, 0.5, 0.75, 1].map((part) => html`<span>${formatTime(duration * part)}</span>`)}
          </div>
          <div class="timeline-track reference-track" id="video-reference-track" aria-label="Image anchors">
            <span class="track-label">Image anchors</span>
            <div class="timeline-rail">
              ${this.imageReferences.map((reference) => {
                const frameIndex = Number.isFinite(reference.frameIndex) ? reference.frameIndex : 0;
                const position = Math.min(100, Math.max(0, frameIndex / Math.max(1, lastFrame) * 100));
                const selected = reference.id === this.selectedReferenceId;
                return html`<button class="timeline-reference-marker${selected ? ' selected' : ''}" type="button"
                  style=${'left: ' + position + '%'} data-action="select-reference" data-reference-id=${reference.id}
                  aria-label=${reference.name + ', output frame ' + frameIndex}
                  aria-valuetext=${'Frame ' + frameIndex + ' of ' + lastFrame}
                  aria-pressed=${selected} aria-keyshortcuts="ArrowLeft ArrowRight Home End" tabindex="0">
                  <img src=${reference.src} alt="">
                  <span>F${String(frameIndex).padStart(3, '0')}</span>
                </button>`;
              })}
            </div>
          </div>
        ` : html`<p class="timeline-empty">Add an image or capture a frame to set a key moment.</p>`}
      </section>
    `;
  }

  renderSelectedClip() {
    const clip = this.selectedClip();
    this.renderPreview();
    this.renderTimelineView(clip);
    this.renderVideoGallery();
    this.renderOutputDetails();
  }

  renderOutputDetails() {
    const root = this.querySelector('#video-output-details-root');
    if (!root) return;
    const clip = this.selectedClip();
    const pending = this.generationProgress && this.pendingRender;
    const metadata = pending ? videoMetadata(this.pendingRender) : clip?.metadata;
    if (!metadata || (!pending && clip.kind !== 'generated')) {
      renderTemplate('', root);
      return;
    }
    const duration = metadata.numFrames / metadata.frameRate;
    const seed = Number.isInteger(metadata.seed) ? metadata.seed : pending ? 'Assigned at render' : 'Not recorded';
    const references = metadata.references || [];
    const referenceSummary = references.length
      ? references.map((reference) => reference.name + ' at frame ' + reference.frameIndex).join(', ')
      : 'No image references';
    const referenceDetails = references.map((reference) =>
      reference.name + ', frame ' + reference.frameIndex + ', strength ' + Number(reference.strength).toFixed(2))
      .join(', ');
    const timeLabel = pending ? 'Elapsed' : clip.stub ? 'Request time' : 'Render time';
    return renderTemplate(html`
      <section class="video-output-details" id="video-output-details" aria-label="Video output details">
        <div class="video-output-title">
          <strong>${pending ? 'Current render' : clip.name}</strong>
          <span>${pending ? 'Render settings' : 'Output details'}</span>
        </div>
        <div class="video-output-facts">
          <span><small>Model</small><b>${metadata.modelName}</b></span>
          <span><small>Duration</small><b>${duration.toFixed(2)} sec</b></span>
          <span><small>Resolution</small><b>${metadata.width} × ${metadata.height}</b></span>
          <span><small>Frame rate</small><b>${metadata.frameRate} fps</b></span>
          <span><small>Frames</small><b>${metadata.numFrames}</b></span>
          <span><small>Seed</small><b>${seed}</b></span>
          <span><small>${timeLabel}</small><b>${formatTime(metadata.elapsedSeconds)}</b></span>
          <span title=${referenceDetails}><small>References</small><b>${references.length} ${references.length === 1 ? 'image' : 'images'}</b></span>
        </div>
        <p class="video-output-prompt" title=${metadata.prompt || ''}>${metadata.prompt || 'No prompt recorded'}</p>
        <p class="video-output-references" title=${referenceDetails}>${referenceSummary}</p>
      </section>`, root);
  }

  renderPreview() {
    const preview = this.querySelector('#video-preview-content-root');
    if (!preview) return;
    const content = this.generationProgress
      ? this.renderProgressPlaceholder(this.generationProgress)
      : this.renderClip(this.selectedClip());
    renderTemplate(content, preview);
    if (this.generationProgress) this.fitProgressPlaceholder();
  }

  fitProgressPlaceholder() {
    const status = this.querySelector('#video-render-status');
    const preview = this.querySelector('#video-preview-content-root');
    if (!status || !preview || !preview.clientWidth || !preview.clientHeight) return;
    const ratio = this.outputWidth / this.outputHeight;
    const width = Math.min(1200, preview.clientWidth, preview.clientHeight * ratio);
    status.style.width = Math.floor(width) + 'px';
    status.style.height = Math.floor(width / ratio) + 'px';
  }

  generationProgressDetails(progress) {
    let label = 'Preparing render';
    let phaseNumber = 0;
    let percent = null;
    if (progress.stopping) {
      label = 'Stopping render';
      phaseNumber = progress.phase > 1 ? 2 : 1;
    } else if (progress.stage === 'preparing') {
      label = 'Loading LTX-2.5';
    } else {
      phaseNumber = progress.phase > 1 ? 2 : 1;
      if (phaseNumber === 1) {
        label = progress.total > 0 && progress.step >= progress.total
          ? 'Base generation complete' : 'Base generation at half resolution';
      } else if (progress.total > 0 && progress.step >= progress.total) {
        label = 'Finalizing video';
      } else {
        label = 'Upscaling and refining';
      }
      if (progress.total > 0 && progress.step < progress.total) {
        percent = Math.round(Math.min(1, progress.step / progress.total) * 100);
      } else if (phaseNumber === 1 && progress.total > 0) {
        percent = 100;
      }
    }
    const elapsed = formatTime(progress.elapsedSeconds);
    const phase = phaseNumber ? 'Stage ' + phaseNumber + ' of 2' : 'Preparing render';
    const progressLabel = phaseNumber === 1 ? 'Base generation progress' : 'Upscaling and refinement progress';
    const text = percent === null
      ? label + ', ' + elapsed + ' elapsed'
      : label + ', ' + percent + '% of this stage, ' + elapsed + ' elapsed';
    return {label, phaseNumber, phase, percent, elapsed, progressLabel, text};
  }

  renderProgressPlaceholder(progress) {
    const details = this.generationProgressDetails(progress);
    const width = details.percent === null ? 0 : details.percent;
    return html`
      <section id="video-render-status" class="video-render-placeholder" role="status"
        aria-label="Video render status" aria-atomic="true"
        style=${'--video-render-ratio: ' + this.outputWidth + ' / ' + this.outputHeight}>
        <div class="video-render-brand"><span>RENDER STATUS</span><span>${this.outputModelName}</span></div>
        <div class="video-render-content">
          <strong>Rendering new clip</strong>
          <span class="video-render-phase">${details.label}</span>
          <div class="video-render-stages" aria-label="LTX generation stages">
            <span class=${details.phaseNumber === 1 ? 'active' : details.phaseNumber > 1 ? 'complete' : ''}>Base generation</span>
            <span class=${details.phaseNumber === 2 ? 'active' : ''}>Upscaling and refining</span>
          </div>
          <div id="video-render-progress" class="video-render-progress${details.percent === null
            ? ' is-indeterminate' : ''}" role="progressbar" aria-label=${details.progressLabel}
            aria-valuemin="0" aria-valuemax="100"
            aria-valuenow=${details.percent === null ? nothing : String(details.percent)}
            aria-valuetext=${details.text} style=${'--video-render-progress: ' + width + '%'}></div>
        </div>
        <div class="video-render-details">
          <span>${details.elapsed} elapsed</span>
          <span>${details.phase}</span>
        </div>
      </section>`;
  }

  renderTimelineView() {
    const previous = this.querySelector('#video-timeline-root');
    if (!previous) return;
    const activeElement = previous.contains(document.activeElement) ? document.activeElement : null;
    const activeMarker = activeElement?.classList.contains('timeline-reference-marker')
      ? activeElement.dataset.referenceId
      : null;
    const activeAction = activeMarker ? null : activeElement?.dataset.action;
    const timeline = document.createElement('div');
    timeline.id = 'video-timeline-root';
    previous.replaceWith(timeline);
    renderTemplate(this.renderTimeline(), timeline);
    if (activeMarker) {
      const marker = Array.from(this.querySelectorAll('.timeline-reference-marker'))
        .find((item) => item.dataset.referenceId === activeMarker);
      marker?.focus();
    } else if (activeAction) {
      const action = Array.from(this.querySelectorAll('#video-timeline-root [data-action]'))
        .find((item) => item.dataset.action === activeAction);
      action?.focus();
    }
  }

  renderVideoGallery() {
    const gallery = this.querySelector('#video-gallery-root');
    if (gallery) renderTemplate(this.renderGallery(), gallery);
  }

  renderError() {
    const errorRoot = this.querySelector('#video-error-root');
    if (errorRoot) renderTemplate(this.error ? html`<p class="video-error" role="alert">${this.error}</p>` : '', errorRoot);
  }

  renderGallery() {
    const outputs = this.clips.filter((clip) => clip.kind === 'generated');
    return html`
      <section class="video-gallery" id="video-gallery" aria-label="Video gallery">
        <div class="video-gallery-head"><strong>Video gallery</strong><span>${outputs.length}${outputs.length === 1 ? ' clip' : ' clips'}</span></div>
        <div class="video-clips">
          ${this.pendingRender ? html`
            <div class="video-gallery-item video-gallery-pending" role="status" aria-label="Video render pending">
              <div class="video-clip-thumb pending-thumb">
                <span class="video-pending-indicator" aria-hidden="true"></span>
                <span>Rendering</span>
              </div>
              <span class="video-clip-name">${this.pendingRender.modelName || 'Video render'}</span>
              <span class="video-clip-state">${this.generationProgress?.stopping ? 'Stopping render' : 'In progress'}</span>
            </div>` : ''}
          ${outputs.length ? outputs.map((clip) => html`
            <div class="video-gallery-item">
              <button class="video-clip${clip.id === this.selectedClipId ? ' selected' : ''}"
                type="button" aria-label=${'Select video ' + clip.name} aria-pressed=${clip.id === this.selectedClipId}
                data-action="select-clip" data-clip-id=${clip.id}>
                <span class="video-clip-thumb">
                  ${clip.thumbnailUrl
                    ? html`<img src=${clip.thumbnailUrl} alt="">`
                    : html`<span class="video-clip-placeholder" title=${clip.thumbnailError || ''}>
                      ${clip.stub ? 'STUB' : clip.thumbnailError ? 'NO PREVIEW' : 'PREVIEW'}
                    </span>`}
                  <span class="video-clip-duration">${formatTime(clip.duration || 0)}</span>
                </span>
                <span class="video-clip-name">${clip.name}</span>
              </button>
              <button class="video-clip-remove" type="button" aria-label=${'Remove video ' + clip.name}
                data-action="remove-clip" data-clip-id=${clip.id}>Remove</button>
            </div>`) : this.pendingRender ? '' : html`<span class="video-gallery-empty">Generated clips appear here.</span>`}
        </div>
      </section>`;
  }

  renderClip(clip) {
    if (!clip) {
      return html`<div class="video-empty">
        <div class="video-empty-mark">VIDEO</div>
        <strong>Preview a video</strong>
        <span>Select a source video or generated clip.</span>
        <span>Capture a still to add it as a keyframe.</span>
      </div>`;
    }
    return html`<div class="video-preview-pane">
      <video id="video-preview" src=${clip.url} ?hidden=${clip.stub} controls playsinline preload="metadata"></video>
      <div class="video-preview-stub" ?hidden=${!clip.stub}>
        <div class="video-empty-mark">STUB</div>
        <strong>Request flow verified</strong>
        <span>The stub returns metadata only. It does not create a video file.</span>
        <span class="video-source-label">${clip.name}</span>
      </div>
      <span class="video-source-label" ?hidden=${clip.stub}>${clip.name}</span>
    </div>`;
  }

  render() {
    return html`
      <div class="video-studio-shell">
        <div class="video-preview-area" id="video-preview-root">
          <div id="video-preview-content-root"></div>
        </div>
        <div id="video-output-details-root"></div>
        <div class="video-editing-area">
          <div id="video-timeline-root"></div>
          <div id="video-error-root"></div>
          <div id="video-gallery-root"></div>
        </div>
      </div>
    `;
  }
}

customElements.define('video-studio', VideoStudio);
