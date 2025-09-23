import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from google import genai
from google.genai import types

# 环境变量: GEMINI_API_KEY
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY is None:
    raise RuntimeError("环境变量 GEMINI_API_KEY 未设置")

# Gemini client
client = genai.Client()

# 线程池用于在非阻塞事件循环中调用阻塞的客户端（如果需要）
executor = ThreadPoolExecutor(max_workers=3)


async def call_gemini(prompt: str, system_instruction: Optional[str] = None) -> str:
    """异步调用 Gemini API（在线程池中执行阻塞调用）。"""

    def sync_call():
        gen_config = types.GenerateContentConfig(
            system_instruction=system_instruction or "你是一个桌游店员工，请用简单清晰的语言和客人描述桌游的规则，请先用一句话解释核心规则。你需要在桌上放置游戏需要的开局布置，并通过操作拆解规则，讲解时，请说明背景、主题，大机制与胜利条件，并介绍每轮回合的操作和规则细节。请在最后列举常见问题解答和需要强调的关键内容。",
        )
        response = client.models.generate_content(
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