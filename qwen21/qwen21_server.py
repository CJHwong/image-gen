#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "mflux @ git+https://github.com/mflux-community/mflux@8c00dab2505a96019df9d30bc9c223bf20d733c4",
#     "pillow",
# ]
# ///
"""
A local web page for Qwen-Image-2.1, on top of the same mflux engine as qwen21_gen.py.

This exists for the form and for the privacy, NOT for speed. mflux memory-maps the
weights, so a fresh CLI run is not measurably slower than a resident one: the same
8-step 1024 image took 30.2s through the CLI and 31s through this server. Holding
the model in memory saves nothing worth having. Set the knobs in a browser instead
of retyping flags, and keep the prompt off disk.

NOTHING IS LOGGED OR SAVED. The prompt never reaches disk, the image never reaches
disk, and the server keeps no history after the response. The page keeps this
session's images in a gallery in tab memory, so a reload clears them. Generation goes straight
from mflux to PIL to an in-page data URL, which also means no EXIF metadata is
embedded; mflux normally writes the prompt into the PNG on save, and this path never
calls save. HTTP access logging is off. Use the download button in the page to keep
an image on purpose.

The server binds 127.0.0.1 by default, so it is not reachable from the network.

The one outbound request is the htmx script from a CDN. It carries no prompt data.

BATCHING is sequential, because mflux has no batched inference: generate_image takes
no batch dimension, and the CLI's --auto-seeds only loops over N seeds. So N images
cost N times the time of one. The count field saves you from resubmitting the form,
and nothing more. Each image is rendered as soon as it is done rather than at the end,
through a chain of htmx requests that carry their own parameters. With an explicit
seed the batch walks seed, seed+1, seed+2, so any image is reproducible from the CLI.
Edits batch the same way, through the same chain.

IMAGE-TO-IMAGE takes one reference image. The model itself handles up to 10 through
the diffusers edit pipeline, but mflux's qwen21 generate_image exposes a single
image_path, so that is the ceiling here. `qwen21 edit` is the multi-reference path.
The reference is passed to mflux as a PIL object, never as a file, so it does not
reach disk. It is the one thing the server holds between requests, because a batch
would otherwise re-post it once per image; see References.

PROGRESS AND CANCEL run over a one-second poll of /progress. No websocket, no SSE
extension, no extra dependency. One button carries both: it reads Generate or Edit
when idle and Cancel while a run is in flight. Cancel stops a generate at the end of
the current step (about 1s at 512, 3.5s at 1024) and kills an edit's child process
group (under 2s), and either way it drops the rest of the batch. There is no live preview; ProgressCallback says why. The page
prints an estimated run time under the button, because the output size drives the
cost superlinearly and a large reference can otherwise quietly cost five minutes.

USAGE:
    uv run qwen21_server.py                    # http://127.0.0.1:8765
    uv run qwen21_server.py --port 9000
    uv run qwen21_server.py -q 8               # int8 weights, for when RAM is tight
"""
import argparse
import base64
import gc
import html
import io
import json
import os
import pathlib
import queue
import random
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from PIL import Image

# qwen21_edit.py sits next to this file. resolve() follows the symlink that puts
# the wrapper on PATH, so the engine is found from either name.
EDIT_SCRIPT = pathlib.Path(__file__).resolve().parent / "qwen21_edit.py"
EDIT_STEP = re.compile(rb"step (\d+)/(\d+)")
MAX_REFERENCES = 10
EDIT_RESOLUTIONS = [1024, 768, 512, 1328]
# The edit pipeline treats output_resolution as an area budget, not a side: it
# calls calculate_dimensions(res * res, reference aspect ratio). So the shape
# always follows the reference, and this number only sets how many pixels. A
# 1280x720 reference comes back 1280x704, the multiple of 32 the pipeline needs.
EDIT_MATCH_CAP = 1328

MAX_BATCH = 8

MATCH = "match"

SIZES = [
    ("1024 x 1024", 1024, 1024),
    ("768 x 768 (faster)", 768, 768),
    ("512 x 512 (fastest)", 512, 512),
    ("1328 x 1328", 1328, 1328),
    ("1664 x 928 (16:9)", 1664, 928),
    ("928 x 1664 (9:16)", 928, 1664),
    ("1472 x 1140 (4:3)", 1472, 1140),
    ("1140 x 1472 (3:4)", 1140, 1472),
]

