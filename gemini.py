import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from google import genai
from google.genai import types

# 环境变量: GEMINI_API_KEY
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Gemini client will be lazily initialized so importing this module
# doesn't raise when the API key is not present. This prevents
# FastAPI (or other runners) from crashing at import time.
client = None

def _init_client_if_needed():
    global client
    if client is None:
        if not GEMINI_API_KEY:
            return None
        # Initialize the client using environment credentials
        client = genai.Client()
    return client

def validate_api_key(timeout: float = 5.0):
    """可选的运行时检查：尝试用当前 key 列出模型以验证 key 是否有效。
    不打印密钥。如果失败，会抛出异常并提供友好建议。
    """
    try:
        c = _init_client_if_needed()
        if c is None:
            print("API key validation skipped: GEMINI_API_KEY not set")
            return False
        # c.models.list() 应是一个轻量调用，用于验证 API key
        models = c.models.list()
        # 如果返回可迭代对象，尽量消费一点以确保请求成功
        _ = next(iter(models), None)
        print("API key validation: success (models list accessible)")
        return True
    except Exception as e:
        # 给出更清晰的建议而不是原始堆栈
        print("API key validation failed:", str(e))
        return False

# 如果用户希望在启动时自动验证（用于调试），设置环境变量 CHECK_KEY_ON_STARTUP=1
if os.environ.get('CHECK_KEY_ON_STARTUP') in ('1', 'true', 'True'):
    validate_api_key()

# 线程池用于在非阻塞事件循环中调用阻塞的客户端（如果需要）
executor = ThreadPoolExecutor(max_workers=3)


async def call_gemini(prompt: str, system_instruction: Optional[str] = None) -> str:
    """异步调用 Gemini API（在线程池中执行阻塞调用）。"""

    def sync_call():
        c = _init_client_if_needed()
        if c is None:
            raise RuntimeError("环境变量 GEMINI_API_KEY 未设置；无法调用 Gemini API。请在运行环境中设置 GEMINI_API_KEY。")

        gen_config = types.GenerateContentConfig(
            system_instruction=system_instruction or "你是一个桌游店员工，请用简单清晰的语言和客人描述桌游的规则，请先用一句话解释核心规则。你需要在桌上放置游戏需要的开局布置，并通过操作拆解规则，讲解时，请说明背景、主题，大机制与胜利条件，并介绍每轮回合的操作和规则细节。请在最后列举常见问题解答和需要强调的关键内容。",
        )
        response = c.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=gen_config,
        )
        return response.text

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, sync_call)


def cli_loop():
    """简单的交互式 CLI，用于本地测试 Gemini。"""
    print("桌游问答 CLI（输入 exit 退出）")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        while True:
            msg = input('你: ').strip()
            if not msg:
                continue
            if msg.lower() in ('exit', 'quit'):
                break
            # 直接把用户输入作为 prompt
            try:
                reply = loop.run_until_complete(call_gemini(msg))
            except Exception as e:
                print('调用 Gemini 出错:', e)
                continue
            print('\nAI:', reply, '\n')
    finally:
        loop.close()


if __name__ == '__main__':
    cli_loop()