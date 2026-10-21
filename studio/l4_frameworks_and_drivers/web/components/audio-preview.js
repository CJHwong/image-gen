import {LitElement, html, svg} from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import {audioPeaks, blobBase64, decodeAudio, downloadAudio, waveBytes} from '../lib/voice-audio.js';

import {mediaDownloadName, mediaExtension} from '../lib/download-name.js';

const MINIMUM_SECONDS = 0.2;

class AudioPreview extends LitElement {
  static properties = {
    downloadText: {attribute: false}, downloadAt: {attribute: false}, downloadId: {attribute: false},
    blob: {attribute: false}, label: {type: String}, locked: {type: Boolean},
    speed: {state: true}, duration: {state: true}, start: {state: true}, end: {state: true}, position: {state: true},
    loading: {state: true}, busy: {state: true}, playing: {state: true},
    error: {state: true}, peaks: {state: true},
  };

  constructor() {
    super();
    this.label = 'Audio preview';
    this.speed = 1;
    this.locked = false;
    this.duration = 0;
    this.start = 0;
    this.end = 0;
    this.position = 0;
    this.peaks = [];
    this.loading = false;
    this.busy = false;
    this.playing = false;
    this.error = '';
    this._revision = 0;
    this._actionRevision = 0;
    this._playRequest = 0;
    this._decodes = new WeakMap();
  }

  createRenderRoot() { return this; }

  updated(changes) {
    if (changes.has('blob')) this._loading = this._load();
    if (['blob', 'loading', 'busy', 'playing', 'duration', 'error', 'speed'].some(name => changes.has(name))) this._publishState();
  }

  get ready() {
    return Boolean(this._decoded) && this._source === this.blob && !this.loading;
  }

  _publishState() {
    const state = {blob: this.blob, ready: this.ready, busy: Boolean(this.busy), playing: Boolean(this.playing), speed: this.speed};
    if (this._lastState && Object.keys(state).every(name => this._lastState[name] === state[name])) return;
    this._lastState = state;
    this.dispatchEvent(new CustomEvent('audio-preview-state', {bubbles: true, composed: true, detail: state}));
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this._revision++;
    this._request?.abort();
    this.pause();
  }

  connectedCallback() {
    super.connectedCallback();
    if (this.hasUpdated && this.blob) this._loading = this._load();
  }

  async _load() {
    const revision = ++this._revision;
    this._source = this.blob;
    this._actionRevision++;
    this._request?.abort();
    // Keep a play request that waits for this source to decode.
    this._stopPlayback();
    this._decoded = null;
    this._encoded = null;
    this._trimmed = null;
    this.duration = this.start = this.end = this.position = 0;
    this.peaks = [];
    this.error = '';
    this.busy = false;
    this.loading = Boolean(this.blob);
    if (!this.blob) return;
    try {
      if (!this._decodes.has(this.blob)) this._decodes.set(this.blob, decodeAudio(this.blob, null));
      const decoded = await this._decodes.get(this.blob);
      if (revision !== this._revision) return;
      const duration = decoded.sourceDuration || decoded.duration;
      if (!Number.isFinite(duration) || duration < MINIMUM_SECONDS) {
        throw new Error('The audio must contain at least 0.2 seconds.');
      }
      this._decoded = decoded;
      this.duration = duration;
      this.end = this.duration;
      this.peaks = audioPeaks(decoded.samples, 160);
    } catch (error) {
      if (revision === this._revision) this.error = error.message || 'The audio could not be decoded.';
    } finally {
      if (revision === this._revision) this.loading = false;
    }
  }

  async play() {
    const request = ++this._playRequest;
    const blob = this.blob;
    await this.updateComplete;
    const revision = this._revision;
    await this._loading;
    if (request !== this._playRequest || blob !== this.blob || revision !== this._revision || !this.isConnected) return;
    return this._play();
  }

  pause() {
    this._playRequest++;
    this._stopPlayback();
  }

