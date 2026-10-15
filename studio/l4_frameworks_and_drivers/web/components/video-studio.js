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

class VideoStudio extends LitElement {
  clips = [];
  imageReferences = [];
  selectedReferenceId = null;
  selectedClipId = null;
  currentTime = 0;
  duration = 0;
  frameLimit = 145;
  error = '';

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    this.addEventListener('click', this.onComponentClick);
    this.addEventListener('change', this.onComponentChange);
    this.addEventListener('input', this.onComponentInput);
    this.addEventListener('loadedmetadata', this.onMetadata, true);
    this.addEventListener('timeupdate', this.onTimeUpdate, true);
  }

  disconnectedCallback() {
    this.removeEventListener('click', this.onComponentClick);
    this.removeEventListener('change', this.onComponentChange);
    this.removeEventListener('input', this.onComponentInput);
    this.removeEventListener('loadedmetadata', this.onMetadata, true);
    this.removeEventListener('timeupdate', this.onTimeUpdate, true);
    super.disconnectedCallback();
    this.clips.forEach(function (clip) {
      if (clip.objectUrl) URL.revokeObjectURL(clip.url);
    });
  }

  firstUpdated() {
    this.renderImageReferences();
    this.renderSelectedClip();
    this.renderError();
  }

  addImageReference(reference) {
    if (this.imageReferences.some(function (saved) { return saved.id === reference.id; })) return;
    this.imageReferences = this.imageReferences.concat({
      id: reference.id,
      name: reference.name,
      src: reference.src,
      base64: reference.base64,
      frameIndex: Number.isInteger(reference.frameIndex) ? reference.frameIndex : 0,
      strength: Number.isFinite(reference.strength) ? reference.strength : 1,
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
    this.querySelectorAll('[data-action="reference-frame"]').forEach((control) => {
      control.max = String(frameCount - 1);
    });
    this.renderTimelineView(this.selectedClip());
  }

  setReferenceStrength(id, control) {
    const reference = this.imageReferences.find((item) => item.id === id);
    if (!reference) return;
    reference.strength = Number(control.value);
    control.nextElementSibling.textContent = reference.strength.toFixed(2);
  }

  renderImageReferences() {
    const list = this.querySelector('#video-references');
    const count = this.querySelector('#video-reference-count');
    if (!list || !count) return;
    count.textContent = this.imageReferences.length + ' shared';
    list.replaceChildren();
    if (!this.imageReferences.length) {
      const empty = document.createElement('span');
      empty.className = 'video-ref-empty';
      empty.textContent = 'Share an image result or add a still.';
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
      frameIndex.max = String(this.frameLimit - 1);
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
      strength.min = '0.05';
      strength.max = '1';
      strength.step = '0.05';
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

  requestPayload(settings) {
    return {
      prompt: settings.prompt,
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
      name: 'LTX-2.5 ' + Math.round(settings.duration) + 's',
      url: URL.createObjectURL(blob),
      objectUrl: true,
      duration: duration,
    });
  }

  addStubClip(result) {
    const duration = result.num_frames / result.frame_rate;
    this.addClip({
      id: 'clip-' + nextClipId++,
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
    this.renderSelectedClip();
  }

  onComponentClick(event) {
    if (!(event.target instanceof Element)) return;
    const control = event.target.closest('[data-action]');
    if (!control) return;
    const action = control.dataset.action;
    if (action === 'add-video') this.querySelector('#video-upload').click();
    if (action === 'add-image') this.querySelector('#video-image-upload').click();
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
    let addedClip = false;
    Array.from(input.files || []).forEach((file) => {
      if (!file.type.startsWith('video/')) {
        this.setError('Choose a video file.');
        return;
      }
      const clip = {
        id: 'clip-' + nextClipId++,
        name: file.name,
        url: URL.createObjectURL(file),
        objectUrl: true,
        duration: 0,
      };
      this.clips = this.clips.concat(clip);
      if (!this.selectedClipId) this.selectedClipId = clip.id;
      addedClip = true;
    });
    input.value = '';
    if (addedClip) this.renderSelectedClip();
    this.renderVideoGallery();
  }

  async onImageFiles(event) {
    const input = event.target;
    const files = Array.from(input.files || []);
    input.value = '';
    for (const file of files) {
      if (!file.type.startsWith('image/')) {
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
    const frameSpan = Math.max(1, this.frameLimit - 1);
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
          </div>` : html`<p class="source-empty">Import a clip to scrub it and capture a frame.</p>`}
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
          <span>${this.frameLimit} frames</span>
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
    renderTemplate(html`${formatTime(this.currentTime)} / ${formatTime(duration)}`, value);
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
    const duration = this.duration || (this.selectedClip() && this.selectedClip().duration) || 0;
    return html`
      <section class="video-gallery" id="video-gallery" aria-label="Video gallery">
        <div class="video-gallery-head"><strong>Video gallery</strong><span>${this.clips.length} clips</span></div>
        <div class="video-clips">
          ${this.clips.map((clip) => html`
            <div class="video-gallery-item">
              <button class="video-clip${clip.id === this.selectedClipId ? ' selected' : ''}"
                type="button" aria-label=${'Select video ' + clip.name} aria-pressed=${clip.id === this.selectedClipId}
                data-action="select-clip" data-clip-id=${clip.id}>
                <span class="video-clip-thumb"><span>VIDEO</span><span>${formatTime(clip.duration || duration)}</span></span>
                <span class="video-clip-name">${clip.name}</span>
              </button>
              <button class="video-clip-remove" type="button" aria-label=${'Remove video ' + clip.name}
                data-action="remove-clip" data-clip-id=${clip.id}>Remove</button>
            </div>`)}
        </div>
      </section>`;
  }

  renderClip(clip) {
    if (!clip) {
      return html`<div class="video-empty">
        <div class="video-empty-mark">VIDEO</div>
        <strong>Build a video sequence</strong>
        <span>Import a clip to scrub its timeline and send a frame to Image.</span>
        <button class="btn" type="button" data-action="add-video">Add video</button>
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
          <button class="pill" type="button" data-action="add-video">Add clip</button>
        </header>
        <div class="video-preview-area" id="video-preview-root"></div>
        <div class="video-editing-area">
          <div id="video-timeline-root"></div>
          <section class="video-reference-tray" aria-label="Image references for video">
            <div class="video-reference-head">
              <div><strong>Image references</strong><span id="video-reference-count">0 shared</span></div>
              <button class="text-btn" type="button" data-action="add-image">Add image</button>
            </div>
            <div class="video-references" id="video-references"></div>
          </section>
          <div id="video-error-root"></div>
          <div id="video-gallery-root"></div>
        </div>
        <input id="video-upload" type="file" accept="video/*" multiple hidden>
        <input id="video-image-upload" type="file" accept="image/*" multiple hidden>
      </div>
    `;
  }
}

customElements.define('video-studio', VideoStudio);
