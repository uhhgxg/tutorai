/* ============================================================
   TutorAI — 文档问答功能
   功能: 拖拽上传 / 文档管理 / 智能问答 / 来源引用
   ============================================================ */

let currentDocId = '';

// ========== 初始化 ==========

document.addEventListener('DOMContentLoaded', () => {
    loadDocuments();
    setupDragDrop();
});

// ========== 拖拽上传 ==========

function setupDragDrop() {
    const zone = document.getElementById('upload-zone');
    if (!zone) return;

    ['dragover', 'dragenter'].forEach(eventName => {
        zone.addEventListener(eventName, (e) => {
            e.preventDefault();
            zone.classList.add('dragover');
        });
    });

    ['dragleave', 'dragend', 'drop'].forEach(eventName => {
        zone.addEventListener(eventName, (e) => {
            e.preventDefault();
            zone.classList.remove('dragover');
        });
    });

    zone.addEventListener('drop', (e) => {
        const file = e.dataTransfer.files[0];
        if (file) uploadFile(file);
    });
}

// ========== 文件上传 ==========

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) uploadFile(file);
    event.target.value = '';
}

async function uploadFile(file) {
    const MAX_SIZE = 32 * 1024 * 1024; // 32MB
    if (file.size > MAX_SIZE) {
        showToast('文件大小不能超过 32MB', 'error');
        return;
    }

    const progressDiv = document.getElementById('upload-progress');
    const statusEl = document.getElementById('upload-status');
    const fillEl = document.getElementById('progress-fill');
    progressDiv.style.display = 'block';
    statusEl.textContent = `正在解析 ${file.name}...`;
    fillEl.style.width = '30%';

    const formData = new FormData();
    formData.append('file', file);

    try {
        fillEl.style.width = '70%';
        const resp = await fetch(`${API}/documents/upload`, {
            method: 'POST',
            body: formData,
        });

        if (!resp.ok) {
            const errText = await resp.text();
            throw new Error(errText);
        }

        fillEl.style.width = '100%';
        const doc = await resp.json();
        statusEl.textContent = `解析完成`;

        setTimeout(() => {
            progressDiv.style.display = 'none';
            showToast(`${doc.filename} 上传成功`, 'success');
        }, 500);

        loadDocuments();
        openDocument(doc.id, doc.filename);

    } catch (e) {
        statusEl.textContent = `上传失败`;
        showToast(`上传失败: ${e.message}`, 'error');
        setTimeout(() => { progressDiv.style.display = 'none'; }, 2500);
    }
}

// ========== 文档列表 ==========

async function loadDocuments() {
    const list = document.getElementById('doc-list');
    if (!list) return;

    try {
        const docs = await apiGet(`${API}/documents`);
        if (docs.length === 0) {
            list.innerHTML = '<div style="padding:12px;color:var(--text-light);font-size:0.8rem;text-align:center">暂无文档</div>';
            return;
        }

        list.innerHTML = docs.map(d => `
            <div class="conv-item" onclick="openDocument('${escapeHtml(d.id)}', '${escapeHtml(d.filename)}')" title="${escapeHtml(d.filename)}">
                <span class="conv-item-title">📄 ${escapeHtml(d.filename)}</span>
                <span class="conv-item-meta">${d.chunk_count}块</span>
            </div>
        `).join('');

        // 同时更新主区域文档卡片
        updateDocCards(docs);

    } catch (e) {
        console.error('加载文档列表失败:', e);
    }
}

function updateDocCards(docs) {
    const container = document.getElementById('doc-cards');
    if (!container) return;

    if (docs.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📁</div>
                <h3>还没有上传文档</h3>
                <p>上传 PDF、TXT、Markdown 或代码文件，即可开始文档问答</p>
            </div>
        `;
        return;
    }

    container.innerHTML = docs.map(d => `
        <div class="doc-card" onclick="openDocument('${escapeHtml(d.id)}', '${escapeHtml(d.filename)}')">
            <div class="doc-card-info">
                <div class="doc-card-name">📄 ${escapeHtml(d.filename)}</div>
                <div class="doc-card-meta">${d.chunk_count} 个文本块 · ${formatTime(d.created_at)}</div>
            </div>
            <button class="doc-card-del" onclick="event.stopPropagation(); deleteDocument('${escapeHtml(d.id)}', '${escapeHtml(d.filename)}')" title="删除">🗑️</button>
        </div>
    `).join('');
}

async function deleteDocument(docId, filename) {
    if (!confirm(`确定删除 "${filename}" 吗？`)) return;
    try {
        await apiDelete(`${API}/documents/${docId}`);
        showToast(`${filename} 已删除`, 'success');
        if (docId === currentDocId) closeDocument();
        loadDocuments();
    } catch (e) {
        showToast(`删除失败: ${e.message}`, 'error');
    }
}

// ========== 文档问答 ==========

function openDocument(docId, filename) {
    currentDocId = docId;
    const section = document.getElementById('qa-section');
    const nameEl = document.getElementById('qa-doc-name');
    const resultDiv = document.getElementById('qa-result');

    section.style.display = 'block';
    nameEl.textContent = `📄 ${filename}`;
    resultDiv.innerHTML = `
        <div class="empty-state" style="padding:20px">
            <p>💡 在下方输入问题，AI 将基于文档内容为你解答</p>
        </div>
    `;
    document.getElementById('qa-question').focus();
    section.scrollIntoView({ behavior: 'smooth' });
}

function closeDocument() {
    currentDocId = '';
    document.getElementById('qa-section').style.display = 'none';
    document.getElementById('qa-result').innerHTML = '';
}

async function queryDocument() {
    if (!currentDocId) return;

    const input = document.getElementById('qa-question');
    const question = input.value.trim();
    if (!question) return;

    const resultDiv = document.getElementById('qa-result');
    const queryBtn = document.getElementById('qa-query-btn');

    resultDiv.innerHTML = `
        <div style="display:flex;align-items:center;gap:10px;color:var(--text-muted)">
            <div class="skeleton" style="width:20px;height:20px;border-radius:50%"></div>
            <span>正在搜索文档并生成回答...</span>
        </div>
    `;
    if (queryBtn) queryBtn.disabled = true;
    input.value = '';

    try {
        const data = await apiPost(`${API}/documents/${currentDocId}/query`, {
            question,
            top_k: 5,
        });

        resultDiv.innerHTML = `
            <div class="qa-answer">${renderMarkdown(data.answer)}</div>
            ${data.sources && data.sources.length > 0 ? `
                <details class="source-list" open>
                    <summary style="cursor:pointer;color:var(--text-muted);font-size:0.85rem;font-weight:500">
                        📎 参考来源 (${data.sources.length} 条)
                    </summary>
                    ${data.sources.map((s, i) => `
                        <div class="source-item">
                            <strong>#${i + 1}</strong> ${escapeHtml(s)}
                        </div>
                    `).join('')}
                </details>
            ` : ''}
        `;

    } catch (e) {
        resultDiv.innerHTML = `
            <div style="color:var(--danger);text-align:center;padding:20px">
                <p>❌ 查询失败: ${escapeHtml(e.message)}</p>
                <button class="btn btn-sm btn-primary" style="margin-top:12px" onclick="queryDocumentRetry('${escapeHtml(question)}')">🔄 重试</button>
            </div>
        `;
    }

    if (queryBtn) queryBtn.disabled = false;
    input.focus();
}

function queryDocumentRetry(question) {
    const input = document.getElementById('qa-question');
    input.value = question;
    queryDocument();
}
