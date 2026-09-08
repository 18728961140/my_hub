"""
项目入口（一键启动文件）

运行方式：
  python main.py

它会启动 FastAPI 服务（默认 0.0.0.0:8001，开启热重载），
聊天接口地址为：POST /api/chat/ask
页面访问地址为：GET  /（新前端 we-talk-web 登录页）
健康检查地址为：GET  /api/health
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from api.chat_router import chat_router

# 创建 FastAPI 应用（框架核心对象：注册路由、处理 HTTP 请求）
app = FastAPI()

# 挂载聊天路由：main 的 prefix="/api" + 路由自己的 prefix="/chat"
# => 最终接口 /api/chat/ask
app.include_router(chat_router, prefix="/api")


@app.get("/api/health")
async def health():
    """健康检查接口：http://127.0.0.1:8001/api/health 返回 ok 说明服务正常"""
    return {"service": "心理陪伴 RAG", "status": "ok"}


# 挂载独立前端项目 we-talk-web（登录 + 聊天）：访问 /web/ 进入登录页
app.mount("/web", StaticFiles(directory="we-talk-web", html=True), name="web")

# 根路径直接挂载新前端项目：访问 / 即进入 we-talk-web 登录页，
# 聊天页为 /chat.html，静态资源为 /css/... 和 /js/...
# （挂载在 /api 路由之后，接口不受影响）
app.mount("/", StaticFiles(directory="we-talk-web", html=True), name="web_root")

# 跨域配置（CORS）：允许浏览器前端（如 Vue 页面）跨域名调用本服务。
# 生产环境建议把 allow_origins 改成具体的前端地址，而不是 *
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    import os

    import uvicorn

    # 一键启动入口：直接运行 `python main.py` 就能启动服务。
    # 可用环境变量覆盖：HOST / PORT / RELOAD
    #   HOST=0.0.0.0   监听所有网卡（局域网可访问）
    #   PORT=8001      端口
    #   RELOAD=true    热重载：改代码自动重启（开发方便）
    uvicorn.run(
        "main:app",                                  # 以字符串方式导入应用（reload 需要）
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8001")),
        reload=os.getenv("RELOAD", "true").lower() == "true",
    )
