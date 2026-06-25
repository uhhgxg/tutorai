/* ============================================================
   TutorAI — 出题测试功能
   功能: 文本出题 / 文件出题 / 流式展示 / 答案显示 / 重新生成
   ============================================================ */

let quizMode = 'text';
let quizFile = null;
let lastResultText = '';  // 最后生成的题目原文，供保存用

// ========== 初始化 ==========

document.addEventListener('DOMContentLoaded', () => {
    const textarea = document.getElementById('quiz-content');
    if (textarea) {
        textarea.addEventListener('input', updateCharCount);
    }
    loadSavedResults();
    // 未登录时跳转
    if (!isLoggedIn()) {
        window.location.href = '/login';
    }
});

function updateCharCount() {
    const textarea = document.getElementById('quiz-content');
    const counter = document.getElementById('quiz-char-count');
    if (textarea && counter) {
        const len = textarea.value.length;
        counter.textContent = `${len} 字`;
        counter.style.color = len >= 50 ? 'var(--success)' : 'var(--text-muted)';
    }
}

// ========== 选项卡切换 ==========

function switchQuizTab(mode) {
    quizMode = mode;
    document.querySelectorAll('.quiz-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.quiz-mode').forEach(m => m.style.display = 'none');

    if (mode === 'text') {
        document.querySelectorAll('.quiz-tab')[0].classList.add('active');
        document.getElementById('quiz-text-mode').style.display = 'block';
    } else {
        document.querySelectorAll('.quiz-tab')[1].classList.add('active');
        document.getElementById('quiz-file-mode').style.display = 'block';
    }
}

// ========== 文件选择 ==========

function handleQuizFileSelect(event) {
    quizFile = event.target.files[0];
    const controls = document.getElementById('quiz-file-controls');
    const fileName = document.getElementById('quiz-file-name');
    if (quizFile && controls) {
        controls.style.display = 'flex';
        if (fileName) fileName.textContent = `已选择: ${quizFile.name}`;
    }
}

// ========== 文本生成 ==========

async function generateQuiz() {
    const content = document.getElementById('quiz-content').value.trim();
    if (content.length < 50) {
        showToast('请输入至少 50 字的知识点内容', 'warning');
        return;
    }

    const count = parseInt(document.getElementById('quiz-count').value);
    const resultDiv = document.getElementById('quiz-result');
    const genBtn = document.getElementById('btn-generate');

    resultDiv.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;color:var(--text-muted)">
            <div class="skeleton" style="width:20px;height:20px;border-radius:50%"></div>
            <span>正在生成 ${count} 道练习题...</span>
        </div>
    `;
    if (genBtn) genBtn.disabled = true;

    const qtype = document.getElementById('quiz-type').value;

    try {
        await streamQuizResult(`${API}/quiz/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify({ content, question_count: count, question_type: qtype }),
        }, resultDiv);
    } catch (e) {
        resultDiv.innerHTML = `
            <div style="color:var(--danger);text-align:center;padding:20px">
                <p>❌ 生成失败: ${escapeHtml(e.message)}</p>
                <button class="btn btn-sm btn-primary" style="margin-top:12px" onclick="generateQuiz()">🔄 重试</button>
            </div>
        `;
    }

    if (genBtn) genBtn.disabled = false;
}

// ========== 文件生成 ==========

