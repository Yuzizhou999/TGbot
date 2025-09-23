# 桌游问答机器人（Google Gemini）

一个使用 Google Gemini（genai）实现的桌游问答示例程序。提供两种交互方式：

- CLI（命令行）交互：快速在本地测试 Gemini 响应。
- Web（FastAPI + 简单前端）：在浏览器中进行问答交互，支持会话上下文回显与可选的 Redis 持久化。

前提
- Python 3.10+
- 在环境变量中设置 GEMINI_API_KEY

安装依赖（建议在虚拟环境中执行，适用于 Windows PowerShell）：

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
```

快速运行

CLI：
```powershell
$env:GEMINI_API_KEY = 'your_gemini_api_key'
python .\gemini.py
```

Web（建议使用当前 Python 环境显式调用 uvicorn）：
```powershell
$env:GEMINI_API_KEY = 'your_gemini_api_key'
# 可选：指向本地 Redis（若启用）
$env:REDIS_URL = 'redis://localhost:6379/0'
python -m uvicorn web_app:app --host 127.0.0.1 --port 8000
# 打开 http://127.0.0.1:8000/
```

功能说明

- 会话上下文：前端会把 `session_id` 保存到浏览器的 localStorage；后端会在收到消息时把会话（裁剪到最近若干条）保存到 Redis（如可用）或内存回退。
- 回显历史：页面加载时若存在 `session_id` 会调用 `/history` 拉取并渲染历史消息。

Redis 持久化（可选）

仓库中包含示例 Redis 配置与 compose：`docker/redis/redis.conf`（开启 AOF）与 `docker-compose.yml`（挂载数据卷）。使用 Docker 启动后，Redis 会把数据持久化到命名卷；结合 AOF 可在重启后恢复会话上下文。

快速启动 Redis（PowerShell）：

```powershell
# 在项目根运行
docker compose up -d
```

验证持久化：仓库内包含 `scripts/verify_redis_persistence.ps1`，会写入测试 key、触发 AOF 重写、重启容器并检查 key 是否仍然存在。

运行验证脚本（PowerShell）：

```powershell
.\scripts\verify_redis_persistence.ps1
```

检查/调试

- 查看容器与端口映射：
```powershell
docker ps --filter "name=local-redis" --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
```
- 在容器内查看 Redis 持久化信息：
```powershell
docker exec -it local-redis redis-cli INFO Persistence
```
- 查看当前会话键（后端使用前缀 `ctx:`）：
```powershell
docker exec -it local-redis redis-cli KEYS "ctx:*"
```

注意

- 请先确保 Docker Desktop 正在运行（若你使用 Docker 容器启动 Redis）。
- 如果后端启动时无法连接到 Redis，应用会回退到内存存储（此时重启服务将丢失会话），请在启动时确认控制台日志中显示已连接到 Redis。

后续改进建议

- 将 session 与用户账户绑定以支持跨设备恢复。
- 增加导出/导入会话的 API。
- 引入更严格的持久化与备份策略（例如配置 AOF 与 RDB 混合策略、启用 appendfsync everysec/always，根据需要调整）。
