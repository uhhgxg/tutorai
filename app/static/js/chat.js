/* ============================================================
   TutorAI — 聊天功能
   功能: 多轮对话 / 流式输出 / 对话管理 / 快捷建议 / 代码复制
   ============================================================ */

let currentConvId = window.location.pathname.split('/chat/')[1] || '';
let isStreaming = false;
let streamAbortController = null;

// ========== 初始化 ==========

document.addEventListener('DOMContentLoaded', () => {
    loadConversations();
    if (currentConvId) loadMessages(currentConvId);
    setupAutoResize();
});

// ========== 对话列表 ==========

async function loadConversations() {
    const list = document.getElementById('conv-list');
    if (!list) return;

    try {
        const convs = await apiGet(`${API}/conversations`);
        if (convs.length === 0) {
            list.innerHTML = '<div style="padding:12px;color:var(--text-light);font-size:0.8rem;text-align:center">暂无对话</div>';
            return;
        }
        list.innerHTML = convs.map(c => `
            <a href="/chat/${c.id}" class="conv-item ${c.id === currentConvId ? 'active' : ''}"
               onclick="event.preventDefault(); switchConv('${c.id}')" title="${escapeHtml(c.title)}">
                <span class="conv-item-title">${escapeHtml(c.title)}</span>
                <button class="conv-item-del" onclick="event.preventDefault(); event.stopPropagation(); deleteConv('${c.id}')" title="删除">×</button>
            </a>
        `).join('');
    } catch (e) {
        console.error('加载对话列表失败:', e);
    }
}

function switchConv(convId) {
    if (isStreaming) {
        showToast('请等待当前回复完成', 'warning');
        return;
    }
    currentConvId = convId;
    window.history.pushState({}, '', `/chat/${convId}`);
    loadMessages(convId);
    loadConversations();
    closeSidebar();
}

async function newChat() {
    if (isStreaming) {
        showToast('请等待当前回复完成', 'warning');
        return;
    }
    try {
        const conv = await apiPost(`${API}/conversations`, '');
        window.location.href = `/chat/${conv.id}`;
    } catch (e) {
        showToast(`创建失败: ${e.message}`, 'error');
    }
}

async function deleteConv(convId) {
    if (!confirm('确定删除这个对话吗？')) return;
    try {
        await apiDelete(`${API}/conversations/${convId}`);
        showToast('对话已删除', 'success');
        if (convId === currentConvId) {
            window.location.href = '/chat';
        } else {
            loadConversations();
        }
    } catch (e) {
        showToast(`删除失败: ${e.message}`, 'error');
    }
}

// ========== 消息加载 ==========

async function loadMessages(convId) {
    const container = document.getElementById('chat-messages');
    const titleEl = document.getElementById('chat-title');
    const clearBtn = document.getElementById('btn-clear');

    try {
        const [msgs, convs] = await Promise.all([
            apiGet(`${API}/conversations/${convId}/messages`),
            apiGet(`${API}/conversations`),
        ]);

        const conv = convs.find(c => c.id === convId);
        if (titleEl) titleEl.textContent = conv ? conv.title : '对话辅导';
        if (clearBtn) clearBtn.style.display = msgs.length > 0 ? '' : 'none';

        container.innerHTML = '';
        if (msgs.length === 0) {
            showWelcome();
        } else {
            msgs.forEach(msg => appendMessage(msg.role, msg.content, msg.created_at));
        }
        scrollToBottom(container);
    } catch (e) {
        console.error('加载消息失败:', e);
        showWelcome();
    }
}

function showWelcome() {
    const container = document.getElementById('chat-messages');
    container.innerHTML = `
        <div class="chat-welcome">
            <div class="chat-welcome-icon">🤖</div>
            <h2>你好！我是 TutorAI</h2>
            <p>我是你的 AI 学习导师，耐心解答你的问题。选择一个话题开始吧。</p>
            <div class="suggestion-chips">
                <button class="chip" onclick="sendSuggestion(this)">请给我解释一下什么是机器学习</button>
                <button class="chip" onclick="sendSuggestion(this)">用 Python 写一个快速排序</button>
                <button class="chip" onclick="sendSuggestion(this)">什么是光合作用？</button>
                <button class="chip" onclick="sendSuggestion(this)">帮我理解牛顿第二定律</button>
                <button class="chip" onclick="sendSuggestion(this)">请介绍一下中国近代史</button>
                <button class="chip" onclick="sendSuggestion(this)">如何高效记忆英语单词？</button>
            </div>
        </div>
    `;
}

