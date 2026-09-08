# WeTalk-Web · 心理陪伴助手 Web 端

基于后端 FastAPI 接口(WeTalk_v2)开发的前端项目,包含**登录页**与**聊天页**。

## 功能

- 用户名 + 密码登录(演示账号:`admin` / `123456`)
- 记住我(勾选后关闭浏览器仍保持登录)
- 聊天:对接后端 `POST /api/chat/ask`,SSE 流式打字机效果,Markdown 渲染
- 用户隔离:登录用户名作为 `user_id` 传给后端,长期记忆按用户隔离
- 会话隔离:每个用户一个 `thread_id`,可"新对话"重新生成
- 深浅色主题切换、退出登录

## 目录结构

```text
we-talk-web/
├── index.html       # 登录页
├── chat.html        # 聊天页
├── css/style.css    # 共享样式(登录 + 聊天,支持深浅主题)
└── js/
    ├── config.js    # API 地址、演示账号配置
    ├── auth.js      # 登录/会话/登出逻辑
    ├── login.js     # 登录页交互
    └── chat.js      # 聊天页交互(流式请求)
```

## 快速开始

1. 启动后端(项目根目录):

   ```bash
   python main.py
   ```

2. 浏览器访问(后端已挂载 `/web`):

   ```text
   http://127.0.0.1:8000/web/
   ```

3. 使用演示账号登录:`admin` / `123456`

## 关于登录的实现说明

后端目前**只有聊天接口**(`POST /api/chat/ask`)和健康检查(`GET /api/health`),没有认证接口,因此登录页暂时采用**前端模拟认证**:

- 账号密码在 `js/config.js` 的 `demoUsers` 中配置;
- 校验通过后把登录态写入浏览器 `localStorage` / `sessionStorage`;
- 聊天时把登录用户名作为 `user_id` 传给后端,实现"按用户隔离长期记忆"。

如果以后后端增加认证接口(如 `POST /api/auth/login`),只需:

1. 在 `js/config.js` 增加 `loginApi` 地址;
2. 把 `js/login.js` 里的 `auth.login(...)` 调用改为 `fetch(CONFIG.apiBase + CONFIG.loginApi, ...)` 并校验返回结果。

## 接口说明(后端)

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/chat/ask` | 聊天接口,请求体 `{question, thread_id, user_id}`,返回 SSE 文本流 |
| GET | `/api/health` | 健康检查 |
| GET | `/` | 后端自带的前端页面(原 `frontend/`) |
| GET | `/web/` | 本项目(登录页) |

## 前后端分离部署

若前端和后端不在同一域名/端口,修改 `js/config.js` 中的 `apiBase`:

```js
const CONFIG = {
  apiBase: "http://127.0.0.1:8000",   // 改成后端实际地址
  ...
};
```

后端已开启 CORS(`allow_origins=["*"]`),跨域请求可以直接使用。
