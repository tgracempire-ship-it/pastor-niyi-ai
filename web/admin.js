/**
 * Pastor Niyi AI · Executive Admin Console
 * Ministerial Intelligence, Traffic Inflow, Questions Telemetry & Feedback Management.
 */

const STORAGE_KEY = 'pastor_ai_admin_token';
let currentMainView = 'analytics'; // 'analytics' or 'feedbacks'
let currentCategory = 'all';
let currentStatus = 'new';
let searchDebounceTimer = null;

// DOM Elements
const loginView = document.getElementById('login-view');
const dashboardView = document.getElementById('dashboard-view');
const loginForm = document.getElementById('admin-login-form');
const adminPasswordInput = document.getElementById('admin-password');
const loginBtn = document.getElementById('login-btn');
const loginError = document.getElementById('login-error');
const defaultPwdBadge = document.getElementById('default-pwd-badge');

// Main view sections
const analyticsSection = document.getElementById('analytics-section');
const feedbacksSection = document.getElementById('feedbacks-section');
const viewAnalyticsBtn = document.getElementById('view-analytics-btn');
const viewFeedbacksBtn = document.getElementById('view-feedbacks-btn');
const viewFeedbackCount = document.getElementById('view-feedback-count');

// Analytics KPI elements
const statTodayVisitors = document.getElementById('stat-today-visitors');
const statTodayChatsSub = document.getElementById('stat-today-chats-sub');
const statLifetimeChats = document.getElementById('stat-lifetime-chats');
const statTotalMembers = document.getElementById('stat-total-members');
const statMemberBreakdown = document.getElementById('stat-member-breakdown');
const statSavedThreads = document.getElementById('stat-saved-threads');
const statBookmarksSub = document.getElementById('stat-bookmarks-sub');
const statOutboundClicks = document.getElementById('stat-outbound-clicks');
const statOutboundBreakdown = document.getElementById('stat-outbound-breakdown');

const inflowChart = document.getElementById('inflow-chart');
const topicsList = document.getElementById('topics-list');
const activityFeed = document.getElementById('activity-feed');

// Feedback elements
const feedbacksList = document.getElementById('feedbacks-list');
const loadingState = document.getElementById('loading-state');
const emptyState = document.getElementById('empty-state');
const statusFilter = document.getElementById('status-filter');
const categoryTabs = document.getElementById('category-tabs');
const searchInput = document.getElementById('search-input');

// Password Modal Elements
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

// --- View Switcher ---
function switchMainView(view) {
  currentMainView = view;
  if (view === 'analytics') {
    viewAnalyticsBtn.classList.add('active');
    viewAnalyticsBtn.setAttribute('aria-selected', 'true');
    viewFeedbacksBtn.classList.remove('active');
    viewFeedbacksBtn.setAttribute('aria-selected', 'false');
    analyticsSection.hidden = false;
    feedbacksSection.hidden = true;
    loadAnalytics();
  } else {
    viewAnalyticsBtn.classList.remove('active');
    viewAnalyticsBtn.setAttribute('aria-selected', 'false');
    viewFeedbacksBtn.classList.add('active');
    viewFeedbacksBtn.setAttribute('aria-selected', 'true');
    analyticsSection.hidden = true;
    feedbacksSection.hidden = false;
    loadFeedbacks();
  }
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

    await loadAnalytics();
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

    loadAnalytics();
    renderFeedbacksData(data);
  } catch (err) {
    console.error('Session load failed:', err);
  }
}

function handleAdminLogout() {
  clearAdminToken();
  showLogin();
}

