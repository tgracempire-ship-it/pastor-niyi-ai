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
        const isAllowed = url.protocol === 'https:' && (url.hostname === 't.me' || url.hostname.endsWith('youtube.com') || url.hostname === 'youtu.be');
        if (!isAllowed) continue;
        const anchor = document.createElement('a');
        const isYT = url.hostname.includes('youtu');
        anchor.className = isYT ? 'listen-link youtube-link' : 'listen-link';
        anchor.href = url.href;
        anchor.target = '_blank';
        anchor.rel = 'noopener noreferrer';
        anchor.textContent = link.label || (url.hostname.includes('youtu') ? 'Watch on YouTube' : 'Listen on Telegram');
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
  const pending = addMessage('assistant', 'Thinking...', true);
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


/* ==========================================================================
   SUGGESTION BOX & OPTION B USER ACCOUNTS
   ========================================================================== */

// --- Suggestion Box Logic ---
const feedbackModal = document.getElementById('feedback-modal');
const openFeedbackBtn = document.getElementById('open-feedback-btn');
const closeFeedbackBtn = document.getElementById('close-feedback-btn');
const cancelFeedbackBtn = document.getElementById('cancel-feedback-btn');
const feedbackForm = document.getElementById('feedback-form');
const feedbackContent = document.getElementById('feedback-content');
const feedbackContact = document.getElementById('feedback-contact');
const charCount = document.getElementById('char-count');
const sendFeedbackBtn = document.getElementById('send-feedback-btn');
const feedbackError = document.getElementById('feedback-form-error');
const feedbackSuccess = document.getElementById('feedback-success-state');
const feedbackDoneBtn = document.getElementById('feedback-done-btn');

function openFeedbackModal() {
  if (!feedbackModal) return;
  feedbackModal.hidden = false;
  if (feedbackForm) feedbackForm.hidden = false;
  if (feedbackSuccess) feedbackSuccess.hidden = true;
  if (feedbackError) feedbackError.hidden = true;
  if (feedbackContent) {
    feedbackContent.value = '';
    charCount.textContent = '0';
  }
  // If user is logged in, optionally pre-populate contact with their name/email
  const currentUser = getCurrentUser();
  if (currentUser && feedbackContact && !feedbackContact.value) {
    feedbackContact.value = currentUser.name || currentUser.email || '';
  }
  setTimeout(() => feedbackContent?.focus(), 150);
}

function closeFeedbackModal() {
  if (feedbackModal) feedbackModal.hidden = true;
}

openFeedbackBtn?.addEventListener('click', openFeedbackModal);
closeFeedbackBtn?.addEventListener('click', closeFeedbackModal);
cancelFeedbackBtn?.addEventListener('click', closeFeedbackModal);
feedbackDoneBtn?.addEventListener('click', closeFeedbackModal);

feedbackModal?.addEventListener('click', (e) => {
  if (e.target === feedbackModal) closeFeedbackModal();
});

// Category pills toggle
document.querySelectorAll('.cat-chip').forEach((chip) => {
  chip.addEventListener('click', () => {
    document.querySelectorAll('.cat-chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    const radio = chip.querySelector('input[type="radio"]');
    if (radio) radio.checked = true;
  });
});

feedbackContent?.addEventListener('input', () => {
  if (charCount) {
    charCount.textContent = feedbackContent.value.length;
  }
});

window.submitFeedbackForm = async function() {
  const content = feedbackContent?.value?.trim();
  if (!content) {
    if (feedbackError) {
      feedbackError.textContent = 'Please enter your suggestion or feedback before sending.';
      feedbackError.hidden = false;
    }
    return;
  }

  const selectedCat = document.querySelector('input[name="feedback-category"]:checked')?.value || 'suggestion';
  const contact = feedbackContact?.value?.trim() || '';

  // Get last user question from history for pastoral context
  let contextQuery = '';
  if (history && history.length) {
    const lastUserTurn = [...history].reverse().find(t => t.role === 'user');
    if (lastUserTurn) contextQuery = lastUserTurn.content.slice(0, 300);
  }

  if (sendFeedbackBtn) {
    sendFeedbackBtn.disabled = true;
    const spinner = sendFeedbackBtn.querySelector('.sheet-spinner');
    if (spinner) spinner.hidden = false;
  }
  if (feedbackError) feedbackError.hidden = true;

  try {
    const headers = { 'Content-Type': 'application/json' };
    const userToken = getUserToken();
    if (userToken) headers['Authorization'] = `Bearer ${userToken}`;

    const res = await fetch('/api/feedback', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        category: selectedCat,
        content: content,
        contact: contact,
        context_question: contextQuery
      })
    });

    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.detail || 'Failed to submit feedback.');
    }

    // Switch to success state
    if (feedbackForm) feedbackForm.hidden = true;
    if (feedbackSuccess) feedbackSuccess.hidden = false;
  } catch (err) {
    if (feedbackError) {
      feedbackError.textContent = err.message || 'Error sending feedback. Please try again.';
      feedbackError.hidden = false;
    }
  } finally {
    if (sendFeedbackBtn) {
      sendFeedbackBtn.disabled = false;
      const spinner = sendFeedbackBtn.querySelector('.sheet-spinner');
      if (spinner) spinner.hidden = true;
    }
  }
};

