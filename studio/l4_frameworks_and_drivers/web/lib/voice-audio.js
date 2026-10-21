export function splitScript(text) {
  return text.split(/(?<=[。！？!?；;])\s*|(?<=\.)\s+|\n+/u).map(part => part.trim()).filter(Boolean);
}

export function waveBytes(samples, sampleRate) {
  const bytes = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(bytes);
  const word = (offset, text) => Array.from(text).forEach((letter, index) => view.setUint8(offset + index, letter.charCodeAt(0)));
  word(0, 'RIFF');
  view.setUint32(4, 36 + samples.length * 2, true);
  word(8, 'WAVE');
  word(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  word(36, 'data');
  view.setUint32(40, samples.length * 2, true);
  samples.forEach((sample, index) => view.setInt16(44 + index * 2, Math.max(-1, Math.min(1, sample)) * 32767, true));
  return new Blob([bytes], {type: 'audio/wav'});
}

const decodedAudio = new WeakMap();

export function decodeAudio(blob, sampleRate = 24000) {
  let rates = decodedAudio.get(blob);
  if (!rates) { rates = new Map(); decodedAudio.set(blob, rates); }
  if (!rates.has(sampleRate)) {
    const pending = decodeSamples(blob, sampleRate).catch(error => {
      rates.delete(sampleRate);
      throw error;
    });
    rates.set(sampleRate, pending);
  }
  return rates.get(sampleRate);
}

async function decodeSamples(blob, sampleRate) {
  const context = new AudioContext();
  try {
    const bytes = await blob.arrayBuffer();
    const header = new DataView(bytes);
    if (!sampleRate) sampleRate = bytes.byteLength >= 28 && header.getUint32(0) === 0x52494646 && header.getUint32(8) === 0x57415645 ? header.getUint32(24, true) : context.sampleRate;
    const decoded = await context.decodeAudioData(bytes);
    const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * sampleRate), sampleRate);
    const source = offline.createBufferSource();
    source.buffer = decoded;
    source.connect(offline.destination);
    source.start();
    const buffer = await offline.startRendering();
    return {samples: buffer.getChannelData(0), sampleRate, duration: buffer.duration, sourceDuration: decoded.duration};
  } finally {
    await context.close();
  }
}

async function compatiblePcmReference(blob, sampleRate, maxSeconds) {
  const bytes = await blob.arrayBuffer();
  const view = new DataView(bytes);
  if (bytes.byteLength < 12 || view.getUint32(0) !== 0x52494646 || view.getUint32(8) !== 0x57415645
      || view.getUint32(4, true) + 8 !== bytes.byteLength) return null;
  let format, data;
  for (let offset = 12; offset + 8 <= bytes.byteLength;) {
    const kind = view.getUint32(offset);
    const size = view.getUint32(offset + 4, true);
    const start = offset + 8;
    if (start + size > bytes.byteLength) return null;
    if (kind === 0x666d7420) {
      if (format !== undefined || size < 16) return null;
      format = start;
    }
    if (kind === 0x64617461) {
      if (data) return null;
      data = {start, size};
    }
    offset = start + size + (size % 2);
  }
  if (format === undefined || !data || view.getUint16(format, true) !== 1
      || view.getUint16(format + 2, true) !== 1 || view.getUint32(format + 4, true) !== sampleRate
      || view.getUint32(format + 8, true) !== sampleRate * 2
      || view.getUint16(format + 12, true) !== 2 || view.getUint16(format + 14, true) !== 16
      || !data.size || data.size % 2) return null;
  const frames = Math.min(data.size / 2, Math.floor(maxSeconds * sampleRate));
  if (data.size / 2 / sampleRate < 0.2) throw new Error('The reference must contain at least 0.2 seconds of audio.');
  if (frames === data.size / 2) return {blob, duration: frames / sampleRate, trimmed: false};
  const header = await waveBytes(new Float32Array(0), sampleRate).arrayBuffer();
  const output = new DataView(header);
  output.setUint32(4, 36 + frames * 2, true);
  output.setUint32(40, frames * 2, true);
  return {blob: new Blob([header, new Uint8Array(bytes, data.start, frames * 2)], {type: 'audio/wav'}),
    duration: frames / sampleRate, trimmed: true};
}

export async function normalizeReference(blob, sampleRate = 24000, maxSeconds = Infinity) {
  const compatible = await compatiblePcmReference(blob, sampleRate, maxSeconds);
  if (compatible) return compatible;
  const decoded = await decodeAudio(blob, sampleRate);
  if (decoded.duration < 0.2) throw new Error('The reference must contain at least 0.2 seconds of audio.');
  const samples = decoded.samples.subarray(0, Math.min(decoded.samples.length, Math.floor(maxSeconds * decoded.sampleRate)));
  return {blob: waveBytes(samples, decoded.sampleRate), duration: samples.length / decoded.sampleRate,
    trimmed: samples.length < decoded.samples.length};
}

export function blobBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = () => reject(new Error('The audio could not be read.'));
    reader.readAsDataURL(blob);
  });
}

export function audioPeaks(samples, count = 80) {
  const stride = Math.max(1, Math.floor(samples.length / count));
  return Array.from({length: count}, (_, index) => {
    let peak = 0;
    for (let offset = index * stride; offset < Math.min(samples.length, (index + 1) * stride); offset++) {
      peak = Math.max(peak, Math.abs(samples[offset]));
    }
    return peak;
  });
}

export const TRACK_GAP = 0.2;

export async function joinAudio(blobs, gap = TRACK_GAP) {
  const chunks = [];
  const native = await Promise.all(blobs.map(blob => decodeAudio(blob, null)));
  const sampleRate = Math.max(24000, ...native.map(audio => audio.sampleRate));
  let length = 0;
  for (const blob of blobs) {
    const {samples} = await decodeAudio(blob, sampleRate);
    if (chunks.length) chunks.push(new Float32Array(Math.round(sampleRate * gap)));
    chunks.push(samples);
  }
  chunks.forEach(chunk => { length += chunk.length; });
  const joined = new Float32Array(length);
  let offset = 0;
  chunks.forEach(chunk => { joined.set(chunk, offset); offset += chunk.length; });
  return waveBytes(joined, sampleRate);
}

export function downloadAudio(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
