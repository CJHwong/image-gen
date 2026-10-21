function slug(text) {
  return String(text || '').normalize('NFKD').replace(/\p{M}/gu, '')
    .toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '-').replace(/^-+|-+$/g, '')
    .slice(0, 60).replace(/-+$/g, '') || 'untitled';
}

function stamp(at) {
  const when = new Date(at ?? NaN);
  if (!Number.isFinite(when.getTime())) return 'undated';
  const two = value => String(value).padStart(2, '0');
  return when.getFullYear() + two(when.getMonth() + 1) + two(when.getDate())
    + '-' + two(when.getHours()) + two(when.getMinutes()) + two(when.getSeconds())
    + String(when.getMilliseconds()).padStart(3, '0');
}

function identity(id) {
  if (!id) return '';
  let hash = 2166136261;
  for (const character of String(id)) hash = Math.imul(hash ^ character.codePointAt(0), 16777619);
  return '-' + (hash >>> 0).toString(36);
}

export function mediaExtension(type, fallback) {
  const extensions = {
    'image/png': 'png', 'image/jpeg': 'jpg', 'image/webp': 'webp',
    'video/mp4': 'mp4', 'video/webm': 'webm',
    'audio/wav': 'wav', 'audio/wave': 'wav', 'audio/x-wav': 'wav',
    'audio/mpeg': 'mp3', 'audio/mp3': 'mp3', 'audio/mp4': 'm4a',
    'audio/aac': 'aac', 'audio/flac': 'flac', 'audio/ogg': 'ogg', 'audio/webm': 'webm',
  };
  return extensions[String(type || '').split(';')[0].trim().toLowerCase()] || fallback;
}

export function mediaDownloadName({kind, text, at, id, extension, start, end}) {
  const media = ['image', 'video', 'audio'].includes(kind) ? kind : 'file';
  const format = String(extension || '').toLowerCase().replace(/[^a-z0-9]/g, '').slice(0, 8) || 'bin';
  const seconds = value => String(Math.round(value * 1000) / 1000);
  const selection = Number.isFinite(start) && Number.isFinite(end) && start >= 0 && end > start
    ? '-' + seconds(start) + '-' + seconds(end) + 's' : '';
  return media + '-' + slug(text) + selection + '-' + stamp(at) + identity(id) + '.' + format;
}