# The page is assembled with str.replace, not str.format, so the CSS and the
# JavaScript keep their normal single braces.
PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Qwen-Image-2.1</title>
<script src="https://unpkg.com/htmx.org@2.0.4"></script>
<style>
  :root {
    color-scheme: dark;
    --bg: #0e0e11; --surface: #15151a; --surface-2: #1c1c23; --surface-3: #24242d;
    --border: #2a2a33; --border-strong: #3a3a46;
    --text: #ececf1; --muted: #a0a0ad; --faint: #6e6e7a;
    --accent: #7c8cff; --accent-strong: #6273f2; --danger: #d9534f; --danger-strong: #e0625e;
    --radius: 12px; --radius-sm: 8px;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
         font: 14px/1.5 ui-sans-serif, -apple-system, system-ui, sans-serif; }
  .app { display: grid; grid-template-columns: minmax(0, 1fr) 380px; height: 100vh; }
  main { overflow-y: auto; padding: 28px 32px 40px; }
  aside { background: var(--surface); border-left: 1px solid var(--border); overflow-y: auto; }
  /* On a phone the controls come first, so the page opens on the prompt. */
  @media (max-width: 900px) {
    .app { grid-template-columns: 1fr; height: auto; }
    aside { order: -1; border-left: 0; border-bottom: 1px solid var(--border); }
    main { overflow: visible; padding: 20px 16px 32px; }
  }

  .topbar { display: flex; align-items: baseline; gap: 12px; margin-bottom: 18px; }
  h1 { font-size: 16px; font-weight: 650; margin: 0; letter-spacing: -0.01em; }
  .sub { color: var(--faint); font-size: 12px; }

  .stage { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    min-height: 52vh; display: flex; flex-direction: column; align-items: center;
    justify-content: center; padding: 18px; }
  .stage img { max-width: 100%; max-height: 66vh; border-radius: var(--radius-sm); display: block; }
  .stage .empty { color: var(--faint); font-size: 13px; text-align: center; max-width: 340px; }
  .details { align-self: stretch; margin-top: 14px; display: flex; flex-direction: column; gap: 10px; }
  .facts { display: flex; flex-wrap: wrap; gap: 6px; }
  .fact { background: var(--surface-2); border: 1px solid var(--border); border-radius: 999px;
    padding: 2px 10px; font-size: 12px; color: var(--muted); }
  .prompt-text { margin: 0; color: var(--muted); font-size: 13px; white-space: pre-wrap;
    overflow-wrap: anywhere; }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; }

  .gallery-head { display: flex; align-items: center; justify-content: space-between;
    margin: 26px 0 12px; }
  h2 { font-size: 13px; font-weight: 600; margin: 0; color: var(--muted); }
  .gallery { display: grid; grid-template-columns: repeat(auto-fill, minmax(132px, 1fr)); gap: 10px; }
  .tile { position: relative; aspect-ratio: 1; padding: 0; border-radius: var(--radius-sm);
    overflow: hidden; border: 1px solid var(--border); background: var(--surface-2); cursor: pointer; }
  .tile img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .tile:hover { border-color: var(--border-strong); }
  .tile.selected { outline: 2px solid var(--accent); outline-offset: 1px; }
  .tile .badge { position: absolute; left: 6px; bottom: 6px; background: rgba(0,0,0,.6);
    border-radius: 999px; padding: 0 7px; font-size: 11px; color: #ddd; }
  /* One placeholder while anything runs, so the next image has a visible slot. */
  .tile.pending { display: none; align-items: center; justify-content: center; cursor: default; }
  body.busy .tile.pending { display: flex; }

  form { display: flex; flex-direction: column; min-height: 100%; }
  .fields { padding: 22px 22px 8px; display: flex; flex-direction: column; gap: 16px; }
  .field { display: flex; flex-direction: column; gap: 6px; }
  label, .label { font-size: 12px; color: var(--muted); font-weight: 500; }
  .opt { color: var(--faint); font-weight: 400; }
  textarea, input, select { width: 100%; background: var(--surface-2); color: var(--text);
    border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 9px 11px; font: inherit; }
  textarea:focus, input:focus, select:focus { outline: none; border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(124, 140, 255, .18); }
  textarea { min-height: 120px; resize: vertical; }
  input[type=range] { padding: 0; border: 0; background: none; accent-color: var(--accent); box-shadow: none; }
  .pair { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .label-row { display: flex; justify-content: space-between; align-items: baseline; }

  .segmented { position: relative; display: grid; grid-template-columns: 1fr 1fr; gap: 3px; padding: 3px;
    background: var(--surface-2); border: 1px solid var(--border); border-radius: 10px; }
  .segmented input { position: absolute; opacity: 0; pointer-events: none; }
  .segmented label { text-align: center; padding: 7px 0; border-radius: 7px; cursor: pointer;
    color: var(--muted); font-size: 13px; }
  .segmented input:checked + label { background: var(--surface-3); color: var(--text);
    box-shadow: 0 1px 2px rgba(0,0,0,.4); }
  .segmented input:focus-visible + label { outline: 2px solid var(--accent); }

  .drop { border: 1px dashed var(--border-strong); border-radius: 10px; padding: 12px;
    display: flex; flex-direction: column; gap: 10px; cursor: pointer; background: var(--surface-2); }
  .drop:hover, .drop.over { border-color: var(--accent); }
  .drop.over { background: rgba(124, 140, 255, .08); }
  .drop .prompt-line { color: var(--faint); font-size: 12px; text-align: center; }
  .thumbs { display: flex; flex-wrap: wrap; gap: 8px; }
  .thumbs:empty { display: none; }
  .thumb { position: relative; width: 56px; height: 56px; }
  .thumb img { width: 100%; height: 100%; object-fit: cover; border-radius: 6px; display: block; }
  .thumb .drop-one { position: absolute; top: -6px; right: -6px; width: 20px; height: 20px;
    border-radius: 50%; border: 1px solid var(--border-strong); background: var(--surface-3);
    color: var(--muted); font-size: 12px; line-height: 1; padding: 0; cursor: pointer; }
  .thumb .drop-one:hover { color: #fff; background: var(--danger); }

  details summary { cursor: pointer; font-size: 12px; color: var(--muted); list-style: none; }
  details summary { display: flex; align-items: center; gap: 8px; }
  details summary::before { content: ""; width: 6px; height: 6px; margin-left: 2px;
    border-right: 1.5px solid currentColor; border-bottom: 1.5px solid currentColor;
    transform: rotate(-45deg); transition: transform .15s; }
  details[open] summary::before { transform: rotate(45deg); }
  details .fields-inner { display: flex; flex-direction: column; gap: 14px; margin-top: 12px; }

  form.mode-generate .edit-only, form.mode-edit .generate-only { display: none; }
  /* Strength means something only when there is a reference to be strong about. */
  .strength-field { display: none; }
  form.mode-generate.has-ref .strength-field { display: flex; }

  .footer { position: sticky; bottom: 0; margin-top: auto; padding: 14px 22px 20px;
    background: linear-gradient(to bottom, rgba(21,21,26,0), var(--surface) 18px);
    display: flex; flex-direction: column; gap: 8px; }
  .btn { border: 1px solid var(--border); background: var(--surface-2); color: var(--text);
    border-radius: var(--radius-sm); padding: 6px 12px; font: inherit; font-size: 12px; cursor: pointer;
    text-decoration: none; }
  .btn:hover { border-color: var(--border-strong); background: var(--surface-3); }
  .btn.danger:hover { background: var(--danger); border-color: var(--danger); }
  .link { background: none; border: 0; padding: 0; color: var(--accent); font: inherit;
    font-size: 12px; cursor: pointer; }
  .link:hover { text-decoration: underline; }
  /* The one button carries all three states. A separate Cancel button meant two
     controls for one run, and the disabled Generate button sat there saying
     nothing useful while the only live control was somewhere else. */
  #go { width: 100%; padding: 12px; border: 0; border-radius: 10px; font: inherit; font-weight: 600;
    color: #fff; cursor: pointer; background: linear-gradient(180deg, var(--accent), var(--accent-strong)); }
  #go:hover { filter: brightness(1.08); }
  #go .busy-label, #go .stopping-label { display: none; }
  body.busy #go .idle-label { display: none; }
  body.busy #go .busy-label { display: inline; }
  body.busy #go { background: var(--danger); }
  body.busy #go:hover { background: var(--danger-strong); }
  body.stopping #go .busy-label { display: none; }
  body.stopping #go .stopping-label { display: inline; }
  body.stopping #go { background: var(--surface-3); color: var(--faint); cursor: progress; filter: none; }

  .status { display: none; align-items: center; gap: 8px; color: var(--muted); font-size: 12px; }
  body.busy .status { display: flex; }
  .spinner { width: 14px; height: 14px; border-radius: 50%; flex: none;
    border: 2px solid var(--border-strong); border-top-color: var(--accent); animation: spin .8s linear infinite; }
  .tile.pending .spinner { width: 22px; height: 22px; border-width: 3px; }
  @keyframes spin { to { transform: rotate(360deg); } }
  #progress { display: none; }
  body.busy #progress { display: block; }
  .bar { height: 4px; background: var(--surface-3); border-radius: 2px; overflow: hidden; }
  .bar div { height: 100%; background: var(--accent); transition: width .4s linear; }
  #progress .hint { margin-top: 6px; }
  .hint { color: var(--faint); font-size: 12px; }
  .estimate { color: var(--faint); font-size: 12px; margin: 0; text-align: center; }
  body.busy .estimate { display: none; }
  .notice { margin: 0; font-size: 12px; color: var(--muted); }
  .notice:empty { display: none; }
  .notice.err { color: #ff8b7a; font-family: ui-monospace, monospace; white-space: pre-wrap; }
</style>
</head>
<body>
<div class="app">
  <main>
    <div class="topbar">
      <h1>Qwen-Image-2.1</h1>
      <span class="sub">__PRECISION__, nothing saved to disk</span>
    </div>
    <section class="stage" id="stage"></section>
    <div class="gallery-head">
      <h2>This session <span class="opt" id="gallery-count"></span></h2>
      <button type="button" class="link" id="clear-gallery">Clear</button>
    </div>
    <div class="gallery" id="gallery">
      <div class="tile pending"><div class="spinner"></div></div>
    </div>
    <!-- Server answers land here and move into the gallery. The batch chain
         placeholders wait here too, so the next request stays in the DOM. -->
    <div id="incoming" hidden></div>
  </main>

  <aside>
    <form id="form" class="mode-generate" hx-post="/generate" hx-target="#incoming"
          hx-swap="beforeend">
      <div class="fields">
        <div class="segmented" role="radiogroup" aria-label="Mode">
          <input type="radio" name="mode" id="mode-generate" value="generate" checked>
          <label for="mode-generate">Generate</label>
          <input type="radio" name="mode" id="mode-edit" value="edit">
          <label for="mode-edit">Edit</label>
        </div>

        <div class="field">
          <label for="prompt">
            <span class="generate-only">Prompt</span>
            <span class="edit-only">Edit instruction</span>
          </label>
          <textarea id="prompt" name="prompt" autofocus
            placeholder="Quote any text you want rendered, exactly."></textarea>
        </div>

        <div class="field">
          <div class="label-row">
            <span class="label">
              <span class="generate-only">Reference <span class="opt">(optional, one image)</span></span>
              <span class="edit-only">References <span class="opt">(required, up to __MAX_REFERENCES__)</span></span>
            </span>
            <button type="button" class="link" id="clear-reference">Clear</button>
          </div>
          <div class="drop" id="drop" tabindex="0">
            <div class="thumbs" id="thumbs"></div>
            <div class="prompt-line" id="reference-note"></div>
          </div>
          <input id="reference" type="file" accept="image/*" hidden>
        </div>

        <div class="field">
          <label for="size">Size</label>
          <select id="size" name="size" class="generate-only">__SIZE_OPTIONS__</select>
          <select id="resolution" name="resolution" class="edit-only">__EDIT_RESOLUTIONS__</select>
        </div>

        <div class="field strength-field">
          <div class="label-row">
            <label for="strength">Reference strength <span class="opt">(share of the schedule skipped)</span></label>
            <output id="strength-value">0.40</output>
          </div>
          <input id="strength" name="strength" type="range" value="0.4" step="0.05" min="0.05" max="1">
        </div>

        <div class="field">
          <label for="count">Count</label>
          <input id="count" name="count" type="number" value="1" min="1" max="__MAX_BATCH__">
        </div>

        <details id="advanced">
          <summary>Advanced</summary>
          <div class="fields-inner">
            <div class="pair">
              <div class="field">
                <label for="steps">Steps</label>
                <input id="steps" name="steps" type="number" value="40" min="1" max="100">
              </div>
              <div class="field generate-only">
                <label for="guidance">Guidance</label>
                <input id="guidance" name="guidance" type="number" value="1.0" step="0.5" min="0">
              </div>
              <div class="field edit-only">
                <label for="cfg">True CFG <span class="opt">(raise if ignored)</span></label>
                <input id="cfg" name="cfg" type="number" value="1.0" step="0.5" min="1" max="10">
              </div>
            </div>
            <div class="field">
              <label for="seed">Seed</label>
              <input id="seed" name="seed" placeholder="random">
            </div>
            <div class="field">
              <label for="negative">Negative prompt</label>
              <input id="negative" name="negative" placeholder="optional">
            </div>
          </div>
        </details>
      </div>

      <div class="footer">
        <button id="go" type="submit">
          <span class="idle-label"><span class="generate-only">Generate</span><span
            class="edit-only">Edit</span></span>
          <span class="busy-label">Cancel</span>
          <span class="stopping-label">Stopping&hellip;</span>
        </button>
        <div class="status">
          <div class="spinner"></div>
          <span><span id="status-text">Generating</span> (<span id="elapsed">0s</span>)</span>
        </div>
        <div id="progress"></div>
        <p class="estimate" id="estimate"></p>
        <p class="notice" id="notice"></p>
      </div>
    </form>
  </aside>
</div>

<script>
  // One timer for the whole run. A batch is a chain of requests, so the button
  // and the clock must stay live until no .chain placeholder is left in the DOM.
  const go = document.getElementById('go');
  const statusText = document.getElementById('status-text');
  const elapsedText = document.getElementById('elapsed');
  const countInput = document.getElementById('count');
  const notice = document.getElementById('notice');
  let startedAt = 0;
  let ticker = null;

  function label(element) {
    if (element.dataset.progress) return 'Working on ' + element.dataset.progress;
    const total = parseInt(countInput.value, 10);
    return total > 1 ? 'Working on 1 of ' + total : 'Working';
  }

  // The poller clocks itself off its own response, and stops when the server
  // says nothing is running. That gap happens between two images of a batch, so
  // every request the page sends plants a fresh poller.
  const progressSlot = document.getElementById('progress');
  const POLLER = '<div hx-get="/progress" hx-trigger="load"'
    + ' hx-target="#progress" hx-swap="innerHTML"></div>';

  function startWork(element) {
    statusText.textContent = label(element);
    document.body.classList.add('busy');
    progressSlot.innerHTML = POLLER;
    htmx.process(progressSlot);
    if (ticker) return;
    startedAt = Date.now();
    elapsedText.textContent = '0s';
    ticker = setInterval(function () {
      elapsedText.textContent = Math.round((Date.now() - startedAt) / 1000) + 's';
    }, 1000);
  }

  function stopWork() {
    clearInterval(ticker);
    ticker = null;
    document.body.classList.remove('busy', 'stopping');
    progressSlot.innerHTML = '';
  }

  // One button, three states. Idle it submits the form. While a run is in
  // flight it reads Cancel, so the click must not reach htmx's submit handling;
  // capture phase runs before that. A second click during Stopping does
  // nothing, because the run is already ending.
  go.addEventListener('click', function (event) {
    if (!document.body.classList.contains('busy')) return;
    event.preventDefault();
    event.stopPropagation();
    if (document.body.classList.contains('stopping')) return;
    document.body.classList.add('stopping');
    statusText.textContent = 'Stopping';
    htmx.ajax('POST', '/cancel', { swap: 'none' });
  }, true);

  // References live in one array, whatever put them there: the picker, a drop,
  // a paste, or "Use as reference" on a result. Generate takes one image, since
  // mflux exposes a single image_path, so a new one replaces the old. Edit takes
  // up to MAX_REFERENCES. Files are read here and posted as base64 in a normal
  // form field, which keeps the server off multipart parsing that the standard
  // library no longer ships.
  const MAX_REFERENCES = __MAX_REFERENCES__;
  const EDIT_MATCH_CAP = __EDIT_MATCH_CAP__;
  const form = document.getElementById('form');
  const referenceInput = document.getElementById('reference');
  const referenceNote = document.getElementById('reference-note');
  const drop = document.getElementById('drop');
  const thumbs = document.getElementById('thumbs');
  let references = [];

  function editing() {
    return document.getElementById('mode-edit').checked;
  }

  function referenceLimit() {
    return editing() ? MAX_REFERENCES : 1;
  }

  function renderReferences() {
    form.classList.toggle('has-ref', references.length > 0);
    referenceInput.multiple = editing();
    showEstimate();
    thumbs.innerHTML = '';
    references.forEach(function (reference, index) {
      const thumb = document.createElement('div');
      thumb.className = 'thumb';
      thumb.title = reference.name;
      const image = document.createElement('img');
      image.src = 'data:image/png;base64,' + reference.b64;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'drop-one';
      remove.textContent = '\\u00d7';
      remove.title = 'Remove this reference';
      remove.addEventListener('click', function (event) {
        event.stopPropagation();  // the drop zone opens the picker on click
        references.splice(index, 1);
        renderReferences();
      });
      thumb.append(image, remove);
      thumbs.append(thumb);
    });
    if (!references.length) {
      referenceNote.textContent = 'Drop, paste or click to add '
        + (editing() ? 'images' : 'an image for image-to-image');
    } else if (editing()) {
      const last = references[references.length - 1];
      referenceNote.textContent = references.length + ' of ' + MAX_REFERENCES
        + (last.width ? ', last is ' + last.width + ' x ' + last.height : '');
    } else {
      referenceNote.textContent = 'Image-to-image. A new image replaces this one.';
    }
  }

  function addReference(b64, name) {
    if (referenceLimit() === 1) references = [];
    if (references.length >= referenceLimit()) {
      referenceNote.textContent = 'At most ' + MAX_REFERENCES + ' references.';
      return;
    }
    const entry = { b64: b64, name: name, width: 0, height: 0 };
    references.push(entry);
    // The estimate needs the pixel count, and "Match the reference" cannot work
    // out the output size without it.
    const probe = new Image();
    probe.onload = function () {
      entry.width = probe.naturalWidth;
      entry.height = probe.naturalHeight;
      renderReferences();
    };
    probe.src = 'data:image/png;base64,' + b64;
    renderReferences();
  }

  function addFiles(files) {
    Array.from(files).filter(function (file) {
      return file.type.startsWith('image/');
    }).forEach(function (file) {
      const reader = new FileReader();
      reader.onload = function () {
        addReference(reader.result.split(',')[1], file.name);
      };
      reader.readAsDataURL(file);
    });
  }

  referenceInput.addEventListener('change', function () {
    addFiles(referenceInput.files);
    referenceInput.value = '';
  });
  drop.addEventListener('click', function () { referenceInput.click(); });
  drop.addEventListener('keydown', function (event) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      referenceInput.click();
    }
  });
  drop.addEventListener('dragover', function (event) {
    event.preventDefault();
    drop.classList.add('over');
  });
  drop.addEventListener('dragleave', function () { drop.classList.remove('over'); });
  drop.addEventListener('drop', function (event) {
    event.preventDefault();
    drop.classList.remove('over');
    addFiles(event.dataTransfer.files);
  });
  document.addEventListener('paste', function (event) {
    const files = event.clipboardData ? event.clipboardData.files : [];
    if (!files.length) return;  // a text paste goes to the field as usual
    event.preventDefault();
    addFiles(files);
  });

  document.getElementById('clear-reference').addEventListener('click', function () {
    references = [];
    renderReferences();
  });

  // The mode only changes what the form looks like. The route stays /generate,
  // which dispatches on the mode field. Swapping hx-post here does not work:
  // htmx resolves the route when it first processes the element, so a later
  // setAttribute is ignored and every edit went to the generate engine.
  // The references are cleared, because the two modes read them differently:
  // a list built for an edit would silently shrink to its first image.
  form.querySelectorAll('input[name=mode]').forEach(function (radio) {
    radio.addEventListener('change', function () {
      form.classList.toggle('mode-edit', editing());
      form.classList.toggle('mode-generate', !editing());
      references = [];
      renderReferences();
    });
  });

  const strength = document.getElementById('strength');
  const strengthValue = document.getElementById('strength-value');
  strength.addEventListener('input', function () {
    strengthValue.textContent = Number(strength.value).toFixed(2);
  });

  // The gallery lives in this tab only. The server keeps no image after it
  // answers, and the page keeps them in memory, so a reload clears them and
  // nothing reaches disk. The download button is the way to keep one.
  const incoming = document.getElementById('incoming');
  const galleryNode = document.getElementById('gallery');
  const pendingTile = galleryNode.querySelector('.pending');
  const stage = document.getElementById('stage');
  const galleryCount = document.getElementById('gallery-count');
  let gallery = [];
  let selectedId = null;
  let nextId = 1;

  function harvest() {
    incoming.querySelectorAll('.item').forEach(function (node) {
      const data = node.dataset;
      gallery.unshift({
        id: nextId++, src: node.querySelector('img').src, seed: data.seed,
        width: data.width, height: data.height, steps: data.steps, elapsed: data.elapsed,
        position: data.position, mode: data.mode, prompt: data.prompt,
      });
      selectedId = gallery[0].id;
      node.remove();
    });
    incoming.querySelectorAll(':scope > .err, :scope > .hint').forEach(function (node) {
      notice.textContent = node.textContent;
      notice.classList.toggle('err', node.classList.contains('err'));
      node.remove();
    });
    renderGallery();
    // The last image of a batch arrives by a chain placeholder, and removing it
    // here detaches the node htmx then fires afterSettle on, so that event never
    // reaches the body. The run ends here instead, once no link is left.
    if (!incoming.querySelector('.chain')) stopWork();
  }

  // Answers arrive by several routes: the form's own request, and each chain
  // placeholder replacing itself. Watching the container catches all of them.
  new MutationObserver(function (records) {
    if (records.some(function (record) { return record.addedNodes.length; })) harvest();
  }).observe(incoming, { childList: true, subtree: true });

  function renderGallery() {
    galleryNode.querySelectorAll('.tile:not(.pending)').forEach(function (tile) { tile.remove(); });
    gallery.forEach(function (entry) {
      const tile = document.createElement('button');
      tile.type = 'button';
      tile.className = 'tile' + (entry.id === selectedId ? ' selected' : '');
      const image = document.createElement('img');
      image.src = entry.src;
      image.alt = entry.prompt;
      const badge = document.createElement('span');
      badge.className = 'badge';
      badge.textContent = entry.mode;
      tile.append(image, badge);
      tile.addEventListener('click', function () {
        selectedId = entry.id;
        renderGallery();
      });
      galleryNode.append(tile);
    });
    galleryCount.textContent = gallery.length ? '(' + gallery.length + ')' : '';
    renderStage();
  }

  function actionButton(text, handler, extraClass) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn' + (extraClass ? ' ' + extraClass : '');
    button.textContent = text;
    button.addEventListener('click', handler);
    return button;
  }

  function renderStage() {
    const entry = gallery.find(function (item) { return item.id === selectedId; });
    stage.innerHTML = '';
    if (!entry) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = 'Images appear here. They live in this tab only: '
        + 'a reload clears them, and nothing is written to disk.';
      stage.append(empty);
      return;
    }
    const image = document.createElement('img');
    image.src = entry.src;
    image.alt = entry.prompt;

    const facts = document.createElement('div');
    facts.className = 'facts';
    [entry.mode, entry.position, 'seed ' + entry.seed, entry.width + ' x ' + entry.height,
     entry.steps + ' steps', entry.elapsed + 's'].forEach(function (text) {
      const fact = document.createElement('span');
      fact.className = 'fact';
      fact.textContent = text;
      facts.append(fact);
    });

    const prompt = document.createElement('p');
    prompt.className = 'prompt-text';
    prompt.textContent = entry.prompt;

    const download = document.createElement('a');
    download.className = 'btn';
    download.href = entry.src;
    download.download = 'qwen21-' + entry.mode + '-' + entry.seed + '.png';
    download.textContent = 'Download';

    // Every action is pure page state; nothing is sent until the next submit.
    const actions = document.createElement('div');
    actions.className = 'actions';
    actions.append(
      actionButton('Use as reference', function () {
        addReference(entry.src.split(',')[1], 'result, seed ' + entry.seed);
      }),
      actionButton('Reuse seed', function () {
        document.getElementById('seed').value = entry.seed;
        document.getElementById('advanced').open = true;
      }),
      actionButton('Reuse prompt', function () {
        document.getElementById('prompt').value = entry.prompt;
      }),
      download,
      actionButton('Remove', function () { removeEntry(entry.id); }, 'danger')
    );

    const details = document.createElement('div');
    details.className = 'details';
    details.append(facts, prompt, actions);
    stage.append(image, details);
  }

  function removeEntry(id) {
    const index = gallery.findIndex(function (item) { return item.id === id; });
    gallery.splice(index, 1);
    const neighbour = gallery[Math.min(index, gallery.length - 1)];
    selectedId = neighbour ? neighbour.id : null;
    renderGallery();
  }

  document.getElementById('clear-gallery').addEventListener('click', function () {
    if (!gallery.length || !confirm('Clear all ' + gallery.length + ' images from this tab?')) return;
    gallery = [];
    selectedId = null;
    renderGallery();
  });

  // Cost, before you spend it. Measured seconds per step on this machine:
  //
  //   megapixels   0.26   0.59   1.05   1.60   1.75
  //   mflux t2i    1.01   1.79   3.32      -   6.14
  //   edit         0.76   1.87   3.52   7.95   7.40
  //
  // The cost is superlinear in pixels, because attention is quadratic in token
  // count. A flat rate per pixel fit the small sizes and then under-promised
  // badly at the top: it called a run 4 minutes that took 345 seconds. That
  // edit was 1265 px at 40 steps; the same edit at 768 px and 24 steps took 72s
  // and was just as correct, so size is the dial to show. An
  // exponent of 1.25 holds both engines inside 3.3 to 4.4, so one curve covers
  // both. The constant sits at the high end on purpose, because an estimate
  // that runs short is worse than one that runs long.
  const STEP_COST = 4.0;          // seconds per step at one megapixel
  const STEP_EXPONENT = 1.25;
  const GENERATE_OVERHEAD = 3;    // per image; the model is already resident
  const EDIT_OVERHEAD = 20;       // once per batch; the child may have to load a pipeline
  const estimateText = document.getElementById('estimate');

  function editResolution() {
    const chosen = document.getElementById('resolution').value;
    if (chosen !== 'match') return Number(chosen);
    const reference = references[references.length - 1];
    if (!reference || !reference.width) return 1024;
    return Math.min(Math.round(Math.sqrt(reference.width * reference.height)),
                    EDIT_MATCH_CAP);
  }

  function targetPixels() {
    if (editing()) {
      const side = editResolution();
      return side * side;
    }
    const size = document.getElementById('size').value;
    if (size === 'match') return 1024 * 1024;
    const parts = size.split('x').map(Number);
    return parts[0] * parts[1];
  }

  function spell(seconds) {
    if (seconds < 90) return Math.round(seconds / 5) * 5 + 's';
    const minutes = Math.floor(seconds / 60);
    const rest = Math.round((seconds % 60) / 15) * 15;
    if (rest && rest < 60) return minutes + ' min ' + rest + 's';
    return (minutes + (rest ? 1 : 0)) + ' min';
  }

  function showEstimate() {
    if (editing() && !references.length) {
      estimateText.textContent = 'Add a reference image to edit.';
      return;
    }
    const steps = Number(document.getElementById('steps').value) || 0;
    const count = Number(countInput.value) || 1;
    const megapixels = targetPixels() / 1e6;
    const perStep = STEP_COST * Math.pow(megapixels, STEP_EXPONENT);
    const overhead = editing() ? EDIT_OVERHEAD : count * GENERATE_OVERHEAD;
    const seconds = count * steps * perStep + overhead;
    const side = editing() ? ', output about ' + editResolution() + ' px' : '';
    estimateText.textContent = 'about ' + spell(seconds) + side;
  }

  form.addEventListener('input', showEstimate);
  form.addEventListener('change', showEstimate);

  renderReferences();
  renderGallery();

  function sideChannel(event) {
    const config = event.detail.requestConfig || event.detail.pathInfo || {};
    const path = config.path || config.requestPath || '';
    return path === '/progress' || path === '/cancel';
  }

  // The references are an array, not a form field, so they are attached here.
  // Only the form itself carries them: a chain request already has a token.
  document.body.addEventListener('htmx:configRequest', function (event) {
    if (event.detail.elt !== form) return;
    event.detail.parameters.references = JSON.stringify(references.map(function (r) {
      return r.b64;
    }));
  });

  document.body.addEventListener('htmx:beforeRequest', function (event) {
    if (sideChannel(event)) return;
    if (event.detail.elt === form) notice.textContent = '';
    startWork(event.detail.elt);
  });
  document.body.addEventListener('htmx:afterSettle', function (event) {
    // A /progress response settles once a second. It is not the end of the run,
    // and treating it as one used to clear the busy state mid-generation.
    if (sideChannel(event)) return;
    if (!document.querySelector('.chain')) stopWork();
  });
  document.body.addEventListener('htmx:responseError', stopWork);
  document.body.addEventListener('htmx:sendError', stopWork);
