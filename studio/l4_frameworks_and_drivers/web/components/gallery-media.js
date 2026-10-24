import {LitElement, html, nothing} from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import './video-gallery-preview.js';
const thumbnails = new Map();
let queue = Promise.resolve();
async function smallImage(key, blob) {
  if (thumbnails.has(key)) { const saved = thumbnails.get(key); thumbnails.delete(key); thumbnails.set(key, saved); return saved; }
  const bitmap = await createImageBitmap(blob);
  try {
    const canvas = document.createElement('canvas');
    const scale = Math.min(1, 256 / Math.max(bitmap.width, bitmap.height));
    canvas.width = Math.max(1, Math.round(bitmap.width * scale)); canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const result = await new Promise(resolve => canvas.toBlob(resolve, 'image/webp', 0.75));
    if (result) { thumbnails.set(key, result); if (thumbnails.size > 64) thumbnails.delete(thumbnails.keys().next().value); }
    return result;
  } finally { bitmap.close(); }
}
class GalleryMedia extends LitElement {
  static properties = {identity: {}, load: {attribute: false}, video: {type: Boolean}, blocked: {type: Boolean}, url: {state: true}, poster: {state: true}};
  createRenderRoot() { return this; }
  connectedCallback() {
    super.connectedCallback(); this.revision = 0;
    this.observer = new IntersectionObserver(entries => {
      this.visible = entries[0].isIntersecting;
      if (this.visible) this.read(); else this.clear();
    }, {rootMargin: '100px'});
    this.observer.observe(this);
  }
  disconnectedCallback() { this.observer?.disconnect(); this.clear(); super.disconnectedCallback(); }
  updated(changes) { if (changes.has('identity')) { this.clear(); if (this.visible) this.read(); } }
  clear() {
    this.revision++; this.loading = false;
    if (this.url) URL.revokeObjectURL(this.url);
    if (this.poster) URL.revokeObjectURL(this.poster);
    this.url = ''; this.poster = '';
  }
  read() {
    if (this.loading || this.url || !this.load) return;
    this.loading = true;
    const revision = this.revision, key = this.identity;
    const active = () => this.isConnected && this.visible && this.revision === revision;
    const task = queue.then(async () => {
      if (!active()) return;
      const saved = !this.video && thumbnails.get(key);
      const data = saved ? {blob: saved} : await this.load();
      if (!active() || !data?.blob) return;
      const blob = this.video || saved ? data.blob : await smallImage(key, data.blob);
      if (!active() || !blob) return;
      this.url = URL.createObjectURL(blob);
      if (this.video && data.poster) this.poster = URL.createObjectURL(data.poster);
    });
    queue = task.catch(() => {});
    task.catch(() => {}).finally(() => { if (active()) this.loading = false; });
  }
  render() {
    if (!this.url) return nothing;
    return this.video ? html`<video-gallery-preview .source=${this.url} .cacheKey=${this.identity}
      .poster=${this.poster} .blocked=${this.blocked}></video-gallery-preview>`
      : html`<img src=${this.url} alt="" decoding="async">`;
  }
}
customElements.define('gallery-media', GalleryMedia);