  _stopPlayback() {
    cancelAnimationFrame(this._frame);
    this._frame = null;
    if (this._player) {
      this._readPosition(this._player);
      this._player.pause();
      this._player.removeAttribute('src');
      this._player.load();
      this._player = null;
    }
    if (this._playUrl) URL.revokeObjectURL(this._playUrl);
    this._playUrl = null;
    this.playing = false;
  }

  _setBoundary(boundary, rawValue) {
    const value = Number(rawValue);
    if (!Number.isFinite(value) || !this._decoded || this._source !== this.blob) return;
    this._actionRevision++;
    this.pause();
    this._request?.abort();
    this.busy = false;
    this.error = '';
    this._trimmed = null;
    if (boundary === 'start') this.start = Math.max(0, Math.min(value, this.end - MINIMUM_SECONDS));
    else this.end = Math.min(this.duration, Math.max(value, this.start + MINIMUM_SECONDS));
    this.position = Math.max(this.start, Math.min(this.end, this.position));
  }

  _input(boundary, event) {
    this._setBoundary(boundary, event.target.value);
    event.target.value = this[boundary].toFixed(2);
  }

  _setPosition(rawValue) {
    const value = Number(rawValue);
    if (!Number.isFinite(value) || !this._decoded || this._source !== this.blob) return;
    const lower = this.playing ? this.start : 0;
    const upper = this.playing ? this.end : this.duration;
    this.position = Math.max(lower, Math.min(upper, value));
    if (!this._player) return;
    try {
      this._player.currentTime = this.position - this._playStart;
    } catch (error) {
      this.pause();
      this.error = error.message || 'The selected audio could not seek to this position.';
    }
  }

  _setSpeed(event) {
    const speed = Number(event.target.value);
    if (![0.5, 0.75, 1, 1.25, 1.5, 2].includes(speed)) return;
    this.speed = speed;
    if (this._player) this._player.playbackRate = speed;
  }

  _positionInput(event) {
    this._setPosition(event.target.value);
    event.target.value = String(this.position);
  }

