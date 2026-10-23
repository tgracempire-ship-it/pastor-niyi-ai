/**
 * Pastor Niyi AI - Executive Admin Console
 * Secure feedback management, password change, and KPI monitoring.
 */

const STORAGE_KEY = 'pastor_ai_admin_token';
let currentCategory = 'all';
let currentStatus = 'new';
let searchDebounceTimer = null;
let cachedStats = null;

// DOM Elements
const loginView = document.getElementById('login-view');
const dashboardView = document.getElementById('dashboard-view');
const loginForm = document.getElementById('admin-login-form');
const adminPasswordInput = document.getElementById('admin-password');
const loginBtn = document.getElementById('login-btn');
const loginError = document.getElementById('login-error');
const defaultPwdBadge = document.getElementById('default-pwd-badge');

const kpiTotal = document.getElementById('kpi-total');
const kpiNew = document.getElementById('kpi-new');
const kpiSuggestions = document.getElementById('kpi-suggestions');
const kpiSermons = document.getElementById('kpi-sermons');
const kpiBugs = document.getElementById('kpi-bugs');

const feedbacksList = document.getElementById('feedbacks-list');
const loadingState = document.getElementById('loading-state');
const emptyState = document.getElementById('empty-state');
const statusFilter = document.getElementById('status-filter');
const categoryTabs = document.getElementById('category-tabs');
const searchInput = document.getElementById('search-input');

const pwdModal = document.getElementById('pwd-modal');
const oldPwdInput = document.getElementById('old-pwd');
const newPwdInput = document.getElementById('new-pwd');
const confirmPwdInput = document.getElementById('confirm-pwd');
const changePwdError = document.getElementById('change-pwd-error');
const changePwdSuccess = document.getElementById('change-pwd-success');
const savePwdBtn = document.getElementById('save-pwd-btn');

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
  setupTabs();
  const token = getAdminToken();
  if (token) {
    verifySessionAndLoad(token);
  } else {
    showLogin();
  }
});

function getAdminToken() {
  return localStorage.getItem(STORAGE_KEY) || sessionStorage.getItem(STORAGE_KEY);
}

function setAdminToken(token, persist = true) {
  if (persist) {
    localStorage.setItem(STORAGE_KEY, token);
  } else {
    sessionStorage.setItem(STORAGE_KEY, token);
  }
}

function clearAdminToken() {
  localStorage.removeItem(STORAGE_KEY);
  sessionStorage.removeItem(STORAGE_KEY);
}

function showLogin() {
  loginView.hidden = false;
  dashboardView.hidden = true;
  adminPasswordInput.value = '';
  loginError.hidden = true;
  setTimeout(() => adminPasswordInput.focus(), 100);
}

function showDashboard() {
  loginView.hidden = true;
  dashboardView.hidden = false;
}

// --- Auth Handlers ---
async function handleAdminLogin() {
  const password = adminPasswordInput.value.trim();
  if (!password) return;

  setLoading(loginBtn, true, 'Authenticating...');
  loginError.hidden = true;

  try {
    const res = await fetch('/api/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password })
    });

    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.detail || 'Authentication failed. Please verify the password.');
    }

    setAdminToken(data.token, true);
    showDashboard();

    if (data.is_default) {
      defaultPwdBadge.hidden = false;
    } else {
      defaultPwdBadge.hidden = true;
    }

    await loadFeedbacks();
  } catch (err) {
    loginError.textContent = err.message;
    loginError.hidden = false;
  } finally {
    setLoading(loginBtn, false, 'Authenticate & Enter');
  }
}

async function verifySessionAndLoad(token) {
  showDashboard();
  loadingState.hidden = false;
  emptyState.hidden = true;

  try {
    const res = await fetch('/api/admin/feedbacks?status=new', {
      headers: { 'Authorization': `Bearer ${token}` }
    });

    if (res.status === 401) {
      clearAdminToken();
      showLogin();
      return;
    }

    const data = await res.json();
    if (data.is_default_password) {
      defaultPwdBadge.hidden = false;
    } else {
      defaultPwdBadge.hidden = true;
    }

    updateKPIs(data.stats);
    renderFeedbacksList(data.feedbacks || []);
  } catch (err) {
    console.error('Session verification failed:', err);
    clearAdminToken();
    showLogin();
  } finally {
    loadingState.hidden = true;
  }
}

function handleAdminLogout() {
  if (confirm('Are you sure you want to sign out from the Admin Console?')) {
    clearAdminToken();
    showLogin();
  }
}

// --- Category Tabs ---
function setupTabs() {
  if (!categoryTabs) return;
  categoryTabs.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      categoryTabs.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      currentCategory = tab.dataset.cat || 'all';
      loadFeedbacks();
    });
  });
}

function handleSearchInput(query) {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => {
    loadFeedbacks();
  }, 350);
}

