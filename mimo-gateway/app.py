"""
MiMo 本地代理网关(方案 A)
- 客户端用 OpenAI 协议打 localhost:8080
- 网关先用本地小模型 + 正则做 PII 脱敏(原始敏感数据不出本机)
- 然后把脱敏后的请求转发到 MiMo-V2.5-Pro 远端
- 流式和非流式都支持
"""
from __future__ import annotations
import os
import json
import time
import uuid
import asyncio
from typing import AsyncIterator
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import httpx

from sanitizer import Sanitizer
from local_llm import chat_sanitize
from mimo_client import chat_completion, stream_chat_completion, MIMO_MODEL, MIMO_BASE_URL
# ---------- 配置 ----------
SANITIZE_MODE = os.environ.get("SANITIZE_MODE", "regex")  # off | regex | hybrid
GATEWAY_PORT  = int(os.environ.get("GATEWAY_PORT", "8080"))
GATEWAY_HOST  = os.environ.get("GATEWAY_HOST", "0.0.0.0")

app = FastAPI(title="MiMo Local Privacy Gateway", version="1.0.0")

_sanitizer: Sanitizer | None = None
_sanitizer_lock = asyncio.Lock()

def get_sanitizer() -> Sanitizer:
    global _sanitizer
    if _sanitizer is not None:
        return _sanitizer
    enable_llm = SANITIZE_MODE == "hybrid"
    _sanitizer = Sanitizer(llm_call=chat_sanitize if enable_llm else None, enable_llm=enable_llm)
    return _sanitizer

# ---------- 健康检查 ----------
@app.get("/health")
def health():
    return {
        "status": "ok",
        "sanitize_mode": SANITIZE_MODE,
        "remote_model": MIMO_MODEL,
        "remote_base_url": MIMO_BASE_URL,
    }

@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "mimo-v2.5-pro-local",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local-gateway",
                "remote_model": MIMO_MODEL,
                "sanitize_mode": SANITIZE_MODE,
            }
        ],
    }

# ---------- 核心:chat completions ----------
class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[dict] = Field(...)
    temperature: float | None = 1.0
    top_p: float | None = 1.0
    max_tokens: int | None = None
    stream: bool | None = False
    tools: list[dict] | None = None
    tool_choice: object | None = None
    extra_body: dict | None = None

@app.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest, request: Request):
    if not req.messages:
        raise HTTPException(400, "messages is empty")

    sanitizer = get_sanitizer()
    # 本次请求的基线(用于计算 delta)
    base_regex = sanitizer.stats.regex_hits
    base_llm   = sanitizer.stats.llm_hits
    original   = req.messages
    sanitized  = sanitizer.sanitize_messages(req.messages)
    d_regex    = sanitizer.stats.regex_hits - base_regex
    d_llm      = sanitizer.stats.llm_hits - base_llm

    # payload to remote
    payload = req.model_dump(exclude_none=True)
    payload["messages"] = sanitized
    payload.setdefault("stream", False)
    # 网关始终用远端真实模型名,客户端发的 model 仅用于本机路由
    payload["model"] = MIMO_MODEL

    if payload["stream"]:
        return StreamingResponse(
            _stream_proxy(payload, original, sanitized, sanitizer, d_regex, d_llm),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # 非流式:把本次命中数附在响应 header 里(便于排查)
    try:
        resp = await asyncio.to_thread(chat_completion, payload)
    except Exception as e:
        raise HTTPException(502, f"upstream error: {e}")
    return JSONResponse(
        resp,
        headers={
            "X-Sanitize-Mode": SANITIZE_MODE,
            "X-Sanitize-Regex-Hits": str(d_regex),
            "X-Sanitize-LLM-Hits": str(d_llm),
        },
    )

async def _stream_proxy(payload: dict, original: list[dict], sanitized: list[dict], sanitizer: Sanitizer, d_regex: int = 0, d_llm: int = 0) -> AsyncIterator[bytes]:
    """SSE 透传,首/尾注入审计行(本次请求的命中数)。"""
    audit = {
        "object": "audit.sanitization",
        "id": str(uuid.uuid4()),
        "created": int(time.time()),
        "stats": {
            "regex_hits": d_regex,
            "llm_hits": d_llm,
            "messages_in": len(original),
            "messages_out": len(sanitized),
        },
        "sanitize_mode": SANITIZE_MODE,
        "remote_model": MIMO_MODEL,
    }
    yield f"data: {json.dumps(audit, ensure_ascii=False)}\n\n".encode("utf-8")

    def gen():
        try:
            for data in stream_chat_completion(payload):
                if data.strip() == "[DONE]":
                    yield "data: [DONE]\n\n"
                else:
                    yield f"data: {data}\n\n"
        except Exception as e:
            err = {"error": {"message": str(e), "type": "upstream_error"}}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"

    loop = asyncio.get_event_loop()
    for chunk in await loop.run_in_executor(None, lambda: list(gen())):
        yield chunk

# ---------- 启动 ----------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=GATEWAY_HOST, port=GATEWAY_PORT, log_level="info")