</script>
</body>
</html>
"""

# One finished image, as a data carrier. The page moves it into the gallery and
# renders it there, so this markup is never shown as it is.
ITEM = """<div class="item" data-seed="{seed}" data-width="{width}" data-height="{height}"
  data-steps="{steps}" data-elapsed="{elapsed:.0f}" data-position="{position}"
  data-mode="{mode}" data-prompt="{prompt}"><img src="data:image/png;base64,{b64}" alt=""></div>"""

CHAIN = (
    '<div class="chain" data-progress="{progress}" hx-post="/generate"'
    " hx-vals='{values}' hx-trigger=\"load\" hx-target=\"this\""
    ' hx-swap="outerHTML"></div>'
)


def render_page(precision):
    options = "".join(
        f'<option value="{width}x{height}">{label}</option>' for label, width, height in SIZES
    )
    options += f'<option value="{MATCH}">Match reference (about 1 MP)</option>'
    resolutions = f'<option value="{MATCH}">Match the reference</option>' + "".join(
        f'<option value="{side}">about {side} x {side}</option>' for side in EDIT_RESOLUTIONS
    )
    return (
        PAGE.replace("__PRECISION__", precision)
        .replace("__SIZE_OPTIONS__", options)
        .replace("__EDIT_RESOLUTIONS__", resolutions)
        .replace("__MAX_BATCH__", str(MAX_BATCH))
        .replace("__MAX_REFERENCES__", str(MAX_REFERENCES))
        .replace("__EDIT_MATCH_CAP__", str(EDIT_MATCH_CAP))
    )


def read_form(handler):
    """Pull the POST body into a plain dict of single values."""
    length = int(handler.headers.get("Content-Length", 0))
    body = handler.rfile.read(length).decode("utf-8")
    return {key: values[0] for key, values in parse_qs(body, keep_blank_values=True).items()}


class References:
    """Uploaded reference images, held in memory only, for the life of one batch.

    One token maps to a list, because an edit takes up to 10 references while
    image-to-image takes one. The generate path just uses the first.

    A batch is a chain of requests, so the reference must outlive the request that
    carried it. The browser sends the bytes once; the chain then passes a token.
    The entry is dropped when the batch ends, and the store is capped so a batch
    the user abandons cannot pin memory for the life of the process.

    This is the one thing the server keeps between requests. It never reaches disk.
    """

    LIMIT = 4

    def __init__(self):
        self.images = {}
        self.lock = threading.Lock()

    def add(self, images):
        token = secrets.token_urlsafe(12)
        with self.lock:
            while len(self.images) >= self.LIMIT:
                self.images.pop(next(iter(self.images)))
            self.images[token] = images
        return token

    def get(self, token):
        with self.lock:
            return self.images.get(token)

    def drop(self, token):
        with self.lock:
            self.images.pop(token, None)


def parse_size(raw):
    width, _, height = raw.partition("x")
    return int(width), int(height)


def match_reference_size(image, budget=1024 * 1024):
    """The reference's own aspect ratio at about `budget` pixels, on a 16 grid.

    mflux resizes the reference to the target size with a plain resize, so asking
    for a square output from a 16:9 photo squashes it. This keeps the shape.
    """
    scale = (budget / (image.width * image.height)) ** 0.5
    width = max(16, 16 * round(image.width * scale / 16))
    height = max(16, 16 * round(image.height * scale / 16))
    return width, height


def load_references(form, references):
    """The reference images for this request, and the token the chain reuses.

    The first request of a batch carries the images as base64 in a JSON array.
    Every later request carries only the token, so the bytes cross the wire once.
    Returns an empty list when there is no reference at all.
    """
    token = form.get("reference_token", "").strip()
    if token:
        return references.get(token) or [], token
    blobs = json.loads(form.get("references") or "[]")
    if not blobs:
        # The page always sends the field, empty when text-to-image. Minting a
        # token for an empty list made every plain generate look like an expired
        # reference.
        return [], None
    if len(blobs) > MAX_REFERENCES:
        raise ValueError(f"at most {MAX_REFERENCES} reference images")
    images = []
    for blob in blobs:
        image = Image.open(io.BytesIO(base64.b64decode(blob)))
        image.load()
        images.append(image)
    return images, references.add(images)


def resolve_size(form, reference):
    raw = form.get("size", "1024x1024")
    if raw != MATCH:
        return parse_size(raw)
    if reference is None:
        return 1024, 1024
    return match_reference_size(reference)


def build_params(form, references):
    """Turn the form into generate_image keyword arguments.

    mflux's qwen21 generate_image exposes a single image_path, so only the first
    reference is used here. Editing is the path that takes all of them.
    """
    reference = references[0] if references else None
    width, height = resolve_size(form, reference)
    seed = form.get("seed", "").strip()
    negative = form.get("negative", "").strip()
    params = {
        "seed": int(seed) if seed else random.randint(0, 1_000_000_000),
        "prompt": form.get("prompt", "").strip(),
        "negative_prompt": negative or None,
        "width": width,
        "height": height,
        "num_inference_steps": int(form.get("steps") or 40),
        "guidance": float(form.get("guidance") or 1.0),
    }
    if reference is not None:
        # mflux skips this share of the schedule: init_time_step =
        # max(1, int(steps * strength)). RMS distance from the reference, one pear
        # at 8 steps: 17.1 at 0.15, 4.0 at 0.55, 2.5 at 0.85, and 74.5 with no
        # reference. Every strength stays close to the reference, so drop the
        # reference when the prompt should win.
        strength = float(form.get("strength") or 0.4)
        if not 0.0 < strength <= 1.0:
            raise ValueError("strength must be above 0 and at most 1")
        params["image_path"] = reference
        params["image_strength"] = strength
    return params


def match_edit_resolution(reference):
    """The reference's own pixel count, as the area budget the pipeline wants.

    An edit usually wants its input back at the size it came in at, so this is
    the default. The cap is there because output_resolution drives the whole
    denoising cost: a 2560x1440 screenshot would ask for about 1920, which is
    far past anything this machine renders in reasonable time.
    """
    side = round((reference.width * reference.height) ** 0.5)
    return min(side, EDIT_MATCH_CAP)


def build_edit_request(form, references):
    """Turn the form into a stdio job for qwen21_edit.py.

    Images go as base64 PNG rather than paths. The page's contract is that no
    prompt and no image reaches disk, and a path would break it.
    """
    if not references:
        raise ValueError("editing needs at least one reference image")
    seed = form.get("seed", "").strip()
    raw = form.get("resolution") or MATCH
    if raw == MATCH:
        # The pipeline sizes from the last reference, so match that one.
        resolution = match_edit_resolution(references[-1])
    elif int(raw) in EDIT_RESOLUTIONS:
        resolution = int(raw)
    else:
        raise ValueError(f"resolution must be {MATCH} or one of {EDIT_RESOLUTIONS}")
    scale = float(form.get("cfg") or 1.0)
    negative = form.get("negative", "").strip()
    return {
        "prompt": form.get("prompt", "").strip(),
        "images": [png_b64(image) for image in references],
        "negative_prompt": negative or None,
        "true_cfg_scale": scale,
        "steps": int(form.get("steps") or 40),
        "output_resolution": resolution,
        "seed": int(seed) if seed else None,
    }


def build_position(form):
    """Which image of how many. The chain carries these, so the server holds no
    batch state; the first request from the form carries neither and starts at 1."""
    total = int(form.get("total") or form.get("count") or 1)
    index = int(form.get("index") or 1)
    if not 1 <= total <= MAX_BATCH:
        raise ValueError(f"count must be between 1 and {MAX_BATCH}")
    return total, index


def next_values(form, kind, request, seed):
    """The form fields for the next image of a batch: the same job at seed + 1.

    An edit carries the raw resolution field, not the resolved number, because
    "match" resolves to a size outside EDIT_RESOLUTIONS and would fail the check
    on the way back in. The token keeps the references, so it resolves the same.
    """
    values = {
        "mode": kind,
        "prompt": request["prompt"],
        "negative": form.get("negative", ""),
        "seed": str(seed + 1),
    }
    if kind == "edit":
        values["resolution"] = form.get("resolution") or MATCH
        values["cfg"] = str(request["true_cfg_scale"])
        values["steps"] = str(request["steps"])
        return values
    values["size"] = f"{request['width']}x{request['height']}"
    values["guidance"] = str(request["guidance"])
    values["steps"] = str(request["num_inference_steps"])
    if "image_strength" in request:
        values["strength"] = str(request["image_strength"])
    return values


def build_chain(values, total, index, token):
    """The placeholder that fetches the next image, or nothing when this was the last.

    It carries every text parameter it needs, so a reload loses the batch instead
    of leaving the server generating into a void. A reference image is the one
    exception: the chain carries a token and the pixels stay in References, so a
    multi-megabyte image is not re-posted once per image in the batch.
    """
    if index >= total:
        return ""
    values = {**values, "total": str(total), "index": str(index + 1)}
    if token:
        values["reference_token"] = token
    return CHAIN.format(
        progress=f"{index + 1} of {total}",
        values=html.escape(json.dumps(values), quote=True),
    )


def error_fragment(message):
    return f'<div class="err">{html.escape(message)}</div>'


def cancelled_fragment(stop):
    return f'<div class="hint">Cancelled ({html.escape(str(stop))}).</div>'


def item_fragment(image, seed, position, steps, started, prompt, mode):
    return ITEM.format(
        b64=png_b64(image),
        position=position,
        seed=seed,
        width=image.width,
        height=image.height,
        steps=steps,
        elapsed=time.time() - started,
        prompt=html.escape(prompt, quote=True),
        mode=mode,
    )


def png_b64(pil_image):
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")

class Cancelled(Exception):
    """Raised out of the denoising loop when the page asks to stop."""


class Progress:
    """What the running generation is doing, for the page to poll.

    One object for the whole server, because only one generation runs at a time.
    Every field is read by request threads and written by the worker thread, so
    it all goes behind one lock.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.stage = ""
        self.step = 0
        self.total = 0
        self.label = ""
        self.cancel_requested = False

    def begin_job(self, label):
        """The worker has the job but has not entered the loop yet.

        Restoring the text encoder after a prompt change happens in here, and
        that takes a second. Without this the page would show an empty bar and
        look stuck.
        """
        with self.lock:
            self.running = True
            self.stage = "preparing"
            self.step = 0
            self.total = 0
            self.label = label

    def set_step(self, step, total):
        """Note: this does not clear cancel_requested.

        A batch is a chain of separate generations with a gap between them. A
        cancel that lands in a gap must still stop the batch, so the flag is
        cleared by the worker when it consumes it, and by the first request of
        a fresh batch. See Qwen21Handler.do_POST.
        """
        with self.lock:
            self.stage = "running"
            self.step = step
            self.total = total

    def finish(self):
        with self.lock:
            self.running = False
            self.stage = ""

    def cancel(self):
        with self.lock:
            self.cancel_requested = True

    def consume_cancel(self):
        """Read the cancel flag and clear it, as one step."""
        with self.lock:
            wanted = self.cancel_requested
            self.cancel_requested = False
            return wanted

    def clear_cancel(self):
        with self.lock:
            self.cancel_requested = False

    def snapshot(self):
        with self.lock:
            return {
                "running": self.running,
                "stage": self.stage,
                "step": self.step,
                "total": self.total,
                "label": self.label,
                "cancel_requested": self.cancel_requested,
            }