// --- Data Fetching & KPIs ---
async function loadFeedbacks() {
  const token = getAdminToken();
  if (!token) {
    showLogin();
    return;
  }

  const status = statusFilter ? statusFilter.value : 'all';
  const search = searchInput ? searchInput.value.trim() : '';
  const params = new URLSearchParams();
  if (status) params.set('status', status);
  if (currentCategory && currentCategory !== 'all') params.set('category', currentCategory);
  if (search) params.set('search', search);

  loadingState.hidden = false;
  emptyState.hidden = true;
  feedbacksList.innerHTML = '';

  try {
    const res = await fetch(`/api/admin/feedbacks?${params.toString()}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });

    if (res.status === 401) {
      clearAdminToken();
      showLogin();
      return;
    }

    const data = await res.json();
    if (data.stats) updateKPIs(data.stats);
    if (typeof data.is_default_password === 'boolean') {
      defaultPwdBadge.hidden = !data.is_default_password;
    }

    renderFeedbacksList(data.feedbacks || []);
  } catch (err) {
    console.error('Failed to load feedbacks:', err);
    feedbacksList.innerHTML = `<div class="alert error full-width">Error loading feedback: ${err.message}</div>`;
  } finally {
    loadingState.hidden = true;
  }
}

function updateKPIs(stats) {
  if (!stats) return;
  cachedStats = stats;
  kpiTotal.textContent = stats.total ?? 0;
  kpiNew.textContent = stats.new ?? 0;
  if (stats.by_category) {
    kpiSuggestions.textContent = stats.by_category.suggestion ?? 0;
    kpiSermons.textContent = stats.by_category.sermon ?? 0;
    kpiBugs.textContent = stats.by_category.bug ?? 0;
  }
}

// --- Rendering Feedback Cards ---
function renderFeedbacksList(items) {
  if (!items || items.length === 0) {
    emptyState.hidden = false;
    feedbacksList.innerHTML = '';
    return;
  }

  emptyState.hidden = true;
  feedbacksList.innerHTML = items.map(item => createFeedbackCardHTML(item)).join('');
}

function createFeedbackCardHTML(fb) {
  const timeFormatted = formatTime(fb.created_at);
  const catLabel = getCategoryLabel(fb.category);
  const statusBadge = getStatusBadge(fb.status);
  const safeContent = escapeHTML(fb.content);
  const safeContact = fb.contact ? escapeHTML(fb.contact) : '';
  const safeContext = fb.context_question ? escapeHTML(fb.context_question) : '';

  const isStarred = fb.status === 'starred';
  const isReviewed = fb.status === 'reviewed';
  const isArchived = fb.status === 'archived';

  return `
    <article class="feedback-card ${fb.status || 'new'}" id="card-${fb.id}">
      <div class="card-head">
        <div class="card-tags">
          <span class="badge cat-${fb.category}">${catLabel}</span>
          ${statusBadge}
        </div>
        <time class="card-date" datetime="${fb.created_at}">${timeFormatted}</time>
      </div>

      <div class="card-body">
        <p class="feedback-text">${safeContent}</p>
        ${safeContext ? `<div class="context-snippet"><strong>Context query:</strong> "${safeContext}"</div>` : ''}
      </div>

      <div class="card-foot">
        <div class="contact-info">
          ${safeContact ? `👤 <span class="contact-val">${safeContact}</span>` : '<span class="anon-label">🔒 Anonymous Member</span>'}
        </div>

        <div class="card-actions">
          <button type="button" class="action-btn star-btn ${isStarred ? 'active' : ''}" 
                  onclick="updateFeedbackStatus('${fb.id}', '${isStarred ? 'reviewed' : 'starred'}')"
                  title="${isStarred ? 'Unstar' : 'Star this suggestion'}">
            ${isStarred ? '★ Starred' : '☆ Star'}
          </button>

          ${!isReviewed ? `
            <button type="button" class="action-btn review-btn" 
                    onclick="updateFeedbackStatus('${fb.id}', 'reviewed')" title="Mark as reviewed">
              ✓ Mark Reviewed
            </button>
          ` : `
            <button type="button" class="action-btn reviewed-done" 
                    onclick="updateFeedbackStatus('${fb.id}', 'new')" title="Re-open to New">
              ↺ Re-open
            </button>
          `}

          ${!isArchived ? `
            <button type="button" class="action-btn archive-btn" 
                    onclick="updateFeedbackStatus('${fb.id}', 'archived')" title="Archive">
              📁 Archive
            </button>
          ` : ''}

          <button type="button" class="action-btn delete-btn" 
                  onclick="confirmDeleteFeedback('${fb.id}')" title="Permanently delete">
            🗑
          </button>
        </div>
      </div>
    </article>
  `;
}

// --- Item Actions ---
async function updateFeedbackStatus(id, newStatus) {
  const token = getAdminToken();
  if (!token) return showLogin();

  try {
    const res = await fetch('/api/admin/feedbacks/status', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ id, status: newStatus })
    });

    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.detail || 'Could not update status');
    }

    // Refresh feedbacks to keep counts and filters in sync
    await loadFeedbacks();
  } catch (err) {
    alert('Action failed: ' + err.message);
  }
}

async function confirmDeleteFeedback(id) {
  if (!confirm('Are you sure you want to delete this feedback entry? This cannot be undone.')) {
    return;
  }

  const token = getAdminToken();
  if (!token) return showLogin();

  try {
    const res = await fetch(`/api/admin/feedbacks/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    });

    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.detail || 'Could not delete feedback');
    }

    // Animate and remove card
    const card = document.getElementById(`card-${id}`);
    if (card) {
      card.style.opacity = '0';
      card.style.transform = 'scale(0.95)';
      setTimeout(() => loadFeedbacks(), 200);
    } else {
      loadFeedbacks();
    }
  } catch (err) {
    alert('Delete failed: ' + err.message);
  }
}

