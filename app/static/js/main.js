/* ============================================================
   TutorAI — 全局共用 JS
   功能: API 封装 / Toast 通知 / 主题切换 / 键盘快捷键 / 工具函数
   ============================================================ */

const API = '/api';

// ========== API 封装 ==========

async function apiGet(url, options = {}) {
    const resp = await fetch(url, { signal: options.timeout ? timeoutSignal(options.timeout) : null });
    if (!resp.ok) {
        const detail = await resp.text().catch(() => 'Unknown error');
        throw new Error(detail || `HTTP ${resp.status}`);
    }
    return resp.json();
}

async function apiPost(url, body) {
    const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!resp.ok) {
        const detail = await resp.text().catch(() => 'Unknown error');
        throw new Error(detail || `HTTP ${resp.status}`);
    }
    return resp.json();
}

async function apiDelete(url) {
    const resp = await fetch(url, { method: 'DELETE' });
    if (!resp.ok) {
        const detail = await resp.text().catch(() => 'Unknown error');
        throw new Error(detail || `HTTP ${resp.status}`);
    }
    return resp.json();
}

function timeoutSignal(ms) {
    return AbortSignal.timeout(ms);
}

// ========== Markdown 渲染 ==========

function renderMarkdown(text) {
    if (typeof marked !== 'undefined') {
        marked.setOptions({ breaks: true, gfm: true });
        const raw = marked.parse(text);
        return addCopyButtons(raw);
    }
    return escapeHtml(text).replace(/\n/g, '<br>');
}

function addCopyButtons(html) {
    const wrapper = document.createElement('div');
    wrapper.innerHTML = html;
    wrapper.querySelectorAll('pre').forEach(pre => {
        pre.style.position = 'relative';
        const btn = document.createElement('button');
        btn.className = 'copy-btn';
        btn.textContent = '复制';
        btn.onclick = function () {
            const code = pre.querySelector('code') || pre;
            navigator.clipboard.writeText(code.textContent).then(() => {
                btn.textContent = '已复制';
                btn.classList.add('copied');
                setTimeout(() => { btn.textContent = '复制'; btn.classList.remove('copied'); }, 2000);
            });
        };
        pre.appendChild(btn);
    });
    return wrapper.innerHTML;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ========== Toast 通知系统 ==========

function createToastContainer() {
    if (document.querySelector('.toast-container')) return;
    const container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
}

function showToast(message, type = 'info', duration = 3500) {
    createToastContainer();
    const container = document.querySelector('.toast-container');

    const icons = { success: '✅', error: '❌', warning: '⚠️', info: 'ℹ️' };
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${icons[type]}</span>
        <span class="toast-body">${escapeHtml(message)}</span>
        <button class="toast-close" onclick="dismissToast(this.parentElement)">×</button>
    `;

    container.appendChild(toast);

    if (duration > 0) {
        setTimeout(() => dismissToast(toast), duration);
    }
}

function dismissToast(toast) {
    if (!toast || toast.classList.contains('removing')) return;
    toast.classList.add('removing');
    setTimeout(() => {
        if (toast.parentElement) toast.remove();
    }, 200);
}

// ========== 主题切换 ==========

function initTheme() {
    const saved = localStorage.getItem('tutorai-theme') || 'light';
    document.documentElement.setAttribute('data-theme', saved);
    updateThemeToggle(saved);
}

function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('tutorai-theme', next);
    updateThemeToggle(next);
}

function updateThemeToggle(theme) {
    const btn = document.getElementById('theme-toggle-btn');
    if (btn) {
        btn.innerHTML = theme === 'dark'
            ? '<span class="theme-toggle-icon">☀️</span> 浅色模式'
            : '<span class="theme-toggle-icon">🌙</span> 深色模式';
    }
}

// ========== 侧边栏（移动端） ==========

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    if (!sidebar) return;
    const isOpen = sidebar.classList.toggle('open');
    if (overlay) overlay.classList.toggle('visible', isOpen);
}

function closeSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebar-overlay');
    if (sidebar) sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('visible');
}

// ========== 全局键盘快捷键 ==========

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeSidebar();
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        const input = document.querySelector('.chat-input, .qa-input');
        if (input) input.focus();
    }
});

// ========== 初始化 ==========

document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    createToastContainer();

    // 侧边栏遮罩点击关闭
    const overlay = document.getElementById('sidebar-overlay');
    if (overlay) overlay.addEventListener('click', closeSidebar);
});

// ========== 工具函数 ==========

function formatTime(isoString) {
    if (!isoString) return '';
    const d = new Date(isoString);
    const now = new Date();
    const diff = now - d;
    if (diff < 60000) return '刚刚';
    if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`;
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function debounce(fn, delay) {
    let timer;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

function scrollToBottom(el) {
    requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
    });
}
