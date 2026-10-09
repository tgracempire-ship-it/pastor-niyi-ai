const form = document.querySelector('#chat-form');
const input = document.querySelector('#message');
const send = document.querySelector('#send');
const conversation = document.querySelector('#conversation');
const welcome = document.querySelector('#welcome');
const errorBox = document.querySelector('#error');

const historyKey = 'pastor-niyi-ai:main:v1';
let history = window.loadPastorChatHistory(historyKey);
let busy = false;

function cleanMarkdown(text) {
  return String(text || '')
    .replace(/\r\n?/g, '\n')
    .replace(/\\([\\`*_{}\[\]()#+\-.!|>])/g, '$1')
    .replace(/^```[\w-]*\s*$/gm, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    // Some model replies place headings and list markers on the end of a paragraph.
    .replace(/\s+(\*\*[^*\n]{2,100}:\*\*)/g, '\n\n$1\n')
    .replace(/\s+([*+-])\s+(?=\*\*|[A-Z0-9])/g, '\n$1 ')
    .replace(/\s+(\d{1,2}[.)])\s+(?=\*\*|[A-Z0-9])/g, '\n$1 ')
    .trim();
}

function appendInlineText(parent, value) {
  const pattern = /(\*\*[^*]+\*\*|__[^_]+__|\*[^*\n]+\*|_[^_\n]+_)/g;
  let cursor = 0;
  let match;

  while ((match = pattern.exec(value))) {
    if (match.index > cursor) {
      parent.append(document.createTextNode(value.slice(cursor, match.index)));
    }

    const token = match[0];
    const isStrong = token.startsWith('**') || token.startsWith('__');
    const tag = document.createElement(isStrong ? 'strong' : 'em');
    tag.textContent = token.slice(isStrong ? 2 : 1, isStrong ? -2 : -1);
    parent.append(tag);
    cursor = pattern.lastIndex;
  }

  if (cursor < value.length) {
    parent.append(document.createTextNode(value.slice(cursor)));
  }
}

function renderAnswer(container, answer) {
  container.replaceChildren();
  const text = cleanMarkdown(answer);
  const lines = text.split('\n');
  let paragraph = [];
  let list = null;
  let listType = '';

  function flushParagraph() {
    if (!paragraph.length) return;
    const element = document.createElement('p');
    appendInlineText(element, paragraph.join(' '));
    container.append(element);
    paragraph = [];
  }

  function closeList() {
    list = null;
    listType = '';
  }

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      closeList();
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    const boldHeading = line.match(/^\*\*(.+?)\*\*:?$/);
    const bullet = line.match(/^[-*+]\s+(.+)$/);
    const numbered = line.match(/^\d{1,2}[.)]\s+(.+)$/);
    const quote = line.match(/^>\s?(.+)$/);

    if (heading || (boldHeading && (boldHeading[1].endsWith(':') || boldHeading[1].length < 72))) {
      flushParagraph();
      closeList();
      const element = document.createElement('h3');
      appendInlineText(element, heading ? heading[2] : boldHeading[1].replace(/:$/, ''));
      container.append(element);
      continue;
    }

    if (bullet || numbered) {
      flushParagraph();
      const type = numbered ? 'ol' : 'ul';
      if (!list || listType !== type) {
        closeList();
        list = document.createElement(type);
        listType = type;
        container.append(list);
      }
      const item = document.createElement('li');
      appendInlineText(item, (bullet || numbered)[1]);
      list.append(item);
      continue;
    }

    if (quote) {
      flushParagraph();
      closeList();
      const element = document.createElement('blockquote');
      appendInlineText(element, quote[1]);
      container.append(element);
      continue;
    }

    closeList();
    paragraph.push(line);
  }

  flushParagraph();
}

function addMessage(role, text, typing = false) {
  const node = document.createElement('article');
  node.className = `message ${role}`;

  if (role === 'assistant') {
    const avatar = document.createElement('img');
    avatar.className = 'message-avatar';
    avatar.src = '/assets/pastor_niyi.webp';
    avatar.alt = 'Pastor Niyi';

    const bubble = document.createElement('div');
    bubble.className = `message-bubble assistant-bubble${typing ? ' typing' : ''}`;
    bubble.setAttribute('aria-live', typing ? 'off' : 'polite');
    if (typing) bubble.textContent = text;
    else renderAnswer(bubble, text);

    node.append(avatar, bubble);
  } else {
    const bubble = document.createElement('div');
    bubble.className = 'message-bubble user-bubble';
    bubble.textContent = text;
    node.append(bubble);
  }

  conversation.append(node);
  node.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  return node;
}
function addSources(bubble, sources) {
  if (!sources.length) return;

  const box = document.createElement('div');
  box.className = 'sources';
  const label = document.createElement('strong');
  label.textContent = 'Sermon references';
  box.append(label);

  for (const source of sources) {
    const row = document.createElement('div');
    row.className = 'source';
    const title = document.createElement('span');
    title.textContent = source.title;
    row.append(title);
    if (source.time) row.append(document.createTextNode(` · ${source.time}`));

    for (const link of source.telegram_links || []) {
      try {
        const url = new URL(link.url);
        if (url.protocol !== 'https:' || url.hostname !== 't.me') continue;
        const anchor = document.createElement('a');
        anchor.className = 'listen-link';
        anchor.href = url.href;
        anchor.target = '_blank';
        anchor.rel = 'noopener noreferrer';
        anchor.textContent = link.label || 'Listen on Telegram';
        row.append(anchor);
      } catch {
        // Ignore malformed source links while keeping the sermon reference visible.
      }
    }

    box.append(row);
  }

  bubble.append(box);
}

