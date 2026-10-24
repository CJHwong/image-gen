// Follow shared server work, including API requests and work started in another tab.
export function screenAwake() {
  let wanted = false, sentinel = null, pending = null, closed = false;
  async function update() {
    if (closed || !wanted || document.visibilityState !== 'visible') {
      if (sentinel) { const old = sentinel; sentinel = null; await old.release().catch(() => {}); }
      return;
    }
    if (sentinel || pending || !navigator.wakeLock) return;
    pending = navigator.wakeLock.request('screen').then(async lock => {
      if (closed || !wanted || document.visibilityState !== 'visible') { await lock.release(); return; }
      sentinel = lock;
      lock.addEventListener('release', () => { if (sentinel === lock) sentinel = null; }, {once: true});
    }).catch(() => {}).finally(() => { pending = null; });
    await pending;
  }
  const visible = () => update();
  document.addEventListener('visibilitychange', visible);
  return {
    set(active) { const next = Boolean(active); if (next === wanted) return; wanted = next; update(); },
    close() { closed = true; document.removeEventListener('visibilitychange', visible); update(); },
  };
}
