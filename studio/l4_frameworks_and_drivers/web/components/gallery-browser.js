import {LitElement, html, svg, nothing} from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/+esm';
import {repeat} from 'https://cdn.jsdelivr.net/npm/lit@3.2.1/directives/repeat.js/+esm';
import './video-gallery-preview.js';
import {pencilLoop} from './gallery-marker.js';
import {galleryView, rememberGalleryView} from '../lib/gallery-view.js';

const icon = name => html`<svg class="icon" aria-hidden="true"><use href=${'#i-' + name}></use></svg>`;

// Each media owner supplies existing records and actions. This component owns browsing,
// never media storage, input selection, or generation state.
class GalleryBrowser extends LitElement {
  static properties = {
    workspace: {type: String}, items: {attribute: false}, selectedId: {attribute: false},
    choose: {attribute: false}, removeItem: {attribute: false}, download: {attribute: false},
    keeping: {type: Boolean}, pending: {type: Boolean}, pendingSelected: {type: Boolean},
    showPending: {attribute: false}, playback: {attribute: false},
    expanded: {type: Boolean, reflect: true}, query: {state: true}, order: {state: true},
    mode: {state: true}, model: {state: true}, grouped: {state: true}, group: {state: true},
    selecting: {state: true}, checked: {state: true}, working: {state: true}, error: {state: true},
  };
  constructor() {
    super();
    this.items = []; this.keeping = true; this.expanded = false;
    this.query = ''; this.order = 'newest'; this.mode = ''; this.model = '';
    this.grouped = false; this.group = ''; this.selecting = false;
    this.checked = new Set(); this.working = false; this.error = '';
    this.restored = false; this.gridScroll = 0;
    this.waitingImages = new WeakSet();
    this.stripScroll = event => {
      if (event.target.matches?.('.strip')) {
        if (this.restoreScroll || !this.gallery?.getClientRects().length) return;
        this.stripPosition = event.target.scrollLeft;
        this.remember({stripScroll: this.stripPosition});
      }
    };
  }
  createRenderRoot() { return this; }
  connectedCallback() {
    super.connectedCallback();
    this.gallery = this.closest('.strip-wrap');
    this.gallery?.addEventListener('scroll', this.stripScroll, true);
    this.visibility = new ResizeObserver(() => { if (this.restoreScroll) this.requestUpdate(); });
    if (this.gallery) this.visibility.observe(this.gallery);
  }
  disconnectedCallback() {
    this.gallery?.removeEventListener('scroll', this.stripScroll, true);
    this.visibility?.disconnect();
    super.disconnectedCallback();
  }
  remember(patch = {}) {
    rememberGalleryView(this.workspace, {expanded: this.expanded, query: this.query,
      order: this.order, mode: this.mode, model: this.model, grouped: this.grouped,
      group: this.group, gridScroll: this.gridScroll, ...patch}, this.keeping);
  }
  willUpdate(changes) {
    if (!this.restored && this.workspace) {
      const saved = this.keeping ? galleryView(this.workspace) : {};
      this.expanded = saved.expanded === true;
      this.query = typeof saved.query === 'string' ? saved.query : '';
      this.order = saved.order === 'oldest' ? 'oldest' : 'newest';
      this.mode = saved.mode || ''; this.model = saved.model || '';
      this.grouped = saved.grouped === true; this.group = saved.group || '';
      this.gridScroll = Number(saved.gridScroll) || 0;
      this.stripPosition = Number(saved.stripScroll) || 0;
      this.restored = true;
      this.restoreScroll = true;
    }
    if (changes.has('keeping') && !this.keeping) this.remember();
    if (changes.has('items')) {
      const ids = new Set(this.items.map(item => item.id));
      this.checked = new Set([...this.checked].filter(id => ids.has(id)));
      // Deleted or stale filter values should not strand the gallery on an empty category.
      if (this.items.length && this.mode && !this.items.some(item => item.mode === this.mode)) this.mode = '';
      if (this.items.length && this.model && !this.items.some(item => item.model === this.model)) this.model = '';
      if (this.items.length && this.group && !this.items.some(item => item.batch === this.group)) this.group = '';
    }
  }
  updated() {
    if (!this.restoreScroll) return;
    if (!this.items.length) return;
    if (this.gallery && !this.gallery.getClientRects().length) return;
    const strip = this.gallery?.querySelector('.strip');
    if (strip && !this.expanded) {
      const loading = Array.from(strip.querySelectorAll('img')).filter(image => !image.complete);
      for (const image of loading) {
        if (this.waitingImages.has(image)) continue;
        this.waitingImages.add(image);
        image.addEventListener('load', () => this.requestUpdate(), {once: true});
        image.addEventListener('error', () => this.requestUpdate(), {once: true});
      }
      if (loading.length) return;
    }
    this.restoreScroll = false;
    if (strip && !this.expanded) strip.scrollLeft = this.stripPosition;
    const grid = this.querySelector('.gallery-browser-grid');
    if (grid) grid.scrollTop = this.gridScroll;
    if (this.revealSelected) {
      this.revealSelected = false;
      strip?.querySelector('.selected')?.scrollIntoView({block: 'nearest', inline: 'nearest'});
    }
  }
  toggle() {
    if (this.working) return;
    this.expanded = !this.expanded;
    if (!this.expanded) { this.selecting = false; this.checked = new Set(); this.revealSelected = true; }
    this.remember();
    this.restoreScroll = true;
  }
  filtered() {
    const query = this.query.trim().toLocaleLowerCase();
    return this.items.filter(item => (!this.mode || item.mode === this.mode)
      && (!this.model || item.model === this.model) && (!this.group || item.batch === this.group)
      && (!query || [item.text, item.description, item.model, item.mode, item.seed, item.name]
        .join(' ').toLocaleLowerCase().includes(query)))
      .map((item, index) => ({item, index})).sort((a, b) => {
        const delta = (Number(b.item.at) || 0) - (Number(a.item.at) || 0);
        return (this.order === 'oldest' ? -delta : delta) || a.index - b.index;
      }).map(row => row.item);
  }
  rows(items) {
    if (!this.grouped || this.group) return items.map(item => ({item}));
    const batches = new Map();
    items.forEach(item => { if (item.batch) batches.set(item.batch, [...(batches.get(item.batch) || []), item]); });
    const seen = new Set();
    return items.flatMap(item => {
      const batch = batches.get(item.batch);
      if (!batch || batch.length < 2) return [{item}];
      if (seen.has(item.batch)) return [];
      seen.add(item.batch);
      return [{item, batch}];
    });
  }
  change(field, value) {
    this[field] = value;
    if (field !== 'group') this.group = '';
    this.gridScroll = 0;
    this.restoreScroll = true;
    this.checked = new Set();
    this.remember();
  }
  check(id) {
    this.checked = new Set(this.checked);
    if (this.checked.has(id)) this.checked.delete(id); else this.checked.add(id);
  }
  pick(item) {
    if (this.working) return;
    if (this.selecting) this.check(item.id);
    else this.choose?.(item.id);
  }
  async act(action) {
    const selected = this.items.filter(item => this.checked.has(item.id));
    if (!selected.length || this.working) return;
    if (action === 'remove' && !confirm('Remove ' + selected.length + ' selected '
      + this.workspace + ' results from ' + (this.keeping ? 'this browser? Other tabs update too.' : 'this tab?'))) return;
    this.working = true; this.error = '';
    try {
      if (action === 'download') await this.download?.(selected.filter(item => item.downloadable !== false).map(item => item.id));
      else {
        let failed = 0;
        for (const item of selected) if (await this.removeItem?.(item.id) === false) failed++;
        this.checked = new Set();
        if (failed) this.error = failed + ' results could not be removed. Try again.';
      }
    } catch (error) { this.error = error.message || 'The gallery action failed. Try again.'; }
    finally { this.working = false; }
  }
  key(event) {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === 'Escape' && this.expanded) {
      event.preventDefault(); event.stopPropagation();
      if (this.selecting) { this.selecting = false; this.checked = new Set(); }
      else { this.toggle(); this.querySelector('.gallery-browse-toggle')?.focus(); }
      return;
    }
    if (event.target.closest('input, select, textarea, [contenteditable]')) return;
    const buttons = Array.from(this.querySelectorAll('.gallery-card-pick'));
    const current = buttons.indexOf(event.target.closest('.gallery-card-pick'));
    if (current < 0) return;
    if (event.key === ' ' && buttons[current].dataset.itemId && !this.selecting && this.workspace !== 'image' && this.playback) {
      event.preventDefault(); event.stopPropagation();
      const item = this.items.find(item => String(item.id) === buttons[current].dataset.itemId);
      if (item && String(item.id) !== String(this.selectedId)) {
        Promise.resolve(this.choose?.(item.id)).then(() => this.playback());
      } else this.playback();
      return;
    }
    const first = buttons[0].getBoundingClientRect();
    const columns = buttons.filter(button => Math.abs(button.getBoundingClientRect().top - first.top) < 3).length || 1;
    const moves = {ArrowRight: current + 1, ArrowLeft: current - 1, ArrowDown: current + columns,
      ArrowUp: current - columns, Home: 0, End: buttons.length - 1};
    if (!(event.key in moves)) return;
    event.preventDefault(); event.stopPropagation();
    const next = buttons[Math.max(0, Math.min(buttons.length - 1, moves[event.key]))];
    next.focus(); next.scrollIntoView({block: 'nearest', inline: 'nearest'});
    if (!this.selecting && next.dataset.itemId) {
      const item = this.items.find(item => String(item.id) === next.dataset.itemId);
      if (item) this.choose?.(item.id);
    }
  }
  thumbnail(item) {
    if (this.workspace === 'video' && item.video) return html`<video-gallery-preview .source=${item.video}
      .poster=${item.thumbnail} .blocked=${this.pending}></video-gallery-preview>`;
    if (item.thumbnail) return html`<img src=${item.thumbnail} alt="" loading="lazy" decoding="async">`;
    const maximum = Math.max(0.001, ...(item.peaks || []));
    if (item.peaks?.length) return svg`<svg class="gallery-wave" viewBox="0 0 160 60" preserveAspectRatio="none" aria-hidden="true">
      ${item.peaks.map((peak, index) => svg`<line x1=${(index + 0.5) * 160 / item.peaks.length}
        x2=${(index + 0.5) * 160 / item.peaks.length} y1=${30 - Math.max(1, peak / maximum * 25)} y2=${30 + Math.max(1, peak / maximum * 25)} />`)}</svg>`;
    return html`<span class="gallery-no-preview">${this.workspace === 'voice' ? 'Audio' : 'No preview'}</span>`;
  }
  card(row) {
    const item = row.item;
    const selected = String(this.selectedId) === String(item.id) && !this.pendingSelected;
    return html`<article class="gallery-card${this.checked.has(item.id) ? ' checked' : ''}">
      <button type="button" class=${'frame gallery-card-pick' + (selected && !row.batch ? ' selected' : '')}
        data-item-id=${row.batch ? nothing : item.id} ?disabled=${this.working}
        aria-label=${row.batch ? 'Open batch of ' + row.batch.length + ' results' : 'View ' + this.workspace + ' ' + item.number}
        aria-pressed=${row.batch ? nothing : String(selected)}
        @click=${() => row.batch ? this.change('group', item.batch) : this.pick(item)}>
        <span class="still">${this.thumbnail(item)}
          ${item.duration ? html`<span class="gallery-duration">${item.duration.toFixed(1)} s</span>` : nothing}
          ${row.batch ? html`<span class="gallery-batch-count">${row.batch.length} results</span>` : nothing}
        </span>
        <span class="no">${row.batch ? 'Batch' : String(item.number).padStart(2, '0')}</span>
        ${selected && !row.batch ? pencilLoop(false) : nothing}
      </button>
      ${this.selecting && !row.batch ? html`<label class="gallery-check" title="Select result">
        <input type="checkbox" aria-label=${'Select ' + this.workspace + ' ' + item.number}
          .checked=${this.checked.has(item.id)} ?disabled=${this.working} @change=${() => this.check(item.id)}></label>` : nothing}
      <p class="gallery-card-text" title=${item.text || item.name || ''}>${item.text || item.name || 'Untitled'}</p>
      <p class="gallery-card-facts">${item.model || this.workspace}${item.mode ? ' · ' + item.mode : ''}</p>
    </article>`;
  }
  render() {
    const items = this.filtered();
    const models = [...new Set(this.items.map(item => item.model).filter(Boolean))].sort();
    const modes = [...new Set(this.items.map(item => item.mode).filter(Boolean))].sort();
    const checked = this.items.filter(item => this.checked.has(item.id));
    const batches = this.items.map(item => item.batch).filter(Boolean);
    const hasBatch = new Set(batches).size < batches.length;
    return html`<button type="button" class="text-btn gallery-browse-toggle" aria-expanded=${String(this.expanded)}
      aria-controls=${this.workspace + '-gallery-browser-panel'} ?disabled=${this.working}
      @keydown=${event => this.key(event)}
      @click=${() => this.toggle()}>${icon(this.expanded ? 'shrink' : 'layout')}${this.expanded ? 'Compact' : 'Browse'}</button>
      ${this.expanded ? html`<section class="gallery-browser-panel" id=${this.workspace + '-gallery-browser-panel'}
        aria-label=${this.workspace + ' gallery browser'} @keydown=${event => this.key(event)}>
        <div class="gallery-browser-tools">
          <input type="search" aria-label="Search gallery" placeholder="Search prompts, scripts, models or seeds"
            .value=${this.query} @input=${event => this.change('query', event.target.value)}>
          <select aria-label="Gallery order" @change=${event => this.change('order', event.target.value)}>
            <option value="newest" .selected=${this.order === 'newest'}>Newest first</option>
            <option value="oldest" .selected=${this.order === 'oldest'}>Oldest first</option></select>
          ${modes.length > 1 ? html`<select aria-label="Filter by mode"
            @change=${event => this.change('mode', event.target.value)}><option value="" .selected=${!this.mode}>All modes</option>
            ${modes.map(mode => html`<option value=${mode} .selected=${this.mode === mode}>${mode}</option>`)}</select>` : nothing}
          ${models.length > 1 ? html`<select aria-label="Filter by model"
            @change=${event => this.change('model', event.target.value)}><option value="" .selected=${!this.model}>All models</option>
            ${models.map(model => html`<option value=${model} .selected=${this.model === model}>${model}</option>`)}</select>` : nothing}
          ${hasBatch ? html`<label class="gallery-group-toggle"><input type="checkbox" .checked=${this.grouped}
            @change=${event => this.change('grouped', event.target.checked)}>Group batches</label>` : nothing}
          <button type="button" class="text-btn" aria-pressed=${String(this.selecting)} ?disabled=${this.working}
            @click=${() => { this.selecting = !this.selecting; this.checked = new Set(); }}>${icon('check')}${this.selecting ? 'Done' : 'Select'}</button>
        </div>
        <div class="gallery-browser-summary">
          ${this.group ? html`<button type="button" class="text-btn" @click=${() => this.change('group', '')}>${icon('undo')}All results</button>` : nothing}
          <span role="status" aria-live="polite">${items.length} of ${this.items.length} results${checked.length ? ' · ' + checked.length + ' selected' : ''}</span>
          ${this.selecting ? html`<button type="button" class="text-btn" ?disabled=${this.working || !items.length}
            @click=${() => { this.checked = new Set(items.map(item => item.id)); }}>Select all ${items.length}</button>
            <button type="button" class="text-btn" ?disabled=${this.working || !checked.length}
              @click=${() => { this.checked = new Set(); }}>Deselect</button>
            <button type="button" class="text-btn" ?disabled=${this.working || !checked.some(item => item.downloadable !== false)}
              @click=${() => this.act('download')}>${icon('download')}Download selected</button>
            <button type="button" class="text-btn gallery-remove" ?disabled=${this.working || !checked.length}
              @click=${() => this.act('remove')}>${icon('trash')}Remove selected</button>` : nothing}
        </div>
        ${this.error ? html`<p class="gallery-browser-error" role="alert">${this.error}</p>` : nothing}
        <div class="gallery-browser-grid" role="group" aria-label="Gallery results" @scroll=${event => {
          this.gridScroll = event.target.scrollTop; this.remember();
        }}>
          ${this.pending ? html`<button type="button" class=${'frame gallery-card-pick gallery-pending' + (this.pendingSelected ? ' selected' : '')}
            aria-pressed=${String(Boolean(this.pendingSelected))}
            aria-label="Show generation in progress" @click=${() => this.showPending?.()}>
            <span class="still"><span class="video-pending-indicator"></span><span>Generating</span></span>
            ${this.pendingSelected ? pencilLoop(false) : nothing}
          </button>` : nothing}
          ${repeat(this.rows(items), row => row.batch ? 'batch-' + row.item.batch : row.item.id, row => this.card(row))}
          ${!items.length ? html`<div class="gallery-no-results"><strong>${this.items.length ? 'No matching results' : 'No completed results yet'}</strong>
            ${this.items.length ? html`<button type="button" class="text-btn" @click=${() => {
              this.query = ''; this.mode = ''; this.model = ''; this.change('group', '');
            }}>Clear filters</button>` : nothing}</div>` : nothing}
        </div>
      </section>` : nothing}`;
  }
}
customElements.define('gallery-browser', GalleryBrowser);