// --- Analytics Loading & Rendering ---
async function loadAnalytics() {
  const token = getAdminToken();
  if (!token) return showLogin();

  try {
    const res = await fetch('/api/admin/analytics', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (res.status === 401) {
      clearAdminToken();
      return showLogin();
    }
    const data = await res.json();
    if (data.ok) {
      renderAnalyticsData(data);
    }
  } catch (err) {
    console.error('Failed to load analytics:', err);
  }
}

function renderAnalyticsData(data) {
  const s = data.summary || {};
  
  // 1. KPI Cards
  if (statTodayVisitors) statTodayVisitors.textContent = s.today_visitors || 0;
  if (statTodayChatsSub) statTodayChatsSub.textContent = `${s.today_chats || 0} study questions asked today`;
  
  if (statLifetimeChats) statLifetimeChats.textContent = s.total_lifetime_chats || 0;
  if (statTotalMembers) statTotalMembers.textContent = s.total_members || 0;
  if (statMemberBreakdown) statMemberBreakdown.textContent = `${s.google_members || 0} Google · ${s.email_members || 0} Email Profiles`;
  
  if (statSavedThreads) statSavedThreads.textContent = s.total_saved_threads || 0;
  if (statBookmarksSub) statBookmarksSub.textContent = `${s.total_bookmarks || 0} bookmarked teachings`;
  
  const totalOutflow = (s.telegram_clicks || 0) + (s.youtube_clicks || 0);
  if (statOutboundClicks) statOutboundClicks.textContent = totalOutflow;
  if (statOutboundBreakdown) statOutboundBreakdown.textContent = `${s.telegram_clicks || 0} Telegram · ${s.youtube_clicks || 0} YouTube`;

  if (viewFeedbackCount) viewFeedbackCount.textContent = s.total_feedbacks || 0;

  // 2. Render 14-Day Inflow Activity Chart
  renderInflowChart(data.chart_days || []);

  // 3. Render Top Spiritual Topics
  renderTopTopics(data.top_topics || []);

  // 4. Render Activity Feed
  renderActivityFeed(data.recent_activity || []);
}

function renderInflowChart(days) {
  if (!inflowChart) return;
  if (!days.length) {
    inflowChart.innerHTML = '<div style="margin: auto; color: var(--text-muted); font-size: 12px;">No traffic recorded yet</div>';
    return;
  }

  const maxVal = Math.max(1, ...days.map(d => Math.max(d.chats || 0, d.visitors || 0)));

  inflowChart.innerHTML = days.map(d => {
    const chatH = Math.round(((d.chats || 0) / maxVal) * 100);
    const visH = Math.round(((d.visitors || 0) / maxVal) * 100);

    return `
      <div class="chart-bar-col" title="${escapeHTML(d.label)}: ${d.chats || 0} questions, ${d.visitors || 0} visitors">
        <div class="bar-stack">
          <div class="bar-segment chats" style="height: ${Math.max(chatH, 4)}%;"></div>
          <div class="bar-segment visitors" style="height: ${Math.max(visH, 4)}%;"></div>
        </div>
        <span class="bar-date-label">${escapeHTML(d.label.split(' ')[1] || d.label)}</span>
      </div>
    `;
  }).join('');
}

function renderTopTopics(topics) {
  if (!topicsList) return;
  if (!topics.length) {
    topicsList.innerHTML = '<p style="color: var(--text-muted); font-size: 12px; margin: 12px 0;">Spiritual queries will appear here as church members interact with sermons.</p>';
    return;
  }

  const maxCount = Math.max(1, ...topics.map(t => t.count));

  topicsList.innerHTML = topics.map(t => {
    const pct = Math.round((t.count / maxCount) * 100);
    return `
      <div class="topic-row">
        <div class="topic-info">
          <span class="topic-bullet"></span>
          <span class="topic-name">${escapeHTML(t.topic)}</span>
        </div>
        <div class="topic-bar-wrap">
          <div class="topic-bar-fill" style="width: ${pct}%;"></div>
        </div>
        <span class="topic-count">${t.count}</span>
      </div>
    `;
  }).join('');
}

function renderActivityFeed(events) {
  if (!activityFeed) return;
  if (!events.length) {
    activityFeed.innerHTML = '<p style="color: var(--text-muted); font-size: 12px; margin: 12px 0;">No ministerial interactions recorded yet today.</p>';
    return;
  }

  activityFeed.innerHTML = events.map(e => {
    const timeAgo = formatTimeAgo(e.time);
    const typeLabel = e.type === 'chat' ? 'Question' : e.type === 'click' ? 'Media' : e.type === 'save_thread' ? 'Saved Study' : 'Page Visit';
    return `
      <div class="activity-item">
        <span class="activity-badge ${escapeHTML(e.type)}">${typeLabel}</span>
        <div class="activity-detail">
          <div class="activity-summary">${escapeHTML(e.summary || e.detail || 'Interaction')}</div>
          <div class="activity-time">${escapeHTML(timeAgo)}</div>
        </div>
      </div>
    `;
  }).join('');
}

function formatTimeAgo(iso) {
  if (!iso) return '';
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'Just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

// --- Feedbacks Loading & Rendering ---
async function loadFeedbacks() {
  const token = getAdminToken();
  if (!token) return showLogin();

  loadingState.hidden = false;
  emptyState.hidden = true;
  feedbacksList.innerHTML = '';

  const status = statusFilter?.value || 'new';
  const search = searchInput?.value?.trim() || '';

  const params = new URLSearchParams();
  if (status !== 'all') params.append('status', status);
  if (currentCategory !== 'all') params.append('category', currentCategory);
  if (search) params.append('search', search);

  try {
    const res = await fetch(`/api/admin/feedbacks?${params.toString()}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });

    if (res.status === 401) {
      clearAdminToken();
      return showLogin();
    }

    const data = await res.json();
    renderFeedbacksData(data);
  } catch (err) {
    console.error('Failed to load feedbacks:', err);
  } finally {
    loadingState.hidden = true;
  }
}

function renderFeedbacksData(data) {
  const feedbacks = data.feedbacks || [];
  if (viewFeedbackCount) viewFeedbackCount.textContent = data.stats?.total || feedbacks.length;

  if (feedbacks.length === 0) {
    emptyState.hidden = false;
    feedbacksList.innerHTML = '';
    return;
  }

  emptyState.hidden = true;
  feedbacksList.innerHTML = feedbacks.map(renderFeedbackCard).join('');
}

function renderFeedbackCard(fb) {
  const dateStr = fb.created_at ? new Date(fb.created_at).toLocaleDateString(undefined, {
    month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit'
  }) : '';

  const isStarred = fb.status === 'starred';

  return `
    <article class="feedback-card" id="fb-${escapeHTML(fb.id)}">
      <div class="card-top">
        <span class="cat-pill ${escapeHTML(fb.category || 'suggestion')}">${escapeHTML(fb.category || 'Suggestion')}</span>
        <span class="status-badge ${escapeHTML(fb.status || 'new')}">${escapeHTML(fb.status || 'new')}</span>
      </div>

      <div class="feedback-body">${escapeHTML(fb.content || '')}</div>

      ${fb.context_question ? `
        <div class="context-box">
          <strong>Context Query:</strong>
          <p>${escapeHTML(fb.context_question)}</p>
        </div>
      ` : ''}

      <div class="card-footer">
        <div class="contact-meta">
          <strong>${escapeHTML(fb.contact || 'Anonymous Member')}</strong>
          <small>${escapeHTML(dateStr)}</small>
        </div>

        <div class="card-actions">
          ${fb.status === 'new' ? `
            <button type="button" class="action-btn" onclick="updateStatus('${escapeHTML(fb.id)}', 'reviewed')" title="Mark Reviewed">✓ Review</button>
          ` : ''}
          <button type="button" class="action-btn" onclick="updateStatus('${escapeHTML(fb.id)}', '${isStarred ? 'reviewed' : 'starred'}')" title="Star Item">
            ${isStarred ? '★ Starred' : '☆ Star'}
          </button>
          <button type="button" class="action-btn del" onclick="deleteFeedbackItem('${escapeHTML(fb.id)}')" title="Delete Item">🗑</button>
        </div>
      </div>
    </article>
  `;
}

async function updateStatus(id, newStatus) {
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
    if (res.ok) {
      loadFeedbacks();
    }
  } catch (err) {
    console.error('Update status error:', err);
  }
}

async function deleteFeedbackItem(id) {
  if (!confirm('Are you sure you want to permanently delete this observation?')) return;
  const token = getAdminToken();
  if (!token) return showLogin();

  try {
    const res = await fetch(`/api/admin/feedbacks/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (res.ok) {
      loadFeedbacks();
    }
  } catch (err) {
    console.error('Delete feedback error:', err);
  }
}

function exportFeedbacksCSV() {
  const token = getAdminToken();
  if (!token) return showLogin();
  window.location.href = `/api/admin/feedbacks/export?token=${encodeURIComponent(token)}`;
}

// --- Category Tabs & Search ---
function setupTabs() {
  categoryTabs?.addEventListener('click', (e) => {
    const btn = e.target.closest('.tab');
    if (!btn) return;
    categoryTabs.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    currentCategory = btn.dataset.cat || 'all';
    loadFeedbacks();
  });
}

function handleSearchInput(val) {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => {
    loadFeedbacks();
  }, 250);
}

// --- Change Password Modal ---
function openChangePasswordModal() {
  if (!pwdModal) return;
  pwdModal.hidden = false;
  oldPwdInput.value = '';
  newPwdInput.value = '';
  confirmPwdInput.value = '';
  changePwdError.hidden = true;
  changePwdSuccess.hidden = true;
  setTimeout(() => oldPwdInput.focus(), 150);
}

function closeChangePasswordModal() {
  if (pwdModal) pwdModal.hidden = true;
}

pwdModal?.addEventListener('click', (e) => {
  if (e.target === pwdModal) closeChangePasswordModal();
});

async function handleChangePassword() {
  const oldPwd = oldPwdInput.value.trim();
  const newPwd = newPwdInput.value.trim();
  const confPwd = confirmPwdInput.value.trim();

  if (newPwd !== confPwd) {
    changePwdError.textContent = 'New passwords do not match.';
    changePwdError.hidden = false;
    return;
  }

  setLoading(savePwdBtn, true, 'Updating...');
  changePwdError.hidden = true;
  changePwdSuccess.hidden = true;

  try {
    const token = getAdminToken();
    const res = await fetch('/api/admin/change-password', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ old_password: oldPwd, new_password: newPwd })
    });

    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.detail || 'Could not change password.');
    }

    if (data.token) setAdminToken(data.token, true);
    defaultPwdBadge.hidden = true;
    changePwdSuccess.textContent = 'Password updated successfully!';
    changePwdSuccess.hidden = false;
    setTimeout(() => closeChangePasswordModal(), 1500);
  } catch (err) {
    changePwdError.textContent = err.message;
    changePwdError.hidden = false;
  } finally {
    setLoading(savePwdBtn, false, 'Update Password');
  }
}

