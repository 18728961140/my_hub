/* ============================================================
   登录 / 会话 / 登出 逻辑
   - 勾选"记住我":登录态存 localStorage(关浏览器不丢)
   - 未勾选:登录态存 sessionStorage(关浏览器失效)
   ============================================================ */

const SESSION_KEY = "wt_session";

function getSession() {
  try {
    return (
      JSON.parse(localStorage.getItem(SESSION_KEY)) ||
      JSON.parse(sessionStorage.getItem(SESSION_KEY)) ||
      null
    );
  } catch {
    return null;
  }
}

function saveSession(user, remember) {
  const session = {
    username: user.username,
    loginAt: new Date().toISOString(),
  };
  localStorage.removeItem(SESSION_KEY);
  sessionStorage.removeItem(SESSION_KEY);
  if (remember) {
    localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  } else {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
  }
}

function clearSession() {
  localStorage.removeItem(SESSION_KEY);
  sessionStorage.removeItem(SESSION_KEY);
}

/* 校验用户名密码:返回 { ok: true } 或 { ok: false, message } */
function login(username, password, remember) {
  const user = CONFIG.demoUsers.find(
    (u) => u.username === username && u.password === password
  );
  if (!user) {
    return { ok: false, message: "用户名或密码错误" };
  }
  saveSession(user, remember);
  return { ok: true };
}

/* 聊天页守卫:未登录则跳回登录页 */
function requireAuth() {
  if (!getSession()) {
    location.replace("index.html");
    return false;
  }
  return true;
}

function logout() {
  clearSession();
  location.replace("index.html");
}

/* 每个用户一个 thread_id(短期记忆隔离),存 localStorage */
function getThreadId(username) {
  const key = "wt_thread_" + username;
  let tid = localStorage.getItem(key);
  if (!tid) {
    tid = crypto.randomUUID();
    localStorage.setItem(key, tid);
  }
  return tid;
}

function newThreadId(username) {
  const tid = crypto.randomUUID();
  localStorage.setItem("wt_thread_" + username, tid);
  return tid;
}