class ProgressCallback:
    """mflux's per-step hook: the only way into a generation already running.

    Registered once on the model, not once per generation, because
    CallbackRegistry.register appends and never dedups. Per-generation state
    lives in the Progress object instead.

    Cancel raises from here. mflux's loop catches only KeyboardInterrupt, so a
    different exception propagates straight out of generate_image, which is
    what we want: it stops at the current step rather than the current batch.

    This hook could also decode the half-finished latents and show a live
    preview. It does not, and that is deliberate. A preview is a full VAE
    decode, and Qwen-Image-2.1 uses a 64-channel causal VAE at 16x spatial
    compression, so the decode alone timed 1.40s at 512, 7.42s at 768 and 8.05s
    at 1024. The wall-clock price is worse than the decode, because the
    decode's allocations disturb the steps that follow. At 1024, 40 steps, two
    runs each:

        no previews      157.4s  154.9s
        every 20 steps   187.1s  176.0s
        every  5 steps   248.3s  295.6s

    One preview at 1024 therefore costs about 25s. That is not a feature, it is
    a tax, so the step counter is all this reports.
    """

    def __init__(self, progress):
        self.progress = progress

    def call_in_loop(self, t, seed, prompt, latents, config, time_steps):
        state = self.progress.snapshot()
        if state["cancel_requested"]:
            raise Cancelled(f"stopped at step {t + 1}")
        self.progress.set_step(t + 1, state["total"])