async function generateQuizFromFile() {
    if (!quizFile) {
        showToast('请先选择一个文件', 'warning');
        return;
    }

    const count = parseInt(document.getElementById('quiz-file-count').value);
    const qtype = document.getElementById('quiz-file-type').value;
    const resultDiv = document.getElementById('quiz-result');
    const genBtn = document.getElementById('btn-generate-file');

    resultDiv.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;color:var(--text-muted)">
            <div class="skeleton" style="width:20px;height:20px;border-radius:50%"></div>
            <span>正在解析文档并生成 ${count} 道练习题...</span>
        </div>
    `;
    if (genBtn) genBtn.disabled = true;

    const formData = new FormData();
    formData.append('file', quizFile);

    try {
        await streamQuizResult(`${API}/quiz/generate-from-file?question_count=${count}&question_type=${qtype}`, {
            method: 'POST',
            body: formData,
            headers: authHeaders(),
        }, resultDiv);
    } catch (e) {
        resultDiv.innerHTML = `
            <div style="color:var(--danger);text-align:center;padding:20px">
                <p>❌ 生成失败: ${escapeHtml(e.message)}</p>
                <button class="btn btn-sm btn-primary" style="margin-top:12px" onclick="generateQuizFromFile()">🔄 重试</button>
            </div>
        `;
    }

    if (genBtn) genBtn.disabled = false;
}

// ========== 流式结果渲染 ==========

async function streamQuizResult(url, fetchOptions, resultDiv) {
    const resp = await fetch(url, fetchOptions);
    if (resp.status === 401) {
        clearAuth();
        window.location.href = '/login';
        return;
    }
    if (!resp.ok) {
        const errText = await resp.text();
        throw new Error(errText);
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let fullText = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        fullText += decoder.decode(value, { stream: true });
        resultDiv.innerHTML = renderMarkdown(fullText);
        resultDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    // 保存全文，供保存按钮使用
    lastResultText = fullText;

    // 生成完成后添加操作按钮
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'quiz-actions';
    actionsDiv.innerHTML = `
        <button class="btn btn-sm btn-primary" onclick="saveResult()">💾 保存结果</button>
        <button class="btn btn-sm btn-secondary" onclick="regenerateQuiz()">🔄 重新生成</button>
        <button class="btn btn-sm btn-secondary" onclick="toggleAnswers(this)">👁️ 显示答案</button>
        <button class="btn btn-sm btn-ghost" onclick="window.print()">🖨️ 打印</button>
    `;
    resultDiv.appendChild(actionsDiv);
}

// ========== 辅助功能 ==========

function regenerateQuiz() {
    document.getElementById('quiz-result').innerHTML = '';
    if (quizMode === 'text') {
        generateQuiz();
    } else {
        generateQuizFromFile();
    }
}

function toggleAnswers(btn) {
    const resultDiv = document.getElementById('quiz-result');
    const strongs = resultDiv.querySelectorAll('strong');
    const showing = btn.textContent.includes('显示');

    strongs.forEach(el => {
        const text = el.textContent.trim();
        if (text.includes('答案') || text.includes('正确') || text.includes('解析')) {
            const parent = el.closest('li, p, div') || el.parentElement;
            if (showing) {
                parent.style.background = 'var(--success-light)';
                parent.style.padding = '6px 10px';
                parent.style.borderRadius = 'var(--radius-xs)';
                parent.style.borderLeft = '3px solid var(--success)';
            } else {
                parent.style.background = '';
                parent.style.padding = '';
                parent.style.borderRadius = '';
                parent.style.borderLeft = '';
            }
        }
    });

    btn.textContent = showing ? '🙈 隐藏答案' : '👁️ 显示答案';
}


// ========== 保存结果 ==========

async function saveResult() {
    if (!lastResultText) {
        showToast('没有可保存的结果', 'warning');
        return;
    }
    try {
        const resp = await fetch(`${API}/quiz/results`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...authHeaders() },
            body: JSON.stringify({
                title: document.getElementById('quiz-content')?.value.trim().slice(0, 30) || '练习题',
                result_text: lastResultText,
            }),
        });
        if (resp.status === 401) { clearAuth(); window.location.href = '/login'; return; }
        if (!resp.ok) throw new Error((await resp.text()) || '保存失败');
        showToast('✅ 已保存到历史记录', 'success');
        loadSavedResults();
    } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
    }
}

// ========== 历史记录 ==========

async function loadSavedResults() {
    const list = document.getElementById('saved-results-list');
    if (!list) return;

    try {
        const resp = await fetch(`${API}/quiz/results`, { headers: authHeaders() });
        if (!resp.ok) { list.innerHTML = ''; return; }
        const results = await resp.json();

        if (results.length === 0) {
            document.getElementById('saved-count').textContent = '0';
        list.innerHTML = '<div style="color:var(--text-muted);padding:8px;font-size:0.85rem">暂无保存记录</div>';
            return;
        }

        document.getElementById('saved-count').textContent = results.length;
        list.innerHTML = results.map(r => `
            <div class="saved-item" onclick="openSavedResult('${r.id}')" style="cursor:pointer;padding:8px 10px;border-radius:var(--radius-sm);display:flex;justify-content:space-between;align-items:center;gap:8px">
                <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:0.9rem">${escapeHtml(r.title)}</span>
                <span style="font-size:0.75rem;color:var(--text-muted);white-space:nowrap">
                    ${r.question_count} 题 · ${formatTime(r.created_at)}
                </span>
            </div>
        `).join('');
    } catch (e) {
        list.innerHTML = '<div style="color:var(--text-muted);padding:8px;font-size:0.85rem">加载失败</div>';
    }
}

async function openSavedResult(resultId) {
    const resultDiv = document.getElementById('quiz-result');
    resultDiv.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted)">加载中...</div>';

    try {
        const resp = await fetch(`${API}/quiz/results/${resultId}`, { headers: authHeaders() });
        if (!resp.ok) throw new Error('加载失败');
        const result = await resp.json();
        resultDiv.innerHTML = renderMarkdown(result.result_text);

        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'quiz-actions';
        actionsDiv.innerHTML = `
            <button class="btn btn-sm btn-secondary" onclick="deleteSavedResult('${resultId}')" style="color:var(--danger)">🗑️ 删除</button>
            <button class="btn btn-sm btn-secondary" onclick="toggleAnswers(this)">👁️ 显示答案</button>
        `;
        resultDiv.appendChild(actionsDiv);
        resultDiv.scrollIntoView({ behavior: 'smooth' });
    } catch (e) {
        resultDiv.innerHTML = `<div style="color:var(--danger);padding:20px">❌ ${escapeHtml(e.message)}</div>`;
    }
}

async function deleteSavedResult(resultId) {
    if (!confirm('确定删除这份练习吗？')) return;
    try {
        const resp = await fetch(`${API}/quiz/results/${resultId}`, { method: 'DELETE', headers: authHeaders() });
        if (!resp.ok) throw new Error('删除失败');
        showToast('已删除', 'success');
        document.getElementById('quiz-result').innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📝</div>
                <h3>开始生成练习题</h3>
                <p>输入知识点或上传文档，AI 将自动生成高质量选择题</p>
            </div>
        `;
        loadSavedResults();
    } catch (e) {
        showToast('删除失败: ' + e.message, 'error');
    }
}
