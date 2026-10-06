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
