// Both explorers read the same local electrs tip. Keep the UI usable during initial sync.
(() => {
  const notice = document.createElement('aside');
  notice.setAttribute('role', 'status');
  notice.style.cssText = 'position:sticky;top:0;z-index:10000;padding:8px 16px;background:#293a49;color:white;font:14px/1.4 sans-serif';
  notice.textContent = 'Waiting for the local mainnet index. On a new node, indexing starts after Bitcoin Core finishes its initial sync. Open Node status to see progress.';
  notice.hidden = true;
  document.body.prepend(notice);
  async function refresh() {
    try {
      const reply = await fetch('/api/blocks/tip/height', {cache: 'no-store', signal: AbortSignal.timeout(5000)});
      notice.hidden = reply.ok && /^\d+$/.test((await reply.text()).trim());
    } catch {
      notice.hidden = false;
    }
  }
  refresh();
  window.setInterval(refresh, 15000);
})();
