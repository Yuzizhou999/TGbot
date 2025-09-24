import os
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager

from gemini import call_gemini

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan handler: 在应用启动时尝试连接 Redis，关闭时清理连接。"""
    global redis_client, REDIS_URL
    # 如果用户显式提供 REDIS_URL，先尝试它
    if REDIS_URL:
        redis_client = await try_connect_redis(REDIS_URL)
        if redis_client:
            print(f"Connected to Redis at {REDIS_URL}")
            yield
            # shutdown
            try:
                await redis_client.close()
            except Exception:
                pass
            return

    # 尝试默认本地 redis
    local_url = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    if not REDIS_URL:
        redis_client = await try_connect_redis(local_url)
        if redis_client:
            REDIS_URL = local_url
            print(f"Connected to local Redis at {local_url}")
            yield
            try:
                await redis_client.close()
            except Exception:
                pass
            return

    # 否则回退到内存并打印提示
    redis_client = None
    print("Redis not available; using in-memory session storage. To enable Redis persistence, set REDIS_URL env var.")
    yield

    # shutdown (nothing to close for in-memory)


app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

# 会话上下文配置
CONTEXT_MAX_MESSAGES = 8

# Redis 支持（可选）：优先使用 REDIS_URL，否则尝试连接本地 redis://localhost:6379/0
REDIS_URL = os.environ.get('REDIS_URL')
redis_client = None

# 内存回退
_INMEM = {}


async def try_connect_redis(url: str):
    """尝试连接指定的 redis URL，返回 client 或 None。"""
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(url)
        # 尝试 ping
        await client.ping()
        return client
    except Exception as e:
        print(f"无法连接 Redis ({url}):", e)
        return None

async def get_messages(session_id: str):
    """获取会话消息列表（从 Redis 或内存）。"""
    if redis_client:
        data = await redis_client.get(f"ctx:{session_id}")
        if data:
            import json
            return json.loads(data)
        return []
    else:
        return _INMEM.get(session_id, [])

async def save_messages(session_id: str, messages):
    """保存会话消息列表（到 Redis 或内存）。"""
    if redis_client:
        import json
        await redis_client.set(f"ctx:{session_id}", json.dumps(messages))
    else:
        _INMEM[session_id] = messages

async def reset_session(session_id: str):
    if redis_client:
        await redis_client.delete(f"ctx:{session_id}")
    else:
        if session_id in _INMEM:
            del _INMEM[session_id]

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.post('/chat')
async def chat(request: Request):
    data = await request.json()
    user_text = data.get('message', '').strip()
    if not user_text:
        return {"error": "empty message"}

    session_id = data.get('session_id')
    if not session_id:
        session_id = str(uuid.uuid4())

    # 获取会话消息列表
    messages = await get_messages(session_id)
    messages.append({"role": "user", "content": user_text})
    if len(messages) > CONTEXT_MAX_MESSAGES:
        messages = messages[-CONTEXT_MAX_MESSAGES:]

    # 构造 prompt（简单拼接角色与内容）
    prompt_parts = []
    for m in messages:
        if m.get('role') == 'user':
            prompt_parts.append(f"用户: {m.get('content')}")
        else:
            prompt_parts.append(f"AI: {m.get('content')}")
    prompt = "\n".join(prompt_parts) + "\nAI:"

    try:
        answer = await call_gemini(prompt)
    except Exception as e:
        return {"error": str(e)}

    # 保存 assistant 回复
    messages.append({"role": "assistant", "content": answer})
    if len(messages) > CONTEXT_MAX_MESSAGES:
        messages = messages[-CONTEXT_MAX_MESSAGES:]
    await save_messages(session_id, messages)

    # 返回回复并一并返回当前会话历史，便于前端回显完整上下文
    return {"reply": answer, "session_id": session_id, "messages": messages}

@app.post('/history')
async def history(request: Request):
    data = await request.json()
    session_id = data.get('session_id')
    if not session_id:
        return {"error": "missing session_id"}
    messages = await get_messages(session_id)
    return {"session_id": session_id, "messages": messages}

@app.post('/reset')
async def reset(request: Request):
    data = await request.json()
    session_id = data.get('session_id')
    if session_id:
        await reset_session(session_id)
        return {"ok": True}
    return {"ok": False}


# -------- RAG 集成（延迟加载，依赖可选） --------
from typing import Optional
rag_service = None

def get_rag_service():
    global rag_service
    if rag_service is None:
        try:
            from rag import RAGService, load_sample_texts
        except Exception as e:
            raise RuntimeError('RAG dependencies not installed or rag.py missing: ' + str(e))
        rag_service = RAGService()
    return rag_service


@app.post('/rag/ingest')
async def rag_ingest(request: Request):
    """Ingest sample_docs into the vectorstore. Returns count or error."""
    try:
        svc = get_rag_service()
    except Exception as e:
        return {"error": str(e)}

    texts = []
    try:
        from rag import load_sample_texts
        texts = load_sample_texts()
    except Exception:
        return {"error": "failed to load sample texts"}

    try:
        svc.ingest_texts(texts)
        return {"ok": True, "ingested": len(texts)}
    except Exception as e:
        return {"error": str(e)}


@app.post('/rag/query')
async def rag_query(request: Request):
    data = await request.json()
    question = data.get('question')
    k = int(data.get('k', 4))
    if not question:
        return {"error": "missing question"}

    try:
        svc = get_rag_service()
    except Exception as e:
        return {"error": str(e)}

    try:
        svc.init()
    except Exception as e:
        return {"error": "RAG initialization failed: " + str(e)}

    try:
        docs = svc.similarity_search(question, k=k)
    except Exception as e:
        return {"error": "similarity search failed: " + str(e)}

    try:
        answer = await svc.generate_answer(question, docs)
        return {"answer": answer, "docs": [getattr(d, 'metadata', getattr(d, 'metadata', {})) for d in docs]}
    except Exception as e:
        return {"error": "generation failed: " + str(e)}


@app.get('/rag/status')
async def rag_status(load: Optional[bool] = False):
    """Return status about the persisted FAISS index in data/faiss_index.
    If load=true is provided, attempt to initialize the RAGService and report success or error."""
    import os, time
    path = 'data/faiss_index'
    exists = os.path.exists(path) and bool(os.listdir(path))
    files = []
    if os.path.exists(path):
        for fn in os.listdir(path):
            fp = os.path.join(path, fn)
            try:
                st = os.stat(fp)
                files.append({
                    'name': fn,
                    'size': st.st_size,
                    'mtime': int(st.st_mtime)
                })
            except Exception:
                files.append({'name': fn, 'size': None, 'mtime': None})

    resp = {'path': path, 'exists': exists, 'files': files}

    if load:
        try:
            svc = get_rag_service()
            svc.init()
            resp['load'] = {'ok': True}
        except Exception as e:
            resp['load'] = {'ok': False, 'error': str(e)}

    return resp

