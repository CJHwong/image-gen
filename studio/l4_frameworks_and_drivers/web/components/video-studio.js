import { LitElement, html, render as renderTemplate } from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';

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

class VideoStudio extends LitElement {
  clips = [];
  imageReferences = [];
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
  error = '';
  handleSourceClick = (event) => this.onComponentClick(event);
  handleSourceChange = (event) => this.onComponentChange(event);
  handleSourceInput = (event) => this.onComponentInput(event);
  handleSourceDragOver = (event) => this.onSourceDragOver(event);
  handleSourceDragLeave = (event) => this.onSourceDragLeave(event);
  handleSourceDrop = (event) => this.onSourceDrop(event);
  handleDocumentPaste = (event) => this.onPaste(event);

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
    if (this.sourcePanel) {
      this.sourcePanel.removeEventListener('click', this.handleSourceClick);
      this.sourcePanel.removeEventListener('change', this.handleSourceChange);
      this.sourcePanel.removeEventListener('input', this.handleSourceInput);
      this.sourcePanel.removeEventListener('dragover', this.handleSourceDragOver);
      this.sourcePanel.removeEventListener('dragleave', this.handleSourceDragLeave);
      this.sourcePanel.removeEventListener('drop', this.handleSourceDrop);
    }
    super.disconnectedCallback();
    this.clips.forEach(function (clip) {
      if (clip.objectUrl) URL.revokeObjectURL(clip.url);
    });
  }

  firstUpdated() {
    this.renderImageReferences();
    this.renderSourceVideos();
    this.renderSelectedClip();
    this.renderError();
  }

  addImageReference(reference) {
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

  selectReference(id) {
    if (!this.imageReferences.some(function (reference) { return reference.id === id; })) return;
    this.selectedReferenceId = id;
    this.renderImageReferences();
    this.renderTimelineView(this.selectedClip());
  }

  setReferenceFrame(id, value) {
    const reference = this.imageReferences.find((item) => item.id === id);
    if (!reference) return;
    reference.frameIndex = Number(value);
    this.renderImageReferences();
    this.renderTimelineView(this.selectedClip());
  }

  setFrameLimit(frameCount) {
    this.frameLimit = frameCount;
    document.querySelectorAll('#video-source-panel [data-action="reference-frame"]').forEach((control) => {
      control.max = String(frameCount - 1);
    });
    this.renderTimelineView(this.selectedClip());
  }

  setModelCapabilities(capabilities) {
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
      + (this.imageReferences.length === 1 ? ' keyframe' : ' keyframes');
    list.replaceChildren();
    if (!this.imageReferences.length) {
      const empty = document.createElement('span');
      empty.className = 'video-ref-empty';
      empty.textContent = 'Add an image or paste with ⌘V. Each still becomes a keyframe.';
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
      frameLabel.textContent = 'Frame';
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
      empty.textContent = 'Add a clip to scrub frames from it.';
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

  addGeneratedClip(blob, settings) {
    const duration = settings.numFrames / settings.frameRate;
    this.addClip({
      id: 'clip-' + nextClipId++,
      kind: 'generated',
      name: (settings.modelName || 'Video') + ' ' + Math.round(settings.duration) + 's',
      url: URL.createObjectURL(blob),
      objectUrl: true,
      duration: duration,
    });
  }

  addStubClip(result) {
    const duration = result.num_frames / result.frame_rate;
    this.addClip({
      id: 'clip-' + nextClipId++,
      kind: 'generated',
      name: 'LTX-2.5 stub ' + Math.round(duration) + 's',
      url: null,
      objectUrl: false,
      duration: duration,
      stub: true,
    });
  }

  addClip(clip) {
    this.clips = this.clips.concat(clip);
    this.selectedClipId = clip.id;
    this.currentTime = 0;
    this.duration = clip.duration || 0;
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
    if (control.id === 'video-playhead') this.seek(event);
    if (control.dataset.action === 'reference-strength') {
      this.setReferenceStrength(control.dataset.referenceId, control);
    }
  }

  onVideoFiles(event) {
    const input = event.target;
    const files = Array.from(input.files || []);
    input.value = '';
    this.addVideoFiles(files);
  }

  addVideoFiles(files) {
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
    await this.addImageFiles(files);
  }

  async addImageFiles(files) {
    for (const file of files) {
      if (!isImageFile(file)) {
        this.setError('Choose an image file.');
        continue;
      }
      try {
        const src = await readDataUrl(file);
        this.addImageReference({
          id: 'video-ref-' + nextClipId++,
          name: file.name,
          src: src,
          base64: src.slice(src.indexOf(',') + 1),
        });
      } catch (error) {
        this.setError('The image could not be added: ' + error.message);
      }
    }
  }

  async addMediaFiles(files) {
    const images = Array.from(files).filter(isImageFile);
    const videos = Array.from(files).filter(isVideoFile);
    const unsupported = Array.from(files).filter((file) => !isImageFile(file) && !isVideoFile(file));
    if (images.length) await this.addImageFiles(images);
    if (videos.length) this.addVideoFiles(videos);
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
    this.addMediaFiles(media);
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
    this.currentTime = 0;
    const clip = this.selectedClip();
    this.duration = clip ? clip.duration || 0 : 0;
    this.error = '';
    this.renderError();
    this.renderSourceVideos();
    this.renderSelectedClip();
  }

  removeClip(id) {
    const removed = this.clips.find(function (clip) { return clip.id === id; });
    if (removed && removed.objectUrl) URL.revokeObjectURL(removed.url);
    this.clips = this.clips.filter(function (clip) { return clip.id !== id; });
    if (this.selectedClipId === id) {
      this.selectedClipId = this.clips.length ? this.clips[0].id : null;
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
    this.duration = clip.duration;
    this.currentTime = video.currentTime || 0;
    this.renderTimelineView(clip);
    this.renderSourceVideos();
    this.renderVideoGallery();
  }

  onTimeUpdate(event) {
    this.currentTime = event.target.currentTime || 0;
    this.drawPlayhead();
    this.renderTimecode();
  }

  drawPlayhead() {
    const track = this.querySelector('.source-track');
    if (!track || !this.duration) return;
    const position = Math.min(100, Math.max(0, this.currentTime / this.duration * 100));
    track.style.setProperty('--playhead', position + '%');
  }

  seek(event) {
    const video = this.querySelector('#video-preview');
    if (!video || !this.duration) return;
    video.currentTime = Number(event.target.value);
    this.currentTime = video.currentTime;
    this.drawPlayhead();
    this.renderTimecode();
  }

  captureFrameForImage() {
    return this.captureFrame('image');
  }

  captureFrameForVideo() {
    return this.captureFrame('video');
  }

  async captureFrame(target) {
    const video = this.querySelector('#video-preview');
    const clip = this.selectedClip();
    if (!video || !clip || video.readyState < 2 || !video.videoWidth || !video.videoHeight) {
      this.setError('Wait for the video frame to load, then try again.');
      return;
    }
    try {
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
      this.dispatchEvent(new CustomEvent('video-frame-captured', {
        detail: {
          blob: blob,
          name: clip.name + ' frame ' + formatTime(video.currentTime),
          target: target,
          frameIndex: Math.round(video.currentTime * 24),
        },
        bubbles: true,
        composed: true,
      }));
      this.clearError();
    } catch (error) {
      this.setError('The frame could not be captured: ' + error.message);
    }
  }

  renderTimeline(clip) {
    const duration = clip ? this.duration || clip.duration || 1 : 0;
    const quarter = duration / 4;
    const frameSpan = Math.max(1, (this.frameLimit || 1) - 1);
    return html`
      <section class="video-timeline" id="video-timeline" aria-label="Video timeline">
        <header class="timeline-head">
          <div><strong>Timeline</strong><span class="track-name">V1</span></div>
          <output id="video-timecode"><span id="video-timecode-value"></span></output>
          <div class="timeline-actions">
            <button class="text-btn" type="button" data-action="capture-video-frame" ?disabled=${!clip || clip.stub}>Add frame to Video</button>
            <button class="text-btn" type="button" data-action="capture-image-frame" ?disabled=${!clip || clip.stub}>Use this frame in Image</button>
          </div>
        </header>
        ${clip ? html`
          <div class="timeline-ruler" aria-hidden="true">
            <span>00:00</span><span>${formatTime(quarter)}</span>
            <span>${formatTime(quarter * 2)}</span><span>${formatTime(quarter * 3)}</span>
            <span>${formatTime(duration)}</span>
          </div>` : html`<p class="source-empty">Choose a source video in the sidebar to scrub it and capture a frame.</p>`}
        <div class="timeline-track source-track" style=${'--playhead: ' + (clip ? Math.min(100, this.currentTime / duration * 100) : 0) + '%'}>
          <span class="track-name">V1</span>
          <div class="timeline-rail">
            <div class="timeline-clip${clip ? '' : ' timeline-clip-empty'}"><span>${clip ? clip.name : 'Source video'}</span></div>
            ${clip ? html`<input id="video-playhead" type="range" min="0" max=${duration} step="0.01"
              .value=${String(Math.min(this.currentTime, duration))} aria-label="Timeline playhead">` : ''}
          </div>
        </div>
        <header class="keyframes-head">
          <div><strong>Output keyframes</strong><span class="track-name">K1</span></div>
          <span>${this.frameLimit || 0} frames</span>
        </header>
        <div class="timeline-ruler keyframe-ruler" aria-hidden="true">
          <span>F000</span><span>F${String(Math.round(frameSpan / 4)).padStart(3, '0')}</span>
          <span>F${String(Math.round(frameSpan / 2)).padStart(3, '0')}</span>
          <span>F${String(Math.round(frameSpan * 3 / 4)).padStart(3, '0')}</span>
          <span>F${String(frameSpan).padStart(3, '0')}</span>
        </div>
        <div class="timeline-track keyframe-track" id="video-keyframe-track">
          <span class="track-name">K1</span>
          <div class="keyframe-rail">
            ${this.imageReferences.length ? this.imageReferences.map((reference) => {
              const frameIndex = Number.isFinite(reference.frameIndex) ? reference.frameIndex : 0;
              const position = Math.min(100, Math.max(0, frameIndex / frameSpan * 100));
              const selected = reference.id === this.selectedReferenceId;
              return html`<button class="keyframe-marker" type="button"
                style=${'left: ' + position + '%'} data-action="select-reference" data-reference-id=${reference.id}
                aria-label=${'Select ' + reference.name + ' at output frame ' + frameIndex}
                aria-pressed=${selected}>
                <img src=${reference.src} alt="">
                <span>F${String(frameIndex).padStart(3, '0')}</span>
              </button>`;
            }) : html`<span class="keyframe-empty">Share or add an image to place its keyframe.</span>`}
          </div>
        </div>
      </section>
    `;
  }

  renderSelectedClip() {
    const clip = this.selectedClip();
    const preview = this.querySelector('#video-preview-root');
    if (preview) renderTemplate(this.renderClip(clip), preview);
    this.renderTimelineView(clip);
    this.renderVideoGallery();
  }

  renderTimelineView(clip) {
    const timeline = this.querySelector('#video-timeline-root');
    if (timeline) renderTemplate(this.renderTimeline(clip), timeline);
    this.renderTimecode();
  }

  renderTimecode() {
    const value = this.querySelector('#video-timecode-value');
    if (!value) return;
    if (!this.selectedClip()) {
      value.textContent = '';
      return;
    }
    const duration = this.duration || (this.selectedClip() && this.selectedClip().duration) || 0;
    value.textContent = formatTime(this.currentTime) + ' / ' + formatTime(duration);
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
          ${outputs.length ? outputs.map((clip) => html`
            <div class="video-gallery-item">
              <button class="video-clip${clip.id === this.selectedClipId ? ' selected' : ''}"
                type="button" aria-label=${'Select video ' + clip.name} aria-pressed=${clip.id === this.selectedClipId}
                data-action="select-clip" data-clip-id=${clip.id}>
                <span class="video-clip-thumb"><span>VIDEO</span><span>${formatTime(clip.duration || duration)}</span></span>
                <span class="video-clip-name">${clip.name}</span>
              </button>
              <button class="video-clip-remove" type="button" aria-label=${'Remove video ' + clip.name}
                data-action="remove-clip" data-clip-id=${clip.id}>Remove</button>
            </div>`) : html`<span class="video-gallery-empty">Generated clips appear here.</span>`}
        </div>
      </section>`;
  }

  renderClip(clip) {
    if (!clip) {
      return html`<div class="video-empty">
        <div class="video-empty-mark">VIDEO</div>
        <strong>Build a video sequence</strong>
        <span>Add a source clip in the right panel to scrub frames and send a still to Image.</span>
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
        <header class="video-studio-head">
          <div><span class="eyebrow">VIDEO WORKSPACE</span><strong>Sequence</strong></div>
        </header>
        <div class="video-preview-area" id="video-preview-root"></div>
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
