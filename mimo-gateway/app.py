"""
MiMo 本地代理网关(方案 A)
- 客户端用 OpenAI 协议打 localhost:8080
- 网关先用本地小模型 + 正则做 PII 脱敏(原始敏感数据不出本机)
- 然后把脱敏后的请求转发到 MiMo-V2.5-Pro 远端
- 流式和非流式都支持

修复历史:
  P0-4  假流式(list 进内存再 yield) → httpx.AsyncClient.stream + 真 async gen
  P0-5  审计 chunk 破坏 OpenAI SSE 协议 → 移到响应末尾
  P1-7  upstream 异常可能泄露 API key → 截断 + 不透传 request body
"""
from __future__ import annotations
import os
import json
import time
import uuid
import asyncio
import secrets
import logging
from typing import AsyncIterator
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
import httpx

from sanitizer import Sanitizer, SanitizeFailedError
from local_llm import chat_sanitize
from mimo_client import (
    chat_completion,
    stream_chat_completion_async,
    MIMO_MODEL,
    MIMO_BASE_URL,
)

# ---------- 配置 ----------
SANITIZE_MODE = os.environ.get("SANITIZE_MODE", "regex")  # off | regex | hybrid
GATEWAY_PORT  = int(os.environ.get("GATEWAY_PORT", "8080"))
GATEWAY_HOST  = os.environ.get("GATEWAY_HOST", "127.0.0.1")
GATEWAY_TOKEN = os.environ.get("GATEWAY_TOKEN")  # P1: optional bearer auth

logger = logging.getLogger("mimo-gateway")

app = FastAPI(title="MiMo Local Privacy Gateway", version="1.1.0")

_sanitizer: Sanitizer | None = None


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


# ---------- 鉴权 (P1: rate-limit / auth) ----------
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # /health 与 /v1/models 公开(用于客户端探活)
    if request.url.path in ("/health", "/v1/models"):
        return await call_next(request)
    if GATEWAY_TOKEN:
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            raise HTTPException(401, "missing or invalid gateway token")
        # 常量时间比较,防止 token 泄露(原代码用 != 存在时序侧信道)。
        if not secrets.compare_digest(auth[7:], GATEWAY_TOKEN):
            raise HTTPException(401, "missing or invalid gateway token")
    return await call_next(request)


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
    try:
        sanitized, sanitized_tools, stats = sanitizer.sanitize(
            req.messages, tools=req.tools, abort_on_failure=True
        )
    except SanitizeFailedError as e:
        # 拒绝 + 不向上游透露 sanitizer 内部错误细节。
        logger.warning("sanitize failed: %r", e)
        raise HTTPException(400, "sanitize failed; refusing to forward") from None

    payload = req.model_dump(exclude_none=True)
    payload["messages"] = sanitized
    if sanitized_tools is not None:
        payload["tools"] = sanitized_tools
    payload.setdefault("stream", False)
    # 网关始终用远端真实模型名
    payload["model"] = MIMO_MODEL

    if payload["stream"]:
        return StreamingResponse(
            _stream_proxy(payload, req.messages, sanitized, stats),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # 非流式
    try:
        resp = await asyncio.to_thread(chat_completion, payload)
    except Exception as e:
        # P1-7: 不回显 e 原文,只记日志;吐给客户端的是通用错误。
        logger.exception("upstream non-stream error")
        raise HTTPException(502, "upstream error") from None
    return JSONResponse(
        resp,
        headers={
            "X-Sanitize-Mode": SANITIZE_MODE,
            "X-Sanitize-Regex-Hits": str(stats.regex_hits),
            "X-Sanitize-LLM-Hits": str(stats.llm_hits),
        },
    )


async def _stream_proxy(
    payload: dict,
    original: list[dict],
    sanitized: list[dict],
    stats,
) -> AsyncIterator[bytes]:
    """SSE 透传,使用 httpx.AsyncClient.stream 真流式 (P0-4)。
    OpenAI 客户端期望首条 data: {...chat.completion.chunk...} (P0-5),
    因此审计 chunk 改为在 [DONE] 之后作为额外 data 事件发送。
    """
    audit = {
        "object": "audit.sanitization",
        "id": str(uuid.uuid4()),
        "created": int(time.time()),
        "stats": {
            "regex_hits": stats.regex_hits,
            "llm_hits": stats.llm_hits,
            "messages_in": len(original),
            "messages_out": len(sanitized),
        },
        "sanitize_mode": SANITIZE_MODE,
        "remote_model": MIMO_MODEL,
    }

    try:
        async for raw in stream_chat_completion_async(payload):
            # stream_chat_completion_async yields SSE-formatted strings
            # already ("data: {...}\n\n") or "[DONE]\n\n".
            yield raw.encode("utf-8") if isinstance(raw, str) else raw
    except Exception as e:
        logger.exception("upstream stream error")
        err = {"error": {"message": "upstream stream error", "type": "upstream_error"}}
        yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n".encode("utf-8")

    # 审计放在 [DONE] 之后 (P0-5),客户端正常 chunk 流已结束。
    yield f"data: {json.dumps(audit, ensure_ascii=False)}\n\n".encode("utf-8")


# ---------- 启动 ----------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=GATEWAY_HOST, port=GATEWAY_PORT, log_level="info")