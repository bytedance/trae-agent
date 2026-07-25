"""
MiMo-V2.5-Pro 远端客户端
OpenAI 兼容协议, base_url = https://api.xiaomimimo.com/v1
模型名: mimo-v2.5-pro
"""
from __future__ import annotations
import os
import httpx

MIMO_BASE_URL = os.environ.get("MIMO_BASE_URL", "https://api.xiaomimimo.com/v1")
MIMO_API_KEY  = os.environ.get("MIMO_API_KEY", "")
MIMO_MODEL    = os.environ.get("MIMO_MODEL", "mimo-v2.5-pro")

def _headers() -> dict:
    if not MIMO_API_KEY:
        raise RuntimeError("MIMO_API_KEY 未设置,无法调用远端 MiMo API")
    return {
        "Authorization": f"Bearer {MIMO_API_KEY}",
        "Content-Type": "application/json",
    }

def chat_completion(payload: dict, timeout: float = 120.0) -> dict:
    """同步调用 MiMo /chat/completions,支持 stream(由调用方按 SSE 处理)。"""
    payload = {**payload, "model": payload.get("model") or MIMO_MODEL}
    with httpx.Client(timeout=timeout) as c:
        r = c.post(f"{MIMO_BASE_URL}/chat/completions", headers=_headers(), json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"MiMo API {r.status_code}: {r.text[:500]}")
    return r.json()

def stream_chat_completion(payload: dict, timeout: float = 300.0):
    """流式调用,逐行 yield SSE data 行(不含 'data: ' 前缀)。"""
    payload = {**payload, "model": MIMO_MODEL, "stream": True}
    headers = _headers()
    headers["Accept"] = "text/event-stream"
    with httpx.Client(timeout=timeout) as c:
        with c.stream("POST", f"{MIMO_BASE_URL}/chat/completions", headers=headers, json=payload) as r:
            if r.status_code >= 400:
                raise RuntimeError(f"MiMo API {r.status_code}: {r.read().decode('utf-8','ignore')[:500]}")
            for line in r.iter_lines():
                if not line:
                    continue
                if line.startswith("data:"):
                    yield line[5:].lstrip()
                else:
                    yield line


async def stream_chat_completion_async(payload: dict, timeout: float = 300.0):
    """P0-4 修复:异步真流式。yield SSE 行(带 'data: ' 前缀)。

    httpx.AsyncClient.stream + aiter_lines 真正边读边 yield,不再把整个
    生成器 list() 进内存再 yield(原实现等同于一次性返回)。
    """
    payload = {**payload, "model": MIMO_MODEL, "stream": True}
    headers = _headers()
    headers["Accept"] = "text/event-stream"
    async with httpx.AsyncClient(timeout=timeout) as c:
        async with c.stream(
            "POST", f"{MIMO_BASE_URL}/chat/completions", headers=headers, json=payload
        ) as r:
            if r.status_code >= 400:
                body = (await r.aread()).decode("utf-8", "ignore")[:500]
                raise RuntimeError(f"MiMo API {r.status_code}: {body}")
            async for line in r.aiter_lines():
                if not line:
                    continue
                if line.startswith("data:"):
                    # 重组成 'data: <payload>\n\n' 让客户端能直接解析。
                    yield f"data: {line[5:].lstrip()}\n\n"
                else:
                    yield f"{line}\n\n"
