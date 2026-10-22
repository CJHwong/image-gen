import {LitElement, html, nothing} from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';

// Existing gallery videos are local blobs. Build one tiny contact sheet at a time,
// then animate that image; never leave a decoder running for each gallery card.
const frames = 16, width = 128, height = 72;
const cache = new Map();
let queue = Promise.resolve();
function waitFor(video, event, start) {
  return new Promise((resolve, reject) => {
    const finish = error => {
      clearTimeout(timeout); video.removeEventListener(event, ready); video.removeEventListener('error', failed);
      error ? reject(error) : resolve();
    };
    const ready = () => finish(), failed = () => finish(new Error('Preview unavailable'));
    const timeout = setTimeout(failed, 10000);
    video.addEventListener(event, ready, {once: true}); video.addEventListener('error', failed, {once: true});
    start();
  });
}
async function contactSheet(source, active) {
  if (!active()) return null;
  if (cache.has(source)) {
    const saved = cache.get(source); cache.delete(source); cache.set(source, saved); return saved;
  }
  const video = document.createElement('video');
  video.muted = true; video.playsInline = true; video.preload = 'metadata';
  try {
    await waitFor(video, 'loadeddata', () => { video.src = source; video.load(); });
    if (!video.videoWidth || !Number.isFinite(video.duration) || video.duration <= 0) return null;
    const seconds = Math.min(2, video.duration);
    const canvas = document.createElement('canvas'); canvas.width = width * frames; canvas.height = height;
    const context = canvas.getContext('2d');
    const scale = Math.min(width / video.videoWidth, height / video.videoHeight);
    const w = video.videoWidth * scale, h = video.videoHeight * scale;
    context.fillStyle = '#181818'; context.fillRect(0, 0, canvas.width, height);
    for (let index = 0; index < frames; index++) {
      if (!active()) return null;
      // A tiny initial seek also uploads frame zero on hardware decoders that
      // report loadeddata before its first texture is available to canvas.
      await waitFor(video, 'seeked', () => { video.currentTime = index ? seconds * index / frames : Math.min(0.001, seconds / 16); });
      if (!active()) return null;
      context.drawImage(video, index * width + (width - w) / 2, (height - h) / 2, w, h);
    }
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/webp', 0.55));
    if (!blob || !active()) return null;
    const result = {blob, seconds};
    cache.set(source, result);
    if (cache.size > 32) cache.delete(cache.keys().next().value);
    return result;
  } finally {
    video.removeAttribute('src'); video.load();
  }
}

class VideoGalleryPreview extends LitElement {
  static properties = {source: {}, poster: {}, blocked: {type: Boolean}, sheet: {state: true}, seconds: {state: true}};
  constructor() { super(); this.visible = false; this.sheet = ''; this.ticket = 0; }
  createRenderRoot() { return this; }
  connectedCallback() {
    super.connectedCallback();
    this.motion = matchMedia('(prefers-reduced-motion: reduce)');
    this.onVisibility = () => this.refresh();
    document.addEventListener('visibilitychange', this.onVisibility);
    this.motion.addEventListener('change', this.onVisibility);
    this.observer = new IntersectionObserver(entries => {
      this.visible = entries[0].isIntersecting; this.refresh();
    }, {threshold: 0.05});
    this.observer.observe(this);
  }
  disconnectedCallback() {
    this.observer?.disconnect(); document.removeEventListener('visibilitychange', this.onVisibility);
    this.motion?.removeEventListener('change', this.onVisibility); this.clear();
    super.disconnectedCallback();
  }
  updated(changes) {
    if (changes.has('source')) { this.clear(); this.failed = ''; }
    if (changes.has('source') || changes.has('blocked')) this.refresh();
  }
  active() {
    return this.isConnected && this.visible && !document.hidden && !this.blocked && !this.motion?.matches
      && this.source?.startsWith('blob:');
  }
  clear() {
    this.ticket++;
    if (this.sheet) URL.revokeObjectURL(this.sheet);
    this.sheet = '';
  }
  refresh() {
    if (!this.active()) { this.clear(); return; }
    if (this.sheet || this.queued || this.failed === this.source) return;
    const source = this.source, ticket = ++this.ticket;
    this.queued = true;
    const active = () => this.active() && this.source === source && this.ticket === ticket;
    const task = queue.then(() => contactSheet(source, active));
    queue = task.catch(() => {});
    task.then(result => {
      if (result && active()) { this.seconds = result.seconds; this.sheet = URL.createObjectURL(result.blob); }
    }).catch(() => { if (active()) this.failed = source; }).finally(() => {
      this.queued = false;
      if (ticket !== this.ticket && this.active()) this.refresh();
    });
  }
  render() {
    return this.sheet ? html`<svg class="video-gallery-sheet" viewBox="0 0 128 72" aria-hidden="true"
      style=${`--loop-duration:${this.seconds}s`}><image href=${this.sheet} width="2048" height="72" /></svg>`
      : this.poster ? html`<img src=${this.poster} alt="" loading="lazy" decoding="async">` : nothing;
  }
}
customElements.define('video-gallery-preview', VideoGalleryPreview);
