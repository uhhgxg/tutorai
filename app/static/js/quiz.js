/* ============================================================
   TutorAI — 出题测试功能
   功能: 文本出题 / 文件出题 / 流式展示 / 答案显示 / 重新生成
   ============================================================ */

let quizMode = 'text';
let quizFile = null;

// ========== 初始化 ==========

document.addEventListener('DOMContentLoaded', () => {
    const textarea = document.getElementById('quiz-content');
    if (textarea) {
        textarea.addEventListener('input', updateCharCount);
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

    try {
        await streamQuizResult(`${API}/quiz/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content, question_count: count }),
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
    formData.append('question_count', count);

    try {
        await streamQuizResult(`${API}/quiz/generate-from-file?question_count=${count}`, {
            method: 'POST',
            body: formData,
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

    // 生成完成后添加操作按钮
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'quiz-actions';
    actionsDiv.innerHTML = `
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
