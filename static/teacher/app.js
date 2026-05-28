/**
 * static/teacher/app.js
 * Teacher Dashboard — vanilla JS, no framework dependencies.
 *
 * Flow:
 *   1. Login form → store teacherId in sessionStorage
 *   2. Load dashboard() → fetch /api/teacher/:id/dashboard + assignments
 *   3. Populate stats bar, filter dropdowns, assignment table
 *   4. Auto-refresh every 30 seconds
 *   5. AI Summary modal (per-student) via /api/teacher/:id/student/:sid/summary
 *   6. AI Class Digest modal via SummariserAgent (full digest endpoint)
 */

'use strict';

// ── State ─────────────────────────────────────────────────────────────────────
let teacherId       = null;
let allAssignments  = [];
let refreshTimer    = null;
const REFRESH_MS    = 30_000;

// ── DOM refs ──────────────────────────────────────────────────────────────────
const loginScreen     = document.getElementById('login-screen');
const dashboardScreen = document.getElementById('dashboard-screen');
const loginForm       = document.getElementById('login-form');
const loginError      = document.getElementById('login-error');
const teacherIdInput  = document.getElementById('teacher-id');

const teacherNameDisplay = document.getElementById('teacher-name-display');
const filterStatus       = document.getElementById('filter-status');
const filterStudent      = document.getElementById('filter-student');
const assignmentTbody    = document.getElementById('assignment-tbody');
const digestBtn          = document.getElementById('digest-btn');
const logoutBtn          = document.getElementById('logout-btn');

const modalOverlay = document.getElementById('modal-overlay');
const modalTitle   = document.getElementById('modal-title');
const modalBody    = document.getElementById('modal-body');
const modalClose   = document.getElementById('modal-close');

// Stat value refs
const statStudents  = document.getElementById('stat-students-val');
const statPending   = document.getElementById('stat-pending-val');
const statProgress  = document.getElementById('stat-progress-val');
const statSubmitted = document.getElementById('stat-submitted-val');
const statReviewed  = document.getElementById('stat-reviewed-val');

// ── Init ──────────────────────────────────────────────────────────────────────
(function init() {
  const saved = sessionStorage.getItem('teacherId');
  if (saved) {
    teacherId = parseInt(saved, 10);
    showDashboard();
  }
})();

// ── Login ─────────────────────────────────────────────────────────────────────
loginForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const telegramId = parseInt(teacherIdInput.value.trim(), 10);
  if (!telegramId || telegramId < 1) {
    showLoginError('Please enter a valid Telegram ID.');
    return;
  }

  try {
    // Resolve Telegram ID → DB record
    const lookupRes = await fetch(`/api/user/by-telegram/${telegramId}`);
    if (!lookupRes.ok) {
      const body = await lookupRes.json().catch(() => ({}));
      showLoginError(body.detail || 'User not found. Start the bot with /start on Telegram first.');
      return;
    }
    const user = await lookupRes.json();
    if (user.role !== 'teacher') {
      showLoginError('This Telegram account is registered as a student, not a teacher.');
      return;
    }
    teacherId = user.id;
    sessionStorage.setItem('teacherId', user.id);
    hideLoginError();
    showDashboard();
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
function showDashboard() {
  loginScreen.classList.add('hidden');
  dashboardScreen.classList.remove('hidden');
  loadDashboard();
  startAutoRefresh();
}

async function loadDashboard() {
  try {
    const [dashData, assignData] = await Promise.all([
      apiFetch(`/api/teacher/${teacherId}/dashboard`),
      apiFetch(`/api/teacher/${teacherId}/assignments`),
    ]);

    // Stats bar
    teacherNameDisplay.textContent = dashData.teacher.full_name;
    statStudents.textContent  = dashData.total_students;
    statPending.textContent   = dashData.assignments_pending;
    statProgress.textContent  = dashData.assignments_in_progress;
    statSubmitted.textContent = dashData.assignments_submitted;
    statReviewed.textContent  = dashData.assignments_reviewed;

    allAssignments = assignData;
    populateStudentFilter(assignData);
    renderTable(assignData);
  } catch (err) {
    assignmentTbody.innerHTML = `<tr><td colspan="6" class="loading-row">⚠️ Failed to load data: ${escHtml(err.message)}</td></tr>`;
  }
}

function startAutoRefresh() {
  clearInterval(refreshTimer);
  refreshTimer = setInterval(loadDashboard, REFRESH_MS);
}

// ── Filters ───────────────────────────────────────────────────────────────────
filterStatus.addEventListener('change',  applyFilters);
filterStudent.addEventListener('change', applyFilters);

function applyFilters() {
  const status  = filterStatus.value;
  const student = filterStudent.value;
  const filtered = allAssignments.filter(a => {
    const statusMatch  = !status  || a.status === status;
    const studentMatch = !student || String(a.student_id) === student;
    return statusMatch && studentMatch;
  });
  renderTable(filtered);
}

function populateStudentFilter(assignments) {
  const seen = new Map();
  assignments.forEach(a => {
    if (!seen.has(a.student_id)) seen.set(a.student_id, a.student_name || `Student #${a.student_id}`);
  });
  // Reset to first option only
  filterStudent.innerHTML = '<option value="">All Students</option>';
  seen.forEach((name, id) => {
    const opt = document.createElement('option');
    opt.value = id;
    opt.textContent = name;
    filterStudent.appendChild(opt);
  });
}

// ── Table rendering ───────────────────────────────────────────────────────────
function renderTable(assignments) {
  if (!assignments.length) {
    assignmentTbody.innerHTML = '<tr><td colspan="6" class="loading-row">No assignments match your filters.</td></tr>';
    return;
  }

  const rows = assignments.map(a => {
    const due      = new Date(a.due_date);
    const now      = new Date();
    const daysLeft = Math.ceil((due - now) / 86_400_000);
    const dueFmt   = due.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });

    let daysHtml;
    if (a.status === 'submitted' || a.status === 'reviewed') {
      daysHtml = `<span class="days-ok">—</span>`;
    } else if (daysLeft < 0) {
      daysHtml = `<span class="days-overdue">Overdue ${Math.abs(daysLeft)}d</span>`;
    } else if (daysLeft === 0) {
      daysHtml = `<span class="days-danger">Due today</span>`;
    } else if (daysLeft <= 2) {
      daysHtml = `<span class="days-danger">${daysLeft}d</span>`;
    } else if (daysLeft <= 5) {
      daysHtml = `<span class="days-warning">${daysLeft}d</span>`;
    } else {
      daysHtml = `<span class="days-ok">${daysLeft}d</span>`;
    }

    const statusClass = `status-${a.status}`;
    const statusLabel = a.status.replace('_', ' ');

    return `<tr>
      <td>${escHtml(a.student_name || '—')}</td>
      <td>${escHtml(a.title)}</td>
      <td>${dueFmt}</td>
      <td><span class="status-badge ${statusClass}">${statusLabel}</span></td>
      <td>${daysHtml}</td>
      <td>
        <button class="btn btn-sm btn-accent" onclick="openStudentSummary(${a.student_id}, ${escHtml(JSON.stringify(a.student_name || 'Student'))})">
          🤖 AI Summary
        </button>
      </td>
    </tr>`;
  });

  assignmentTbody.innerHTML = rows.join('');
}

