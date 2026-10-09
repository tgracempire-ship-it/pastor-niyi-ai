window.createPastorChatTimeout = function createPastorChatTimeout(milliseconds) {
  if (typeof AbortController === 'undefined') return { signal: undefined, clear() {} };
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), milliseconds);
  return { signal: controller.signal, clear: () => window.clearTimeout(timer) };
};

window.readPastorChatStream = async function readPastorChatStream(response, onEvent) {
  if (!response.body || typeof response.body.getReader !== 'function') {
    throw new Error('Your browser cannot display a live reply. Please reload or use an updated browser.');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let eventName = 'message';
  let dataLines = [];

  function dispatch() {
    if (dataLines.length) onEvent(eventName, dataLines.join('\n'));
    eventName = 'message';
    dataLines = [];
  }

  function consumeLine(line) {
    if (line.endsWith('\r')) line = line.slice(0, -1);
    if (!line) { dispatch(); return; }
    if (line.startsWith(':')) return;
    const colon = line.indexOf(':');
    const field = colon < 0 ? line : line.slice(0, colon);
    const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '');
    if (field === 'event') eventName = value;
    else if (field === 'data') dataLines.push(value);
  }

  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      let newline;
      while ((newline = buffer.indexOf('\n')) >= 0) {
        consumeLine(buffer.slice(0, newline));
        buffer = buffer.slice(newline + 1);
      }
      if (done) break;
    }
    if (buffer) consumeLine(buffer);
    dispatch();
  } catch (error) {
    await reader.cancel().catch(() => {});
    throw error;
  }
};

window.readChatEvent = function readChatEvent(data) {
  try { return JSON.parse(data); } catch { return {}; }
};

window.loadPastorChatHistory = function loadPastorChatHistory(key) {
  try {
    const saved = JSON.parse(window.localStorage.getItem(key) || '[]');
    if (!Array.isArray(saved)) return [];
    return saved
      .filter((turn) => turn && ['user', 'assistant'].includes(turn.role) && typeof turn.content === 'string')
      .slice(-12)
      .map((turn) => ({
        role: turn.role,
        content: turn.content.slice(0, 12000),
        ...(turn.role === 'assistant' && Array.isArray(turn.sources) ? {
          sources: turn.sources.slice(0, 8).filter((source) => source && typeof source === 'object').map((source) => ({
            title: String(source.title || 'Sermon').slice(0, 300),
            time: String(source.time || '').slice(0, 80),
            telegram_links: Array.isArray(source.telegram_links) ? source.telegram_links.slice(0, 5)
              .filter((link) => link && typeof link.url === 'string')
              .map((link) => ({ url: link.url.slice(0, 500), label: String(link.label || 'Listen on Telegram').slice(0, 80) })) : [],
          })),
        } : {}),
      }));
  } catch {
    return [];
  }
};

window.savePastorChatHistory = function savePastorChatHistory(key, history) {
  try { window.localStorage.setItem(key, JSON.stringify(history.slice(-12))); }
  catch { /* Keep the active conversation working if browser storage is unavailable. */ }
};
