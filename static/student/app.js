/**
 * static/student/app.js
 * Student Dashboard — vanilla JS, no framework.
 *
 * Flow:
 *   1. Login → store studentId in sessionStorage
 *   2. loadDashboard() → fetch /api/student/:id/dashboard + assignments
 *   3. Render summary strip, filter tabs, assignment cards
 *   4. Card click → detail modal (progress timeline, feedback, AI summary)
 *   5. Confetti burst when a "reviewed" assignment is first seen
 */

'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
let studentId        = null;
let allAssignments   = [];
let activeFilter     = 'all';
const celebratedIds  = new Set();  // track which reviewed assignments have fired confetti

// ── DOM refs ──────────────────────────────────────────────────────────────────
const loginScreen    = document.getElementById('login-screen');
const dashboardScreen= document.getElementById('dashboard-screen');
const loginForm      = document.getElementById('login-form');
const loginError     = document.getElementById('login-error');
const studentIdInput = document.getElementById('student-id');

const studentNameDisplay = document.getElementById('student-name-display');
const cardsGrid          = document.getElementById('cards-grid');

const modalOverlay = document.getElementById('modal-overlay');
const modalTitle   = document.getElementById('modal-title');
const modalTeacher = document.getElementById('modal-teacher');
const modalBody    = document.getElementById('modal-body');
const modalClose   = document.getElementById('modal-close');

const confettiCanvas = document.getElementById('confetti-canvas');
const filterTabs     = document.querySelectorAll('.filter-tabs .tab');

// Summary strip
const sv = (id) => document.getElementById(id);
const stripTotal     = sv('strip-total-val');
const stripPending   = sv('strip-pending-val');
const stripProgress  = sv('strip-progress-val');
const stripSubmitted = sv('strip-submitted-val');
const stripReviewed  = sv('strip-reviewed-val');

// ── Init ──────────────────────────────────────────────────────────────────────
(function init() {
  const saved = sessionStorage.getItem('studentId');
  if (saved) {
    studentId = parseInt(saved, 10);
    showDashboard();
  }
})();

// ── Login ─────────────────────────────────────────────────────────────────────
loginForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const id = parseInt(studentIdInput.value.trim(), 10);
  if (!id || id < 1) { showLoginError('Please enter a valid Student ID.'); return; }
  try {
    const res = await fetch(`/api/student/${id}/dashboard`);
    if (!res.ok) { showLoginError('Student not found. Check your ID.'); return; }
    const data = await res.json();
    studentId = id;
    sessionStorage.setItem('studentId', id);
    studentNameDisplay.textContent = data.student_name;
    hideLoginError();
    showDashboard(data);
  } catch {
    showLoginError('Cannot reach the server. Is the app running?');
  }
});

