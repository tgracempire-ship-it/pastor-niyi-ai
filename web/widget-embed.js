(() => {
  const script = document.currentScript;
  if (!script || document.querySelector('[data-pastor-niyi-ai-widget]')) return;

  const base = new URL(script.src, window.location.href);
  const position = script.dataset.position === 'bottom-left' ? 'bottom-left' : 'bottom-right';
  const root = document.createElement('div');
  root.dataset.pastorNiyiAiWidget = '';
  const shadow = root.attachShadow({ mode: 'open' });
  const style = document.createElement('style');
  style.textContent = `
    :host{all:initial;position:fixed;z-index:2147483000;right:22px;bottom:22px;font-family:system-ui,sans-serif;color:#243a32}
    :host([data-position="bottom-left"]){right:auto;left:22px}
    *{box-sizing:border-box}
    .launcher{width:58px;height:58px;display:grid;place-items:center;border:0;border-radius:20px;background:#1e463a;color:#f2dfad;box-shadow:0 8px 26px #18362b42;cursor:pointer;transition:transform .18s,background .18s,box-shadow .18s}
    .launcher:hover{transform:translateY(-2px);background:#285744;box-shadow:0 11px 30px #18362b4d}
    .launcher:focus-visible,.close:focus-visible{outline:3px solid #ad8b4d;outline-offset:3px}
    .launcher svg{width:25px;height:25px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
    .panel{position:absolute;right:0;bottom:74px;width:min(390px,calc(100vw - 32px));height:min(640px,calc(100dvh - 116px));min-height:390px;overflow:hidden;border:1px solid #dfdfd5;border-radius:19px;background:#f8f7f2;box-shadow:0 18px 60px #20372b36;transform-origin:bottom right;animation:open .2s cubic-bezier(.2,.8,.2,1)}
    :host([data-position="bottom-left"]) .panel{right:auto;left:0;transform-origin:bottom left}
    .panel[hidden]{display:none}
    iframe{display:block;width:100%;height:100%;border:0;background:#f8f7f2}
    @keyframes open{from{opacity:0;transform:translateY(8px) scale(.985)}to{opacity:1;transform:translateY(0) scale(1)}}
    @media(max-width:520px){:host,:host([data-position="bottom-left"]){inset:0}.launcher{position:absolute;right:16px;bottom:16px;width:56px;height:56px;border-radius:19px}:host([data-position="bottom-left"]) .launcher{right:auto;left:16px}.panel,:host([data-position="bottom-left"]) .panel{position:absolute;inset:0;width:100%;height:100%;min-height:0;border:0;border-radius:0;box-shadow:none;transform-origin:center}}
    @media(prefers-reduced-motion:reduce){.launcher{transition:none}.panel{animation:none}}
  `;
  const button = document.createElement('button');
  button.className = 'launcher';
  button.type = 'button';
  button.setAttribute('aria-label', 'Open Pastor Niyi AI chat');
  button.setAttribute('aria-expanded', 'false');
  button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11.2a7.8 7.8 0 0 1-8.1 7.8 8.8 8.8 0 0 1-3.6-.8L4 20l1.3-3.8A7.4 7.4 0 0 1 4 11.8 7.9 7.9 0 0 1 12 4a7.8 7.8 0 0 1 8 7.2Z"/><path d="M8.5 11.8h7M12 8.3v7"/></svg>';

  const panel = document.createElement('section');
  panel.className = 'panel';
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-label', 'Pastor Niyi AI chat');
  panel.hidden = true;
  const frame = document.createElement('iframe');
  frame.title = 'Pastor Niyi AI chat';
  frame.loading = 'lazy';
  frame.referrerPolicy = 'strict-origin-when-cross-origin';
  frame.src = new URL('/widget', base.origin).href;
  panel.append(frame);
  shadow.append(style, button, panel);
  document.body.append(root);

  function setOpen(open) {
    panel.hidden = !open;
    button.setAttribute('aria-expanded', String(open));
    button.setAttribute('aria-label', open ? 'Close Pastor Niyi AI chat' : 'Open Pastor Niyi AI chat');
    if (open && frame.contentWindow) frame.contentWindow.postMessage({ type: 'pastor-niyi-ai:focus' }, base.origin);
    if (!open) button.focus({ preventScroll: true });
  }
  frame.addEventListener('load', () => {
    if (!panel.hidden && frame.contentWindow) frame.contentWindow.postMessage({ type: 'pastor-niyi-ai:focus' }, base.origin);
  });
  root.dataset.position = position;
  button.addEventListener('click', () => setOpen(panel.hidden));
  window.addEventListener('message', (event) => {
    if (event.origin === base.origin && event.source === frame.contentWindow && event.data?.type === 'pastor-niyi-ai:close') setOpen(false);
  });
  window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !panel.hidden) setOpen(false);
  });
})();
