/* ============================================================
   聊天页交互:对接 POST /api/chat/ask(SSE 流式)
   - user_id   = 登录用户名(长期记忆按用户隔离)
   - thread_id = 该用户的会话 ID(短期记忆隔离)
   ============================================================ */

if (!requireAuth()) {
  throw new Error("未登录");
}

const session = getSession();
const state = {
  threadId: getThreadId(session.username),
  userId: session.username,
};

const messagesEl = document.getElementById("messages");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("sendBtn");
const chatArea = document.getElementById("chatArea");
const newChatBtn = document.getElementById("newChatBtn");
const logoutBtn = document.getElementById("logoutBtn");
const themeBtn = document.getElementById("themeBtn");
const themeIcon = document.getElementById("themeIcon");
const userLabel = document.getElementById("userLabel");

let isStreaming = false;

// 顶部显示当前登录用户
userLabel.textContent = "已登录: " + session.username;

// ---------- 工具函数 ----------
function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderMarkdown(text) {
  let html = escapeHtml(text);                 // 1. 转义,防 XSS
  html = html.replace(/\n/g, "<br>");          // 2. 换行
  html = html.replace(/```([\s\S]*?)```/g,     // 3. 代码块 ```...```
    (match, code) => "<pre><code>" + code.trim() + "</code></pre>");
  html = html.replace(/`([^`\n]+)`/g, "<code>$1</code>");   // 4. 行内代码
  html = html.replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");  // 5. 加粗
  return html;
}

function scrollToBottom() {
  chatArea.scrollTop = chatArea.scrollHeight;
}

function showWelcome() {
  messagesEl.innerHTML = `
    <div class="welcome">
      <h1>你好,${escapeHtml(session.username)}</h1>
      <p>无论压力、焦虑还是情绪困扰,都可以和我说说</p>
      <div class="suggestions">
        <button class="suggestion" onclick="send('最近压力很大,晚上总是睡不着,怎么办?')">压力大睡不着怎么办</button>
        <button class="suggestion" onclick="send('我总是忍不住自我否定,很痛苦')">总自我否定怎么办</button>
        <button class="suggestion" onclick="send('我感觉自己什么都做不好')">感觉自己什么都不会</button>
      </div>
    </div>`;
}

function appendUser(text) {
  const div = document.createElement("div");
  div.className = "message user";
  div.innerHTML = `
    <div class="avatar user">${escapeHtml(session.username.slice(0, 1).toUpperCase())}</div>
    <div class="message-body"><div class="text"></div></div>`;
  div.querySelector(".text").textContent = text;
  messagesEl.appendChild(div);
}

function appendAssistant() {
  document.querySelector(".welcome")?.remove();
  const div = document.createElement("div");
  div.className = "message assistant";
  div.innerHTML = `
    <div class="avatar assistant">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
        <circle cx="12" cy="7" r="4"/>
      </svg>
    </div>
    <div class="message-body"><div class="text typing">正在思考</div></div>`;
  messagesEl.appendChild(div);
  scrollToBottom();
  return div.querySelector(".text");
}

// ---------- 发送消息(核心) ----------
async function send(text) {
  text = (text || inputEl.value).trim();
  if (!text || isStreaming) return;

  inputEl.value = "";
  autoResize();
  appendUser(text);

  const assistantEl = appendAssistant();
  isStreaming = true;
  sendBtn.disabled = true;

  try {
    const response = await fetch(CONFIG.apiBase + CONFIG.chatApi, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: text,
        thread_id: state.threadId,
        user_id: state.userId,
      }),
    });

    if (!response.ok) throw new Error("请求失败:" + response.status);

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";
    let firstChunk = true;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (firstChunk) {
        assistantEl.classList.remove("typing");
        firstChunk = false;
      }
      buffer += decoder.decode(value, { stream: true });
      assistantEl.innerHTML = renderMarkdown(buffer);
      scrollToBottom();
    }

    buffer += decoder.decode();
    assistantEl.innerHTML = renderMarkdown(buffer) || "（没有收到回复）";
  } catch (err) {
    assistantEl.classList.remove("typing");
    assistantEl.innerHTML =
      "出错了:" + escapeHtml(err.message) +
      ",请确认后端服务已启动(python main.py)";
  } finally {
    isStreaming = false;
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

// ---------- 新对话 ----------
function newChat() {
  if (isStreaming) return;
  state.threadId = newThreadId(session.username);
  messagesEl.innerHTML = "";
  showWelcome();
}

// ---------- 输入框自适应高度 ----------
function autoResize() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px";
}

// ---------- 主题切换 ----------
function toggleTheme() {
  const root = document.documentElement;
  const isDark = root.dataset.theme === "dark";
  root.dataset.theme = isDark ? "light" : "dark";
  localStorage.setItem("theme", root.dataset.theme);
  updateThemeIcon();
}

function updateThemeIcon() {
  const isDark = document.documentElement.dataset.theme === "dark";
  themeIcon.innerHTML = isDark
    ? '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>'
    : '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z"/>';
}

// ---------- 事件绑定 ----------
sendBtn.addEventListener("click", () => send());
newChatBtn.addEventListener("click", newChat);
logoutBtn.addEventListener("click", logout);
themeBtn.addEventListener("click", toggleTheme);
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});
inputEl.addEventListener("input", autoResize);

// ---------- 初始化 ----------
const savedTheme = localStorage.getItem("theme");
if (savedTheme) {
  document.documentElement.dataset.theme = savedTheme;
}
updateThemeIcon();
showWelcome();
inputEl.focus();