function showLoginError(msg) {
  loginError.textContent = msg;
  loginError.classList.remove('hidden');
}
function hideLoginError() {
  loginError.textContent = '';
  loginError.classList.add('hidden');
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
async function showDashboard(dashData) {
  loginScreen.classList.add('hidden');
  dashboardScreen.classList.remove('hidden');
  await loadDashboard(dashData);
}

async function loadDashboard(dashData) {
  try {
    if (!dashData) {
      const res  = await apiFetch(`/api/student/${studentId}/dashboard`);
      dashData   = res;
      studentNameDisplay.textContent = dashData.student_name;
    }

    stripTotal.textContent     = dashData.total_assignments;
    stripPending.textContent   = dashData.pending;
    stripProgress.textContent  = dashData.in_progress;
    stripSubmitted.textContent = dashData.submitted;
    stripReviewed.textContent  = dashData.reviewed;

    const assignments = await apiFetch(`/api/student/${studentId}/assignments`);
    allAssignments = assignments;
    renderCards(filterAssignments());
    triggerConfettiForReviewed(assignments);
  } catch (err) {
    cardsGrid.innerHTML = `<div class="loading-state">⚠️ Failed to load: ${escHtml(err.message)}</div>`;
  }
}

// ── Filter tabs ───────────────────────────────────────────────────────────────
filterTabs.forEach(tab => {
  tab.addEventListener('click', () => {
    filterTabs.forEach(t => t.classList.remove('active'));
    tab.classList.add('active');
    activeFilter = tab.dataset.filter;
    renderCards(filterAssignments());
  });
});

function filterAssignments() {
  if (activeFilter === 'all') return allAssignments;
  return allAssignments.filter(a => a.status === activeFilter);
}

// ── Card rendering ────────────────────────────────────────────────────────────
function renderCards(assignments) {
  if (!assignments.length) {
    cardsGrid.innerHTML = '<div class="loading-state">No assignments in this category.</div>';
    return;
  }
  cardsGrid.innerHTML = assignments.map(a => buildCard(a)).join('');

  // Attach click listeners
  cardsGrid.querySelectorAll('.assignment-card').forEach(card => {
    card.addEventListener('click', () => openDetail(parseInt(card.dataset.id, 10)));
  });
}

function buildCard(a) {
  const due      = new Date(a.due_date);
  const now      = new Date();
  const totalMs  = due - new Date(a.created_at);
  const elapsedMs= now - new Date(a.created_at);
  const pct      = totalMs > 0 ? Math.max(0, Math.min(100, (elapsedMs / totalMs) * 100)) : 100;
  const daysLeft = Math.ceil((due - now) / 86_400_000);

  // Countdown bar class
  let barClass = '';
  let labelClass = '';
  let countdownText = '';
  if (a.status === 'submitted' || a.status === 'reviewed') {
    countdownText = a.status === 'reviewed' ? '🌟 Reviewed by teacher' : '✅ Submitted';
  } else if (daysLeft < 0) {
    barClass = 'danger'; labelClass = 'danger';
    countdownText = `⚠️ Overdue by ${Math.abs(daysLeft)} day${Math.abs(daysLeft) !== 1 ? 's' : ''}`;
  } else if (daysLeft === 0) {
    barClass = 'danger'; labelClass = 'danger';
    countdownText = '⚠️ Due today!';
  } else if (daysLeft <= 2) {
    barClass = 'danger'; labelClass = 'danger';
    countdownText = `🔴 ${daysLeft} day${daysLeft !== 1 ? 's' : ''} left`;
  } else if (daysLeft <= 5) {
    barClass = 'warn'; labelClass = 'warn';
    countdownText = `🟡 ${daysLeft} days left`;
  } else {
    countdownText = `🟢 ${daysLeft} days left`;
  }

  // Latest progress snippet
  let progressHtml = '';
  if (a.progress_updates && a.progress_updates.length > 0) {
    const latest = a.progress_updates[a.progress_updates.length - 1];
    progressHtml = `<div class="card-progress-snippet">💬 ${escHtml(truncate(latest.message, 80))}</div>`;
  }

  // Feedback badge
  let feedbackHtml = '';
  if (a.feedback) {
    feedbackHtml = `<div class="card-feedback-badge">✅ Feedback received</div>`;
  }

  const pillClass = `pill-${a.status}`;
  const statusLabel = a.status.replace('_', ' ');

  return `<div class="assignment-card status-${escHtml(a.status)}" data-id="${a.id}" role="button" tabindex="0" aria-label="${escHtml(a.title)}">
    <div class="card-header">
      <div>
        <div class="card-title">${escHtml(a.title)}</div>
        <div class="card-teacher">${a.teacher_name ? '👩‍🏫 ' + escHtml(a.teacher_name) : ''}</div>
      </div>
      <span class="status-pill ${pillClass}">${statusLabel}</span>
    </div>
    <div class="card-countdown">
      <div class="countdown-bar-bg">
        <div class="countdown-bar-fill ${barClass}" style="width:${pct}%"></div>
      </div>
      <span class="countdown-label ${labelClass}">${countdownText}</span>
    </div>
    ${progressHtml}
    ${feedbackHtml}
  </div>`;
}

// ── Detail modal ──────────────────────────────────────────────────────────────
async function openDetail(assignmentId) {
  const a = allAssignments.find(x => x.id === assignmentId);
  if (!a) return;

  modalTitle.textContent  = a.title;
  modalTeacher.textContent = a.teacher_name ? `👩‍🏫 ${a.teacher_name}` : '';
  modalBody.innerHTML     = '<div class="spinner"></div>';
  modalOverlay.classList.remove('hidden');
  document.body.style.overflow = 'hidden';

  // Build rich detail — use already-fetched data
  renderModalContent(a);
}

function renderModalContent(a) {
  const due       = new Date(a.due_date);
  const daysLeft  = Math.ceil((due - new Date()) / 86_400_000);
  const dueFmt    = due.toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'long', year: 'numeric' });

  const sections = [];

  // Description
  if (a.description) {
    sections.push(`
      <div>
        <p class="modal-section-title">Assignment Brief</p>
        <div class="modal-description">${escHtml(a.description)}</div>
      </div>
    `);
  }

  // Due date
  let dueText = '';
  if (a.status === 'submitted' || a.status === 'reviewed') {
    dueText = `Due: ${dueFmt}`;
  } else if (daysLeft < 0) {
    dueText = `Due: ${dueFmt} — ⚠️ Overdue by ${Math.abs(daysLeft)} day(s)`;
  } else if (daysLeft === 0) {
    dueText = `Due: ${dueFmt} — ⚠️ Due today!`;
  } else {
    dueText = `Due: ${dueFmt} — ${daysLeft} day(s) remaining`;
  }
  sections.push(`<div><p class="modal-section-title">Deadline</p><p style="font-size:.9rem;color:var(--text-secondary)">${escHtml(dueText)}</p></div>`);

  // Progress timeline
  sections.push(buildTimeline(a.progress_updates));

  // Submission info
  if (a.submission) {
    const sub = a.submission;
    const submittedAt = new Date(sub.submitted_at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    let subInfo = `Submitted on ${submittedAt}`;
    if (sub.file_name) subInfo += ` · 📎 ${escHtml(sub.file_name)}`;
    if (sub.file_type === 'photo') subInfo += ' · 📷 Photo';
    if (sub.file_type === 'voice') subInfo += ' · 🎤 Voice note';
    if (sub.text_content) subInfo += `\n\n${escHtml(truncate(sub.text_content, 200))}`;
    sections.push(`<div><p class="modal-section-title">Your Submission</p><div class="modal-description">${subInfo.replace(/\n/g, '<br>')}</div></div>`);
  }

  // Feedback
  if (a.feedback) {
    const fbText = a.feedback.formatted_feedback || a.feedback.raw_feedback || '';
    sections.push(`
      <div class="feedback-block">
        <div class="feedback-header">✅ Teacher Feedback</div>
        <div class="feedback-text">${escHtml(fbText)}</div>
      </div>
    `);
  }

  // AI summary
  if (a.ai_summary) {
    sections.push(`
      <div class="ai-summary-block">
        <div class="ai-summary-header">🤖 AI Progress Summary</div>
        <div class="ai-summary-text">${escHtml(a.ai_summary)}</div>
      </div>
    `);
  }

  modalBody.innerHTML = sections.join('');
}