// ========== 消息渲染 ==========

function appendMessage(role, content, createdAt) {
    const container = document.getElementById('chat-messages');
    const welcome = container.querySelector('.chat-welcome');
    if (welcome) welcome.remove();

    const div = document.createElement('div');
    div.className = `message ${role}`;
    div.innerHTML = `
        <div class="message-avatar">${role === 'user' ? '👤' : '🤖'}</div>
        <div class="message-body">
            <div class="message-bubble">${renderMarkdown(content)}</div>
            ${createdAt ? `<div class="message-time">${formatTime(createdAt)}</div>` : ''}
        </div>
    `;
    container.appendChild(div);
    scrollToBottom(container);
}

function createStreamingBubble() {
    const container = document.getElementById('chat-messages');
    const welcome = container.querySelector('.chat-welcome');
    if (welcome) welcome.remove();

    const div = document.createElement('div');
    div.className = 'message assistant';
    div.id = 'streaming-message';
    div.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-body">
            <div class="message-bubble streaming-cursor"></div>
        </div>
    `;
    container.appendChild(div);
    scrollToBottom(container);
    return div.querySelector('.message-bubble');
}

function finalizeStreamingBubble(html) {
    const msg = document.getElementById('streaming-message');
    if (!msg) return;
    msg.removeAttribute('id');
    const bubble = msg.querySelector('.message-bubble');
    bubble.classList.remove('streaming-cursor');
    bubble.innerHTML = html;
    const body = msg.querySelector('.message-body');
    const timeDiv = document.createElement('div');
    timeDiv.className = 'message-time';
    timeDiv.textContent = formatTime(new Date().toISOString());
    body.appendChild(timeDiv);
}

// ========== 发送消息 ==========

async function sendMessage() {
    if (isStreaming) return;

    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message) return;

    input.value = '';
    input.style.height = 'auto';
    const sendBtn = document.getElementById('btn-send');
    const stopBtn = document.getElementById('btn-stop');
    sendBtn.disabled = true;
    if (stopBtn) stopBtn.classList.add('visible');

    appendMessage('user', message);

    if (!currentConvId) {
        try {
            const conv = await apiPost(`${API}/conversations`, '');
            currentConvId = conv.id;
            window.history.pushState({}, '', `/chat/${currentConvId}`);
            loadConversations();
        } catch (e) {
            showToast('创建对话失败', 'error');
            sendBtn.disabled = false;
            if (stopBtn) stopBtn.classList.remove('visible');
            return;
        }
    }

    isStreaming = true;
    const bubble = createStreamingBubble();
    let fullContent = '';

    try {
        const resp = await fetch(`${API}/conversations/${currentConvId}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message }),
        });

        if (!resp.ok) throw new Error(await resp.text());

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            fullContent += decoder.decode(value, { stream: true });
            bubble.innerHTML = renderMarkdown(fullContent);
            bubble.classList.add('streaming-cursor');
            scrollToBottom(document.getElementById('chat-messages'));
        }
    } catch (e) {
        bubble.innerHTML = renderMarkdown(`❌ 请求失败: ${escapeHtml(e.message)}`);
        showToast('回复生成失败', 'error');
    }

    finalizeStreamingBubble(renderMarkdown(fullContent));
    isStreaming = false;
    sendBtn.disabled = false;
    if (stopBtn) stopBtn.classList.remove('visible');
    document.getElementById('btn-clear').style.display = '';
    input.focus();
    loadConversations();
}

// ========== 输入处理 ==========

function handleChatKey(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function setupAutoResize() {
    const textarea = document.getElementById('chat-input');
    if (!textarea) return;
    textarea.addEventListener('input', function () {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 150) + 'px';
    });
}

function sendSuggestion(chip) {
    document.getElementById('chat-input').value = chip.textContent;
    sendMessage();
}

function clearChat() {
    if (currentConvId) deleteConv(currentConvId);
}