// --- CSV Export ---
function exportFeedbacksCSV() {
  const token = getAdminToken();
  if (!token) return showLogin();
  window.location.href = `/api/admin/feedbacks/export?token=${encodeURIComponent(token)}`;
}

// --- Change Password Modal ---
function openChangePasswordModal() {
  pwdModal.hidden = false;
  oldPwdInput.value = '';
  newPwdInput.value = '';
  confirmPwdInput.value = '';
  changePwdError.hidden = true;
  changePwdSuccess.hidden = true;
  setTimeout(() => oldPwdInput.focus(), 150);
}

function closeChangePasswordModal() {
  pwdModal.hidden = true;
}

// Close modal on backdrop click or Escape
pwdModal?.addEventListener('click', (e) => {
  if (e.target === pwdModal) closeChangePasswordModal();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !pwdModal.hidden) closeChangePasswordModal();
});

async function handleChangePassword() {
  const oldPwd = oldPwdInput.value;
  const newPwd = newPwdInput.value;
  const confirmPwd = confirmPwdInput.value;

  changePwdError.hidden = true;
  changePwdSuccess.hidden = true;

  if (newPwd.length < 4) {
    changePwdError.textContent = 'New password must be at least 4 characters long.';
    changePwdError.hidden = false;
    return;
  }

  if (newPwd !== confirmPwd) {
    changePwdError.textContent = 'New passwords do not match. Please verify.';
    changePwdError.hidden = false;
    return;
  }

  const token = getAdminToken();
  setLoading(savePwdBtn, true, 'Updating...');

  try {
    const res = await fetch('/api/admin/change-password', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({
        old_password: oldPwd,
        new_password: newPwd
      })
    });

    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.detail || 'Password change failed.');
    }

    changePwdSuccess.textContent = 'Password updated successfully! Keep it safe.';
    changePwdSuccess.hidden = false;
    defaultPwdBadge.hidden = true;

    setTimeout(() => {
      closeChangePasswordModal();
    }, 1400);
  } catch (err) {
    changePwdError.textContent = err.message;
    changePwdError.hidden = false;
  } finally {
    setLoading(savePwdBtn, false, 'Update Password');
  }
}

// --- Helpers ---
function togglePasswordVisibility(inputId, btn) {
  const input = document.getElementById(inputId);
  if (!input) return;
  if (input.type === 'password') {
    input.type = 'text';
    btn.textContent = '🙈';
  } else {
    input.type = 'password';
    btn.textContent = '👁';
  }
}

function setLoading(btn, isLoading, text) {
  if (!btn) return;
  btn.disabled = isLoading;
  const textEl = btn.querySelector('.btn-text');
  const spinner = btn.querySelector('.spinner');
  if (textEl) textEl.textContent = text;
  if (spinner) spinner.hidden = !isLoading;
}

function getCategoryLabel(cat) {
  switch (cat) {
    case 'suggestion': return '💡 Suggestion';
    case 'sermon': return '📖 Sermon Quality';
    case 'bug': return '🐛 Bug Report';
    case 'testimony': return '❤️ Testimony';
    case 'rating': return '⭐ Rating';
    default: return '💬 Feedback';
  }
}

function getStatusBadge(status) {
  switch (status) {
    case 'new': return '<span class="status-badge new">New</span>';
    case 'reviewed': return '<span class="status-badge reviewed">Reviewed</span>';
    case 'starred': return '<span class="status-badge starred">⭐ Starred</span>';
    case 'archived': return '<span class="status-badge archived">Archived</span>';
    default: return '';
  }
}

function formatTime(isoStr) {
  if (!isoStr) return '';
  try {
    const d = new Date(isoStr);
    const now = new Date();
    const diffMs = now - d;
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    
    if (diffHours < 1) {
      const diffMins = Math.max(1, Math.floor(diffMs / (1000 * 60)));
      return `${diffMins}m ago`;
    }
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffHours < 48) return 'Yesterday';
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch (e) {
    return isoStr;
  }
}

function escapeHTML(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