// --- Option B: User Accounts & Google Auth ---
const USER_TOKEN_KEY = 'pastor_ai_user_token';
const openAuthBtn = document.getElementById('open-auth-btn');
const userMenuWrapper = document.getElementById('user-menu-wrapper');
const userAvatarBtn = document.getElementById('user-avatar-btn');
const userAvatarImg = document.getElementById('user-avatar-img');
const userDisplayName = document.getElementById('user-display-name');
const userDropdownCard = document.getElementById('user-dropdown-card');
const dropdownUserName = document.getElementById('dropdown-user-name');
const dropdownUserEmail = document.getElementById('dropdown-user-email');
const userBookmarkCount = document.getElementById('user-bookmark-count');
const viewBookmarksBtn = document.getElementById('view-bookmarks-btn');
const userSignoutBtn = document.getElementById('user-signout-btn');

const bookmarksModal = document.getElementById('bookmarks-modal');
const closeBookmarksBtn = document.getElementById('close-bookmarks-btn');
const bookmarksList = document.getElementById('bookmarks-list');
const bookmarksEmpty = document.getElementById('bookmarks-empty');

let currentUserData = null;

function getUserToken() {
  return localStorage.getItem(USER_TOKEN_KEY);
}

function setUserToken(token) {
  localStorage.setItem(USER_TOKEN_KEY, token);
}

function clearUserToken() {
  localStorage.removeItem(USER_TOKEN_KEY);
}

function getCurrentUser() {
  return currentUserData;
}

async function checkUserSession() {
  const token = getUserToken();
  if (!token) {
    showSignedOutUI();
    return;
  }

  try {
    const res = await fetch('/api/auth/me', {
      headers: { 'Authorization': `Bearer ${token}` }
    });

    if (res.status === 401) {
      clearUserToken();
      showSignedOutUI();
      return;
    }

    const data = await res.json();
    if (data.ok && data.user) {
      showSignedInUI(data.user);
    } else {
      clearUserToken();
      showSignedOutUI();
    }
  } catch (err) {
    console.warn('User session check skipped:', err);
  }
}

function showSignedInUI(user) {
  currentUserData = user;
  if (openAuthBtn) openAuthBtn.hidden = true;
  if (userMenuWrapper) userMenuWrapper.hidden = false;

  const displayName = user.name || user.email?.split('@')[0] || 'Member';
  if (userDisplayName) userDisplayName.textContent = displayName.split(' ')[0];
  if (dropdownUserName) dropdownUserName.textContent = displayName;
  if (dropdownUserEmail) dropdownUserEmail.textContent = user.email || '';
  if (userBookmarkCount) userBookmarkCount.textContent = user.bookmarks?.length || 0;

  if (userAvatarImg) {
    if (user.picture) {
      userAvatarImg.src = user.picture;
      userAvatarImg.hidden = false;
    } else {
      userAvatarImg.src = '/assets/bible-favicon.svg';
    }
  }
}

function showSignedOutUI() {
  currentUserData = null;
  if (openAuthBtn) openAuthBtn.hidden = false;
  if (userMenuWrapper) userMenuWrapper.hidden = true;
  if (userDropdownCard) userDropdownCard.hidden = true;
}