function buildTimeline(updates) {
  let inner = '';
  if (!updates || !updates.length) {
    inner = '<p class="timeline-empty">No progress updates yet. Tell your teacher how you\'re getting on!</p>';
  } else {
    inner = updates.map(u => {
      const date = new Date(u.created_at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
      const tag  = u.interpreted_status ? `<span class="timeline-status-tag">${escHtml(u.interpreted_status)}</span>` : '';
      return `<div class="timeline-item">
        <div class="timeline-dot"></div>
        <div class="timeline-content">
          <div class="timeline-date">${date}</div>
          <div class="timeline-text">${escHtml(u.message)}</div>
          ${tag}
        </div>
      </div>`;
    }).join('');
  }
  return `<div><p class="modal-section-title">Progress Updates</p><div class="timeline">${inner}</div></div>`;
}

// ── Confetti ──────────────────────────────────────────────────────────────────
function triggerConfettiForReviewed(assignments) {
  const reviewed = assignments.filter(a => a.status === 'reviewed' && !celebratedIds.has(a.id));
  if (!reviewed.length) return;
  reviewed.forEach(a => celebratedIds.add(a.id));
  launchConfetti();
}

function launchConfetti() {
  const canvas = confettiCanvas;
  const ctx    = canvas.getContext('2d');
  canvas.width  = window.innerWidth;
  canvas.height = window.innerHeight;
  canvas.classList.add('active');

  const COLORS = ['#C2410C','#F59E0B','#16A34A','#0369A1','#7C3AED','#DB2777'];
  const pieces = Array.from({ length: 120 }, () => ({
    x:   Math.random() * canvas.width,
    y:   Math.random() * canvas.height - canvas.height,
    w:   6 + Math.random() * 8,
    h:   10 + Math.random() * 6,
    rot: Math.random() * 360,
    rotV: (Math.random() - 0.5) * 6,
    vx: (Math.random() - 0.5) * 3,
    vy: 3 + Math.random() * 4,
    color: COLORS[Math.floor(Math.random() * COLORS.length)],
    alpha: 1,
  }));

  let frame = 0;
  const MAX_FRAMES = 180;

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    pieces.forEach(p => {
      p.x  += p.vx;
      p.y  += p.vy;
      p.rot += p.rotV;
      if (frame > MAX_FRAMES * 0.6) p.alpha -= 0.012;

      ctx.save();
      ctx.globalAlpha = Math.max(0, p.alpha);
      ctx.translate(p.x + p.w / 2, p.y + p.h / 2);
      ctx.rotate((p.rot * Math.PI) / 180);
      ctx.fillStyle = p.color;
      ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
      ctx.restore();
    });

    frame++;
    if (frame < MAX_FRAMES + 30) {
      requestAnimationFrame(draw);
    } else {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      canvas.classList.remove('active');
    }
  }
  requestAnimationFrame(draw);
}

// ── Modal helpers ─────────────────────────────────────────────────────────────
function closeModal() {
  modalOverlay.classList.add('hidden');
  document.body.style.overflow = '';
}
modalClose.addEventListener('click', closeModal);
modalOverlay.addEventListener('click', (e) => { if (e.target === modalOverlay) closeModal(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });

// ── Logout ────────────────────────────────────────────────────────────────────
document.getElementById('logout-btn').addEventListener('click', () => {
  sessionStorage.removeItem('studentId');
  studentId = null;
  allAssignments = [];
  dashboardScreen.classList.add('hidden');
  loginScreen.classList.remove('hidden');
  studentIdInput.value = '';
});

// ── Keyboard nav for cards ────────────────────────────────────────────────────
cardsGrid.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') {
    const card = e.target.closest('.assignment-card');
    if (card) { e.preventDefault(); openDetail(parseInt(card.dataset.id, 10)); }
  }
});

// ── Utilities ─────────────────────────────────────────────────────────────────
async function apiFetch(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function escHtml(str) {
  if (typeof str !== 'string') return str == null ? '' : String(str);
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function truncate(str, max) {
  if (!str) return '';
  return str.length > max ? str.slice(0, max) + '…' : str;
}