// ── Student AI summary modal ──────────────────────────────────────────────────
window.openStudentSummary = async function (studentId, studentName) {
  openModal(`AI Summary — ${studentName}`);
  showModalSpinner();
  try {
    const data = await apiFetch(`/api/teacher/${teacherId}/student/${studentId}/summary`);
    let content = '';
    if (data.assignments && data.assignments.length) {
      content = data.assignments
        .map(a => `📌 ${a.title}\n${a.summary || 'No summary available.'}`)
        .join('\n\n─────────────────────\n\n');
    } else {
      content = 'No assignments found for this student.';
    }
    modalBody.textContent = content;
  } catch (err) {
    modalBody.textContent = `⚠️ Failed to load summary: ${err.message}`;
  }
};

// ── Class digest modal ────────────────────────────────────────────────────────
digestBtn.addEventListener('click', async () => {
  openModal('📊 AI Class Digest');
  showModalSpinner();
  try {
    // Use the status endpoint which calls generate_teacher_digest
    const data = await apiFetch(`/api/teacher/${teacherId}/assignments`);
    if (!data.length) {
      modalBody.textContent = 'No assignments yet. Assign some work via Telegram first!';
      return;
    }

    // Group by student and build digest text client-side
    const byStudent = {};
    data.forEach(a => {
      const name = a.student_name || `Student #${a.student_id}`;
      if (!byStudent[name]) byStudent[name] = [];
      byStudent[name].push(a);
    });

    const statusEmoji = { pending: '📝', in_progress: '🔄', submitted: '✅', reviewed: '🌟' };
    const lines = ['CLASS DIGEST\n'];
    for (const [name, assignments] of Object.entries(byStudent)) {
      lines.push(`👤 ${name}`);
      assignments.forEach(a => {
        const due   = new Date(a.due_date);
        const days  = Math.ceil((due - new Date()) / 86_400_000);
        const emoji = statusEmoji[a.status] || '❓';
        const timing = days < 0 ? `overdue ${Math.abs(days)}d` : `${days}d left`;
        lines.push(`  ${emoji} ${a.title} — ${a.status.replace('_', ' ')} (${timing})`);
      });
      lines.push('');
    }
    modalBody.textContent = lines.join('\n');
  } catch (err) {
    modalBody.textContent = `⚠️ Failed to generate digest: ${err.message}`;
  }
});

// ── Modal helpers ─────────────────────────────────────────────────────────────
function openModal(title) {
  modalTitle.textContent = title;
  modalOverlay.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}
function closeModal() {
  modalOverlay.classList.add('hidden');
  document.body.style.overflow = '';
}
function showModalSpinner() {
  modalBody.innerHTML = '<div class="spinner"></div>';
}

modalClose.addEventListener('click', closeModal);
modalOverlay.addEventListener('click', (e) => { if (e.target === modalOverlay) closeModal(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });

// ── Logout ────────────────────────────────────────────────────────────────────
logoutBtn.addEventListener('click', () => {
  clearInterval(refreshTimer);
  sessionStorage.removeItem('teacherId');
  teacherId = null;
  allAssignments = [];
  dashboardScreen.classList.add('hidden');
  loginScreen.classList.remove('hidden');
  teacherIdInput.value = '';
});

// ── Utilities ─────────────────────────────────────────────────────────────────
async function apiFetch(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`HTTP ${res.status}: ${body}`);
  }
  return res.json();
}

function escHtml(str) {
  if (typeof str !== 'string') return str;
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}
