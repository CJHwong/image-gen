// Workspace help owns its overlay and focus, independently of any media preview.
const IMAGE_GUIDE = [
  ['Generate, or Edit', 'Generate writes a picture from a prompt. Edit changes one you already have, and needs an image from the strip: click a frame, then Edit this.'],
  ['A Look', 'A chip adds one sentence after your words. Each model offers only the options its own test kept.'],
  ['Rewrite', 'It writes out the words you typed, and the words in the marked areas, at length. Each answer lands where it was written, and the Look is added after them. In a batch your words lead every image and each row adds to them, and the press writes a row from its own picture.'],
  ['Mark a region', "Fill the area you want changed. Do not circle it: the mark's own shape is the shape that comes back repainted."],
  ['What changes there', 'One row per marked colour says what changes in that area. Or pick the Mark a region template and leave the rows empty.'],
  ['The brush', 'Three widths, and a loupe follows the brush while you draw. The area you mark is the area that changes, so keep the mark close to what should change.'],
  ['The wait', 'An edit reads your prompt and images for about a minute before its first step. The line in the top bar counts that time.'],
  ['Run and Cancel', 'Run empties the form it sent. Cancel puts all of it back, the marked region included.'],
  ['The strip', 'Images stay in the strip. Download the ones you want before you clear it.'],
];

const VIDEO_GUIDE = [
  ['Generate, or Edit', 'Generate a video from a prompt, optional image keyframes, or an audio track. Edit requires explicitly choosing a clip and an adapter; viewing a gallery clip does not select it for editing.'],
  ['Prompt and templates', 'Describe the subject, action, setting and camera movement. Templates provide starting points; a Look adds to your words.'],
  ['Rewrite and enhancement', 'Rewrite is an explicit prompt-writing action. Generate also runs the model’s prompt enhancer automatically before rendering.'],
  ['References', 'Add a still as a keyframe or an audio track to guide the video. Remove a reference with its cross; this does not delete a gallery result.'],
  ['Duration and size', 'Choose the output shape, resolution and duration before generating. Larger or longer clips take more time and memory.'],
  ['Fast mode', 'LTX-2.5 offers Fast mode in Advanced. It uses float16 computation with the same weights for faster rendering; generated details may differ.'],
  ['Run and Cancel', 'Progress covers the whole render and reaches completion only when the clip is ready. Cancel stops the active operation.'],
  ['The gallery', 'Select one clip to preview. Its action buttons let you download, copy inputs, edit or remove it.'],
];

function videoGuide(capabilities) {
  const edit = capabilities.modes?.some(mode => mode.id === 'edit');
  return VIDEO_GUIDE.filter(([name]) => name !== 'Fast mode' || capabilities.fast_mode).map(([name, text]) => {
    if (!edit && name === 'Generate, or Edit') return ['Generate', 'Generate a video from a prompt, optional image keyframes, or an audio track.'];
    if (!edit && name === 'The gallery') return [name, 'Select one clip to preview. Use its action buttons to download, copy inputs or remove it.'];
    return [name, text];
  });
}

function voiceGuide(capabilities) {
  const params = capabilities.modes?.flatMap(mode => mode.params) || [];
  const drama = params.some(param => param.id === 'max_tokens');
  const edit = capabilities.modes?.some(mode => mode.id === 'edit');
  return [
    ['Generate a clip', 'Write the words you want spoken. Generate produces one continuous audio clip for the script.'],
    ['Templates and direction', drama
      ? 'Pick a delivery template or put cues such as [whispers] inside the script. Drama-3 does not use a separate voice description.'
      : 'For Design, choose a voice template or describe the voice. The script contains the words to speak; the voice description directs the delivery.'],
    ['Clone a voice', drama
      ? 'Add a clean reference recording and its exact transcript. Recordings longer than 15 seconds use the first 15 seconds; make the transcript match that excerpt.'
      : 'Add a clean reference recording of one speaker. AuK does not require a transcript for cloning. Remove the reference before recording another one.'],
    ['Preview and selection', 'Click the waveform to choose a playback position. Drag the end handles to select a range, then play that selection. Playback speed changes the preview only.'],
    ['Clip actions', (edit ? 'Download or edit the selected audio from the action bar. ' : 'Download the selected audio from the action bar. ') + 'The more menu includes Send to Video, Send to Clone and copying inputs.'],
    [drama ? 'Audio token limit' : 'Duration', drama
      ? 'Advanced sets a safety limit per internal script chunk. Higher values allow longer output but may prolong repetition; the default is 2048.'
      : 'Use automatic duration or set a target length in Advanced. A window that is too short can cut off words.'],
    ['Run and Cancel', 'The preview and gallery show generation progress. Cancel keeps completed clips; successful generation clears the submitted inputs.'],
    ['Shared status', 'UI and API runs share one model slot. Other tabs follow the current operation and lock controls while it runs.'],
  ];
}

export function closeGuide(restoreFocus = true) {
  const sheet = document.getElementById('guide-sheet');
  if (!sheet) return;
  sheet.remove();
  const toggle = document.getElementById('guide-toggle');
  toggle.setAttribute('aria-expanded', 'false');
  if (restoreFocus) toggle.focus();
}

export function syncGuide(workspace, backend) {
  const sheet = document.getElementById('guide-sheet');
  if (sheet && (sheet.dataset.workspace !== workspace || sheet.dataset.backend !== backend)) closeGuide(false);
}

export function openGuide(workspace, backend, capabilities = {}) {
  if (document.getElementById('guide-sheet')) return closeGuide();
  const sheet = document.createElement('div');
  sheet.className = 'sheet';
  sheet.id = 'guide-sheet';
  sheet.dataset.workspace = workspace;
  sheet.dataset.backend = backend;
  sheet.setAttribute('role', 'region');
  sheet.setAttribute('aria-label', 'How to use this studio');
  const list = document.createElement('dl');
  const entries = workspace === 'voice' ? voiceGuide(capabilities) : workspace === 'video' ? videoGuide(capabilities) : IMAGE_GUIDE;
  entries.forEach(([name, description]) => {
    const term = document.createElement('dt');
    const text = document.createElement('dd');
    term.textContent = name;
    text.textContent = description;
    list.append(term, text);
  });
  const api = document.createElement('p');
  api.className = 'guide-api';
  const spec = document.createElement('a');
  spec.href = '/api/docs';
  spec.target = '_blank';
  spec.rel = 'noreferrer';
  spec.textContent = 'OpenAPI spec';
  api.append(spec, document.createTextNode(' lists every JSON route. Start at /api/v1/studio.'));
  const close = document.createElement('button');
  close.type = 'button';
  close.className = 'icon-btn close';
  close.setAttribute('aria-label', 'Close');
  close.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-x"/></svg>';
  close.addEventListener('click', () => closeGuide());
  sheet.addEventListener('keydown', event => {
    if (event.key !== 'Escape') return;
    event.stopPropagation();
    closeGuide();
  });
  sheet.append(list, api, close);
  document.getElementById('workspace-guide-host').append(sheet);
  document.getElementById('guide-toggle').setAttribute('aria-expanded', 'true');
  close.focus();
}

document.dispatchEvent(new CustomEvent('studio-guide-ready', {
  detail: {open: openGuide, close: closeGuide, sync: syncGuide},
}));