async function ask(text, retrying = false) {
  if (busy || !text.trim()) return;

  busy = true;
  welcome.hidden = true;
  errorBox.hidden = true;
  input.value = '';
  input.style.height = 'auto';
  if (!retrying) addMessage('user', text);
  const pending = addMessage('assistant', "Searching Pastor Niyi's messages...", true);
  const bubble = pending.querySelector('.message-bubble');
  send.disabled = true;
  let answerText = '';
  let sources = [];
  let streamError = null;
  const timeout = window.createPastorChatTimeout(120000);

  try {
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: history.map(({ role, content }) => ({ role, content })) }),
      signal: timeout.signal,
    });
    if (!response.ok) {
      const raw = await response.text();
      let data = {};
      try { data = raw ? JSON.parse(raw) : {}; } catch { /* Use the HTTP status fallback. */ }
      throw new Error(data.detail || `The server returned an error (HTTP ${response.status}). Please try again shortly.`);
    }

    await window.readPastorChatStream(response, (name, rawEvent) => {
      const event = window.readChatEvent(rawEvent);
      if (name === 'status' && !answerText) {
        bubble.classList.add('typing');
        bubble.textContent = event.message || 'Preparing a reply...';
      } else if (name === 'token' && event.text) {
        answerText += event.text;
        bubble.classList.remove('typing');
        bubble.classList.add('streaming');
        bubble.setAttribute('aria-live', 'off');
        renderAnswer(bubble, answerText);
        pending.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      } else if (name === 'sources') {
        sources = Array.isArray(event.sources) ? event.sources : [];
      } else if (name === 'error') {
        streamError = new Error(event.detail || 'The assistant could not finish the reply. Please try again.');
      }
    });
    if (streamError) throw streamError;
    if (!answerText.trim()) throw new Error('The assistant returned an empty response. Please try again.');

    bubble.classList.remove('typing', 'streaming');
    bubble.setAttribute('aria-live', 'polite');
    renderAnswer(bubble, answerText);
    addSources(bubble, sources);
    pending.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    history.push({ role: 'user', content: text }, { role: 'assistant', content: answerText, sources });
    history = history.slice(-12);
    window.savePastorChatHistory(historyKey, history);
  } catch (err) {
    if (answerText) {
      bubble.classList.remove('typing', 'streaming');
      bubble.setAttribute('aria-live', 'polite');
      renderAnswer(bubble, answerText);
      addSources(bubble, sources);
    } else {
      pending.remove();
    }
    const message = err.name === 'TimeoutError' || err.name === 'AbortError'
      ? 'That reply took too long. Please try again shortly.'
      : err.message;
    errorBox.replaceChildren(document.createTextNode(`${message} `));
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'retry-button';
    retry.textContent = 'Try again';
    retry.addEventListener('click', () => ask(text, true));
    errorBox.append(retry);
    errorBox.hidden = false;
  } finally {
    timeout.clear();
    busy = false;
    send.disabled = false;
    if (errorBox.hidden) input.focus();
    else errorBox.querySelector('.retry-button')?.focus();
  }
}
form.addEventListener('submit', (event) => {
  event.preventDefault();
  ask(input.value);
});

input.addEventListener('input', () => {
  input.style.height = 'auto';
  input.style.height = `${Math.min(input.scrollHeight, 140)}px`;
});

input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

document.querySelectorAll('.suggestion').forEach((button) => {
  button.addEventListener('click', () => ask(button.dataset.prompt));
});

if (history.length) {
  welcome.hidden = true;
  for (const turn of history) {
    const row = addMessage(turn.role, turn.content);
    if (turn.role === 'assistant' && turn.sources?.length) {
      addSources(row.querySelector('.message-bubble'), turn.sources);
    }
  }
}