class EditEngine:
    """A long-lived qwen21_edit.py child that answers one edit at a time.

    Editing cannot live in this process. It needs diffusers and torch, and this
    server runs on mflux; the two pull different, heavy dependency trees, and
    mflux has never ported the Qwen3-VL vision tower that instruction editing
    depends on. A child process keeps both engines intact and keeps this file
    free of a second model stack.

    The child speaks JSON over pipes, not files and not flags. Reference images
    as paths would put them on disk and the prompt as an argument would put it
    in `ps`, and the page promises neither happens.

    It stays alive between edits because building the pipeline costs 20 to 36
    seconds and nothing about it depends on the job. Two 768 edits measured
    31.9s then 19.6s down one child, so the second paid no load at all. It does
    not stay alive across a switch to generating: the edit engine measured
    38.7 GiB allocated on MPS and mflux peaks at 30.7 GB, which do not fit
    together, so GenerationWorker stops one before starting the other.

    start_new_session puts the child in its own process group, and cancel kills
    that whole group. Killing the child alone does not work: qwen21_edit.py has
    a `uv run` shebang, so the process here is uv and the interpreter is its
    child. Killing uv left the interpreter denoising to the last step, which
    made cancel look like it did nothing for 20 seconds.
    """

    def __init__(self):
        self.proc = None
        self.progress = None

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def ensure(self):
        if self.running():
            return
        self.proc = subprocess.Popen(
            [str(EDIT_SCRIPT), "--stdio"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True,
        )
        threading.Thread(target=self._watch_steps, args=(self.proc,), daemon=True).start()

    def stop(self):
        """Kill the child and free the memory the next generation needs."""
        if self.proc is None:
            return
        self._kill()
        self.proc = None

    def _kill(self):
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            self.proc.kill()  # the group is already gone

    def _watch_steps(self, proc):
        """Turn the child's step lines into progress, for the child's whole life."""
        for line in proc.stderr:
            match = EDIT_STEP.search(line)
            if match and self.progress is not None:
                self.progress.set_step(int(match.group(1)), int(match.group(2)))

    def submit(self, request, progress):
        """Run one edit. Returns the image and the seed it used."""
        self.ensure()
        self.progress = progress
        stopped_at = []
        answered = threading.Event()
        watcher = threading.Thread(
            target=self._watch_cancel, args=(progress, stopped_at, answered), daemon=True
        )
        watcher.start()
        try:
            self.proc.stdin.write(json.dumps(request).encode() + b"\n")
            self.proc.stdin.flush()
            payload = self.proc.stdout.readline()
        except (BrokenPipeError, OSError):
            payload = b""
        answered.set()
        watcher.join()

        # Only a kill counts as a cancel. A cancel that lands after the answer
        # keeps the finished image and the warm child.
        if stopped_at:
            self.proc = None  # the kill took the pipeline with it
            raise Cancelled(f"stopped at step {stopped_at[0] if stopped_at else 0}")
        if not payload:
            self.stop()
            raise RuntimeError("the edit engine stopped answering")
        result = json.loads(payload)
        if "error" in result:
            raise RuntimeError(result["error"])
        image = Image.open(io.BytesIO(base64.b64decode(result["image"])))
        image.load()
        return image, result["seed"]

    def _watch_cancel(self, progress, stopped_at, answered):
        """Cancel means kill. There is no way to interrupt the child politely,
        and the pipeline dies with it, so the next edit rebuilds.

        The watch ends with the edit. The child outlives it, and a watcher
        left polling an idle child killed it on the next cancel of anything."""
        while not answered.is_set() and self.running():
            if progress.snapshot()["cancel_requested"]:
                stopped_at.append(progress.snapshot()["step"])
                self._kill()
                return
            answered.wait(0.4)


class Job:
    """One unit of work for the worker thread, and the slot its answer comes back in.

    `kind` is "generate" for the mflux path or "edit" for the subprocess. Both
    queue here so the two engines never hold the GPU at the same time.
    """

    def __init__(self, kind, request, label):
        self.kind = kind
        self.request = request
        self.label = label
        self.done = threading.Event()
        self.image = None
        self.seed = None
        self.error = None


class GenerationWorker:
    """Owns the model and every MLX call, on one thread.

    It also runs editing, which happens in a child process rather than here.
    Both paths queue on this thread so the two engines never hold the GPU at
    once; see _serve_edit for why the mflux model is dropped first.

    MLX binds GPU streams to the thread that created them, and
    ThreadingHTTPServer answers each request on a fresh thread. Calling the
    model straight from a request thread aborts the process with
    "There is no Stream(gpu, 1) in current thread". So request threads hand a
    Job to this queue and wait, and only this thread touches MLX.

    The queue also serializes generations, which is what we want anyway. Two 512
    runs measured back to back took 26s of wall clock; the same two run at once
    took 31s, each one slowing from 11.0s to 27.5s. The GPU is already saturated
    by one generation, so overlapping them only adds contention.
    """

    def __init__(self, quantize):
        self.quantize = quantize
        self.edit_engine = EditEngine()
        self.progress = Progress()
        self.jobs = queue.Queue()
        self.ready = threading.Event()
        self.load_error = None
        self.model = None
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self.model = load_model(self.quantize, self.progress)
        except Exception as error:
            self.load_error = error
        finally:
            self.ready.set()
        while self.load_error is None:
            self._serve_one(self.jobs.get())

    def _serve_one(self, job):
        if self.progress.consume_cancel():
            job.error = Cancelled("stopped before this image started")
            job.done.set()
            return
        self.progress.begin_job(job.label)
        try:
            if job.kind == "edit":
                self._serve_edit(job)
            else:
                self._serve_generate(job)
        except Exception as error:
            job.error = error
        finally:
            self.progress.clear_cancel()
            self.progress.finish()
            self._release_buffers()
            job.done.set()

    def _serve_generate(self, job):
        # Only one engine fits in memory at a time. See EditEngine.
        self.edit_engine.stop()
        self._ensure_model()
        self._ensure_encoder(job.request)
        self.progress.set_step(0, job.request["num_inference_steps"])
        job.image = self.model.generate_image(**job.request).image
        job.seed = job.request["seed"]

    def _serve_edit(self, job):
        """Hand the job to the edit child, with the GPU to itself.

        The edit engine loads the full Qwen3-VL including the vision tower and
        measured 38.7 GiB allocated on MPS. Holding the mflux model as well
        would not fit on a 64 GB machine, so it is dropped first and rebuilt
        lazily on the next generation. That rebuild measured 3.8s.
        """
        self._drop_model()
        job.image, job.seed = self.edit_engine.submit(job.request, self.progress)

    def _ensure_model(self):
        if self.model is None:
            self.model = load_model(self.quantize, self.progress)

    def _drop_model(self):
        self.model = None
        self._release_buffers()

    def _ensure_encoder(self, request):
        """Put the text encoder back when this request actually needs it.

        MemorySaver drops the encoder before every denoising loop, so after the
        first generation it is gone. A prompt whose embeddings are already in
        model.prompt_cache does not need it. Anything else does, and rebuilding
        the model is the only way back.

        Measured at 1.0s against 40s for the generation itself. A batch reuses
        one prompt, so it pays nothing; changing the prompt costs that second.
        """
        if self.model.text_encoder is not None:
            return
        needed = [request["prompt"]]
        # mflux encodes the negative prompt only when true CFG is on
        if request.get("negative_prompt") and request.get("guidance", 1.0) > 1.0:
            needed.append(request["negative_prompt"])
        if all(text in self.model.prompt_cache for text in needed):
            return
        self._drop_model()
        self.model = load_model(self.quantize, self.progress)

    @staticmethod
    def _release_buffers():
        """Hand MLX's reuse pool back after each generation.

        MLX keeps freed tensor buffers around to reuse. A CLI run exits and the
        OS reclaims them; a resident server just holds them. Measured at 1024:

            without this   cache 22.42 GB held between generations
            with this      cache  0.00 GB

        Nothing accumulates either way, so this is not a leak. It is headroom
        given back between generations.
        """
        import mlx.core as mx

        gc.collect()
        mx.clear_cache()

    def submit(self, kind, request, label=""):
        """Called from a request thread. Blocks until the worker answers."""
        job = Job(kind, request, label)
        self.jobs.put(job)
        job.done.wait()
        if job.error:
            raise job.error
        return job.image, job.seed


class Qwen21Handler(BaseHTTPRequestHandler):
    """Serves the page. All model work goes through the worker."""

    worker = None
    precision = "bf16"
    references = References()

    def log_message(self, *args):
        """Silence the access log. Prompts live in POST bodies, and none of this
        is wanted on disk or on the terminal."""

    def _send(self, body, status=200, content_type="text/html; charset=utf-8"):
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/progress":
            self._send(progress_fragment(self.worker.progress.snapshot()))
            return
        if self.path != "/":
            self._send("not found", status=404, content_type="text/plain")
            return
        self._send(render_page(self.precision))

    def do_POST(self):
        if self.path == "/cancel":
            self.worker.progress.cancel()
            self._send("", status=204, content_type="text/plain")
            return
        if self.path != "/generate":
            self._send("not found", status=404, content_type="text/plain")
            return
        self._send(self._handle_generate())

    def _handle_generate(self):
        """Both modes, one path. Only the request builder and the engine differ;
        batching, cancel and the reference token behave the same for both."""
        form = read_form(self)
        kind = "edit" if form.get("mode") == "edit" else "generate"
        try:
            references, token = load_references(form, self.references)
            total, index = build_position(form)
            if token and not references:
                return error_fragment("The reference image expired. Pick it again.")
            if kind == "edit":
                request = build_edit_request(form, references)
            else:
                request = build_params(form, references)
        except ValueError as error:
            return error_fragment(f"Bad form value: {error}")
        except OSError as error:
            return error_fragment(f"Could not read that reference image: {error}")
        if index == 1:
            # A fresh submit, so drop a cancel left over from an earlier batch.
            self.worker.progress.clear_cancel()
        if not request["prompt"]:
            what = "An edit instruction" if kind == "edit" else "A prompt"
            return error_fragment(f"{what} is required.")
        return self._run(form, kind, request, total, index, token)

    def _run(self, form, kind, request, total, index, token):
        started = time.time()
        label = f"{index} of {total}" if total > 1 else ""
        try:
            image, seed = self.worker.submit(kind, request, label)
        except Exception as error:
            # Either way the batch ends here, so the reference can go.
            if token:
                self.references.drop(token)
            if isinstance(error, Cancelled):
                return cancelled_fragment(error)
            return error_fragment(f"{type(error).__name__}: {error}")
        steps = request["steps"] if kind == "edit" else request["num_inference_steps"]
        item = item_fragment(
            image, seed, label or "1 image", steps, started, request["prompt"], kind
        )
        chain = build_chain(next_values(form, kind, request, seed), total, index, token)
        if not chain and token:
            self.references.drop(token)  # batch over; let the reference go
        return item + chain


POLLER = (
    '<div hx-get="/progress" hx-trigger="load delay:800ms"'
    ' hx-target="#progress" hx-swap="innerHTML"></div>'
)


def progress_fragment(state):
    """What the page polls while a generation runs.

    Every response carries the next poller, so the loop clocks itself. It never
    stops itself: the page clears #progress when the work ends, which removes
    the poller. Letting the server end the loop does not work, because there are
    two windows where nothing is running but more is coming, the gap between two
    images of a batch and the moment between the click and the worker picking
    the job up. Both used to kill the poller for the rest of the run.
    """
    if not state["running"]:
        return POLLER
    step, total = state["step"], state["total"]
    percent = round(100 * step / total) if total else 0
    caption = "preparing" if state["stage"] == "preparing" else f"step {step} of {total}"
    if state["label"]:
        caption += f", image {state['label']}"
    if state["cancel_requested"]:
        caption = "stopping at the end of this step"
    return (
        f'<div class="bar"><div style="width:{percent}%"></div></div>'
        f'<div class="hint">{caption}</div>{POLLER}'
    )


def load_model(quantize, progress=None):
    """Build the model and register mflux's MemorySaver.

    MemorySaver drops the 17.5 GB Qwen3-VL text encoder before the denoising
    loop. The encoder is dead weight once the prompt is encoded, and carrying it
    through 40 steps is what made this server peak far above the CLI. The CLI
    registers this through CallbackManager; the first version of this server
    registered nothing. Measured at 1024, four generations each:

        without   peak 45.01 GB   active 30.39 GB   cache 22.42 GB
        with      peak 30.68 GB   active 15.25 GB   cache  0.00 GB

    30.68 GB is exactly what the CLI reports for the same image.

    QwenImage21 defaults model_config to ModelConfig.qwen_image_21(), which is
    the only config this server serves, so quantize is the one thing to pass.

    ProgressCallback is registered here for the same reason MemorySaver is:
    CallbackRegistry.register appends and offers no way to remove, so a
    per-generation registration would stack one callback per image. Registering
    at build time keeps it at exactly one, and _ensure_encoder rebuilds through
    this function so it survives a prompt change.
    """
    from mflux.callbacks.instances.memory_saver import MemorySaver
    from mflux.models.qwen21.variants.txt2img.qwen_image_21 import QwenImage21

    model = QwenImage21(quantize=quantize)
    model.callbacks.register(
        MemorySaver(model=model, keep_transformer=True, cache_limit_bytes=None, num_seeds=1)
    )
    if progress is not None:
        model.callbacks.register(ProgressCallback(progress))
    return model


def main():
    parser = argparse.ArgumentParser(
        description="Serve Qwen-Image-2.1 on a local web page. Nothing is logged or saved."
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="port (default 8765)")
    parser.add_argument(
        "-q", "--quantize", type=int, choices=[3, 4, 5, 6, 8],
        help="quantize the weights; omit for bf16, which is this repo's default",
    )
    args = parser.parse_args()

    # Bind before loading. The weights take a minute, and discovering a busy port
    # after that minute is a waste. serve_forever comes later, so anything that
    # connects during the load just waits in the listen backlog.
    try:
        server = ThreadingHTTPServer((args.host, args.port), Qwen21Handler)
    except OSError as error:
        sys.exit(f"Cannot bind {args.host}:{args.port} ({error}). Pass --port for a free one.")

    Qwen21Handler.precision = f"int{args.quantize}" if args.quantize else "bf16"
    print(f"Loading Qwen-Image-2.1 ({Qwen21Handler.precision}).", flush=True)
    print("First run downloads about 33 GB. Later runs read the HuggingFace cache.", flush=True)
    worker = GenerationWorker(args.quantize)
    worker.ready.wait()
    if worker.load_error:
        sys.exit(f"Could not load the model: {worker.load_error}")
    Qwen21Handler.worker = worker

    print(f"\nReady on http://{args.host}:{args.port}", flush=True)
    print("Nothing is written to disk. Ctrl-C to stop.\n", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        worker.edit_engine.stop()  # the child does not share our signal handling
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