  _pointer(event) {
    if (!this._decoded || event.target.closest('input')) return;
    const track = event.currentTarget;
    const bounds = track.getBoundingClientRect();
    if (!bounds.width) return;
    const seconds = Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)) * this.duration;
    if (event.type === 'pointerdown') track.setPointerCapture(event.pointerId);
    this._setPosition(seconds);
  }

  _readPosition(player) {
    if (player.readyState >= 1 && Number.isFinite(player.currentTime)) {
      this.position = Math.max(this.start, Math.min(this.end, this._playStart + player.currentTime));
    }
  }

  _trackPosition(player) {
    if (this._player !== player) return;
    this._readPosition(player);
    this._frame = requestAnimationFrame(() => this._trackPosition(player));
  }

  async _play() {
    if (this.playing) { this.pause(); return; }
    if (!this._decoded || this._source !== this.blob) return;
    const position = this.position >= this.start && this.position < this.end ? this.position : this.start;
    const revision = this._revision;
    const source = this.blob;
    this.error = '';
    this.dispatchEvent(new CustomEvent('audio-preview-play', {bubbles: true, composed: true}));
    if (revision !== this._revision || source !== this.blob || !this.isConnected) return;
    this.position = position;
    const {samples, sampleRate} = this._decoded;
    const clipped = waveBytes(samples.slice(Math.round(this.start * sampleRate), Math.round(this.end * sampleRate)), sampleRate);
    this._playUrl = URL.createObjectURL(clipped);
    const player = new Audio(this._playUrl);
    player.playbackRate = this.speed;
    this._player = player;
    this._playStart = this.start;
    player.onloadedmetadata = () => {
      if (this._player === player) player.currentTime = this.position - this._playStart;
    };
    player.onended = () => {
      if (this._player !== player) return;
      this.pause();
      this.position = this.start;
    };
    player.onerror = () => {
      if (this._player !== player) return;
      this.pause();
      this.error = 'The selected audio could not be played.';
    };
    try {
      this.playing = true;
      await player.play();
      if (this._player === player) this._trackPosition(player);
    } catch (error) {
      if (this._player !== player) return;
      this.pause();
      this.error = error.message || 'The selected audio could not be played.';
    }
  }

  async _crop() {
    const key = `${this._revision}:${this.start}:${this.end}`;
    if (this._trimmed?.key === key) return this._trimmed.blob;
    const request = new AbortController();
    this._request = request;
    if (!this._encoded) {
      const {samples, sampleRate} = this._decoded;
      const original = this.blob.type.includes('wav') ? this.blob : waveBytes(samples, sampleRate);
      this._encoded = blobBase64(original);
    }
    const encoded = await this._encoded;
    if (request.signal.aborted) throw new DOMException('The selection changed.', 'AbortError');
    const response = await fetch('/api/v1/audio/trim', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, signal: request.signal,
      body: JSON.stringify({audio: {name: 'selection.wav', data: encoded}, start_seconds: this.start, end_seconds: this.end}),
    });
    if (!response.ok) {
      const failure = await response.json().catch(() => null);
      throw new Error((typeof failure?.error === 'string' ? failure.error : failure?.error?.message) || failure?.message || `The audio selection failed (${response.status}).`);
    }
    const blob = await response.blob();
    if (!blob.size || !blob.type.startsWith('audio/')) throw new Error('The server did not return an audio selection.');
    this._trimmed = {key, blob};
    return blob;
  }

  async action(action) {
    if (!['video', 'clone', 'edit', 'download'].includes(action)) {
      this.error = 'Choose Send to Video, Send to Clone, Edit or Download.';
      return;
    }
    const source = this.blob;
    await this.updateComplete;
    const revision = this._revision;
    await this._loading;
    if (source !== this.blob || revision !== this._revision || !this.isConnected) return;
    return this._action(action);
  }

  async _action(action) {
    if (!this._decoded || this._source !== this.blob || this.busy || (this.locked && action !== 'download')) return;
    this.error = '';
    this.busy = true;
    const revision = this._revision;
    const actionRevision = ++this._actionRevision;
    const source = this.blob;
    const start = this.start;
    const end = this.end;
    try {
      const originalDownload = action === 'download' && start === 0 && end === this.duration;
      const blob = originalDownload ? source : await this._crop();
      if (revision !== this._revision || actionRevision !== this._actionRevision || source !== this.blob || start !== this.start || end !== this.end || !this.isConnected) return;
      if (this.locked && action !== 'download') return;
      const name = originalDownload ? source.name || (source.type.includes('wav') ? 'audio.wav' : 'audio') : 'selection.wav';
      if (action === 'download') downloadAudio(blob, mediaDownloadName({kind: 'audio',
        text: this.downloadText, at: this.downloadAt, id: this.downloadId,
        extension: originalDownload ? mediaExtension(source.type, 'wav') : 'wav',
        ...(originalDownload ? {} : {start, end})}));
      else this.dispatchEvent(new CustomEvent('audio-preview-action', {
        bubbles: true, composed: true, detail: {action, blob, start, end, name, duration: this.duration},
      }));
    } catch (error) {
      if (revision === this._revision && actionRevision === this._actionRevision && error.name !== 'AbortError') this.error = error.message || 'The audio selection failed.';
    } finally {
      if (revision === this._revision && actionRevision === this._actionRevision) this.busy = false;
    }
  }

  render() {
    const ready = this.ready;
    const left = this.duration ? this.start / this.duration * 100 : 0;
    const right = this.duration ? this.end / this.duration * 100 : 100;
    const cursor = this.duration ? this.position / this.duration * 100 : 0;
    return html`<section class="audio-preview" aria-label=${this.label}>
      <div class="audio-preview-heading"><strong>${this.label}</strong>
        <span>${ready ? `${(this.end - this.start).toFixed(2)} s selected` : this.loading ? 'Loading audio…' : 'No audio selected'}</span></div>
      <div class="audio-preview-wave" style=${`--selection-start:${left}%;--selection-end:${right}%;--playback-position:${cursor}%`}
        @pointerdown=${this._pointer} @pointermove=${event => { if (event.currentTarget.hasPointerCapture(event.pointerId)) this._pointer(event); }}>
        <svg viewBox="0 0 640 80" preserveAspectRatio="none" aria-hidden="true">
          ${this.peaks.map((peak, index) => {
            const percent = (index + 0.5) / this.peaks.length * 100;
            return svg`<rect class=${'audio-preview-wave-bar' + (percent >= left && percent <= right ? ' audio-preview-wave-bar-selected' : '')}
              x=${index * 4 + 1} y=${40 - Math.max(1, peak * 36)} width="2" height=${Math.max(2, peak * 72)} rx="1" />`;
          })}
        </svg>
        <div class="audio-preview-selection"></div>
        <div class="audio-preview-playhead" aria-hidden="true"></div>
        <div class="audio-preview-ruler" aria-hidden="true" ?hidden=${!ready}>
          ${[0, 0.25, 0.5, 0.75, 1].map(fraction => html`<span>${(this.duration * fraction).toFixed(2)} s</span>`)}
        </div>
        <input class="audio-preview-range audio-preview-range-start" type="range" aria-label="Selection start handle"
          min="0" max=${this.duration} step="0.01" .value=${String(this.start)} ?disabled=${!ready}
          aria-valuetext=${`${this.start.toFixed(2)} seconds`} @input=${event => this._input('start', event)}>
        <input class="audio-preview-range audio-preview-range-end" type="range" aria-label="Selection end handle"
          min="0" max=${this.duration} step="0.01" .value=${String(this.end)} ?disabled=${!ready}
          aria-valuetext=${`${this.end.toFixed(2)} seconds`} @input=${event => this._input('end', event)}>
      </div>
      <div class="audio-preview-controls">
      <div class="audio-preview-player" role="group" aria-label="Audio playback" style=${`--player-progress:${cursor}%`}>
        <button type="button" class="icon-btn" aria-label=${this.playing ? 'Pause' : 'Play'} title=${this.playing ? 'Pause' : 'Play'}
          ?disabled=${!ready} @click=${this.play}>
          <svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path d=${this.playing ? 'M9 6v12M15 6v12' : 'M9 5l11 7-11 7z'}></path></svg>
        </button>
        <input type="range" aria-label="Playback position" min="0" max=${this.duration} step="0.01"
          .value=${String(this.position)} ?disabled=${!ready} aria-valuetext=${`${this.position.toFixed(2)} seconds`}
          @input=${this._positionInput}>
        <output class="audio-preview-position-value">${this.position.toFixed(2)} / ${this.duration.toFixed(2)} s</output>
        <span class=${'audio-preview-speed-control' + (this.speed === 1 ? '' : ' is-adjusted')}>
          <select class="audio-preview-speed" aria-label="Playback speed" title="Playback speed"
            .value=${String(this.speed)} @change=${this._setSpeed}>
            ${[0.5, 0.75, 1, 1.25, 1.5, 2].map(speed => html`<option value=${String(speed)} ?selected=${speed === this.speed}>${speed}×</option>`)}
          </select>
          <svg viewBox="0 0 12 12" aria-hidden="true"><path d="m3 4.5 3 3 3-3"></path></svg>
        </span>
      </div>
      <div class="audio-preview-times">
        <label>Start <input type="number" aria-label="Selection start" min="0" max=${Math.max(0, this.end - MINIMUM_SECONDS)} step="0.01"
          .value=${this.start.toFixed(2)} ?disabled=${!ready} @change=${event => this._input('start', event)}> s</label>
        <label>End <input type="number" aria-label="Selection end" min=${this.start + MINIMUM_SECONDS} max=${this.duration} step="0.01"
          .value=${this.end.toFixed(2)} ?disabled=${!ready} @change=${event => this._input('end', event)}> s</label>
      </div>
      </div>
      ${this.busy ? html`<p class="audio-preview-status" role="status">Preparing selection…</p>` : ''}
      ${this.error ? html`<p class="audio-preview-error" role="alert">${this.error}</p>` : ''}
    </section>`;
  }
}

customElements.define('audio-preview', AudioPreview);