// --- Google OAuth Modal ---
const googleModal = document.getElementById('google-modal');
const googleClientIdInput = document.getElementById('google-client-id-input');
const googleConfigMsg = document.getElementById('google-config-msg');
const saveGoogleBtn = document.getElementById('save-google-btn');

async function openGoogleOAuthModal() {
  if (!googleModal) return;
  googleModal.hidden = false;
  if (googleConfigMsg) googleConfigMsg.hidden = true;
  try {
    const res = await fetch('/api/auth/config');
    const data = await res.json();
    if (googleClientIdInput && data.google_client_id) {
      googleClientIdInput.value = data.google_client_id;
    }
  } catch (e) {}
}

function closeGoogleOAuthModal() {
  if (googleModal) googleModal.hidden = true;
}

googleModal?.addEventListener('click', (e) => {
  if (e.target === googleModal) closeGoogleOAuthModal();
});

async function handleSaveGoogleClientId() {
  const token = getAdminToken();
  if (!token) return showLogin();

  const clientId = googleClientIdInput?.value?.trim() || '';
  setLoading(saveGoogleBtn, true, 'Saving...');

  try {
    const res = await fetch('/api/admin/google-client-id', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      },
      body: JSON.stringify({ client_id: clientId })
    });

    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.detail || 'Could not save client ID');

    if (googleConfigMsg) {
      googleConfigMsg.textContent = 'Google Client ID saved successfully!';
      googleConfigMsg.hidden = false;
    }
    setTimeout(() => closeGoogleOAuthModal(), 1200);
  } catch (err) {
    alert('Error saving Client ID: ' + err.message);
  } finally {
    setLoading(saveGoogleBtn, false, 'Save Client ID');
  }
}

// Helper: Toggle Password Visibility
function togglePasswordVisibility(inputId, btn) {
  const el = document.getElementById(inputId);
  if (!el) return;
  if (el.type === 'password') {
    el.type = 'text';
    btn.style.color = 'var(--gold)';
  } else {
    el.type = 'password';
    btn.style.color = 'var(--text-muted)';
  }
}

function setLoading(btn, isLoading, text) {
  if (!btn) return;
  btn.disabled = isLoading;
  const textSpan = btn.querySelector('.btn-text');
  const spinner = btn.querySelector('.spinner');
  if (textSpan) textSpan.textContent = text;
  if (spinner) spinner.hidden = !isLoading;
}

function escapeHTML(str) {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