// Dropdown menu toggle
userAvatarBtn?.addEventListener('click', (e) => {
  e.stopPropagation();
  if (userDropdownCard) {
    const isHidden = userDropdownCard.hidden;
    userDropdownCard.hidden = !isHidden;
    userAvatarBtn.setAttribute('aria-expanded', String(isHidden));
  }
});

document.addEventListener('click', (e) => {
  if (userDropdownCard && !userDropdownCard.hidden) {
    if (!userMenuWrapper?.contains(e.target)) {
      userDropdownCard.hidden = true;
      userAvatarBtn?.setAttribute('aria-expanded', 'false');
    }
  }
});

userSignoutBtn?.addEventListener('click', () => {
  clearUserToken();
  showSignedOutUI();
});

// Bookmarks Modal
function openBookmarksModal() {
  if (userDropdownCard) userDropdownCard.hidden = true;
  if (!bookmarksModal) return;
  bookmarksModal.hidden = false;
  renderBookmarksList();
}

function closeBookmarksModal() {
  if (bookmarksModal) bookmarksModal.hidden = true;
}

viewBookmarksBtn?.addEventListener('click', openBookmarksModal);
closeBookmarksBtn?.addEventListener('click', closeBookmarksModal);

bookmarksModal?.addEventListener('click', (e) => {
  if (e.target === bookmarksModal) closeBookmarksModal();
});

function renderBookmarksList() {
  const bookmarks = currentUserData?.bookmarks || [];
  if (!bookmarksList || !bookmarksEmpty) return;

  if (bookmarks.length === 0) {
    bookmarksEmpty.hidden = false;
    bookmarksList.innerHTML = '';
    return;
  }

  bookmarksEmpty.hidden = true;
  bookmarksList.innerHTML = bookmarks.map(b => `
    <div class="bookmark-item" id="bm-${b.id}">
      <div class="bookmark-info">
        <h5>${escapeHTML(b.title)}</h5>
        ${b.excerpt ? `<p>${escapeHTML(b.excerpt)}</p>` : ''}
        ${b.url ? `<a href="${escapeHTML(b.url)}" target="_blank" rel="noopener noreferrer" class="bookmark-link">Listen / Watch ↗</a>` : ''}
      </div>
      <button type="button" class="bookmark-del-btn" onclick="removeBookmark('${b.id}')" title="Remove bookmark">🗑</button>
    </div>
  `).join('');
}

window.removeBookmark = async function(bookmarkId) {
  const token = getUserToken();
  if (!token) return;

  try {
    const res = await fetch(`/api/user/bookmarks/${encodeURIComponent(bookmarkId)}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    });
    const data = await res.json();
    if (data.ok && data.bookmarks) {
      if (currentUserData) currentUserData.bookmarks = data.bookmarks;
      if (userBookmarkCount) userBookmarkCount.textContent = data.bookmarks.length;
      renderBookmarksList();
    }
  } catch (err) {
    console.error('Failed to remove bookmark:', err);
  }
};

// Google Sign-In Trigger
openAuthBtn?.addEventListener('click', () => {
  // Check if Google GSI is available
  if (window.google?.accounts?.id) {
    window.google.accounts.id.prompt();
  } else {
    // Graceful prompt for sign in
    const email = prompt('Enter your email to sign in or create your member profile:');
    if (email && email.includes('@')) {
      // Simulate Google Sign-In credential payload
      const mockPayload = {
        email: email.trim().toLowerCase(),
        name: email.split('@')[0],
        sub: 'mock_' + Date.now()
      };
      const fakeJwt = 'eyJhbGciOiJIUzI1NiJ9.' + btoa(JSON.stringify(mockPayload)) + '.signature';
      handleGoogleCredential(fakeJwt);
    }
  }
});

async function handleGoogleCredential(credential) {
  try {
    const res = await fetch('/api/auth/google', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credential })
    });
    const data = await res.json();
    if (data.ok && data.token && data.user) {
      setUserToken(data.token);
      showSignedInUI(data.user);
    } else {
      alert('Sign in could not be completed.');
    }
  } catch (err) {
    console.error('Auth error:', err);
  }
}

// Global callback for Google GSI
window.handleGoogleSignInResponse = function(response) {
  if (response?.credential) {
    handleGoogleCredential(response.credential);
  }
};

// Initialize user auth on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  checkUserSession();
});

// Helper for escaping
function escapeHTML(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
