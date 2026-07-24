"""
本地小模型封装 - 线程安全的 llama-cpp 加载器
对外只暴露 chat_sanitize(messages, max_tokens) 一个函数,固定走 chat 格式。
"""
from __future__ import annotations
import os
import threading
from llama_cpp import Llama

_LOCK = threading.Lock()
_LLM: Llama | None = None

DEFAULT_GGUF = os.environ.get(
    "LOCAL_MODEL_PATH",
    "/workspace/mimo-gateway/.cache/models/Qwen--Qwen2.5-0.5B-Instruct-GGUF/snapshots/master/qwen2.5-0.5b-instruct-q4_k_m.gguf",
)

def get_llm() -> Llama:
    global _LLM
    if _LLM is not None:
        return _LLM
    with _LOCK:
        if _LLM is None:
            n_ctx = int(os.environ.get("LOCAL_MODEL_CTX", "2048"))
            n_threads = int(os.environ.get("LOCAL_MODEL_THREADS", "2"))
            _LLM = Llama(
                model_path=DEFAULT_GGUF,
                n_ctx=n_ctx,
                n_threads=n_threads,
                n_gpu_layers=0,
                use_mmap=True,
                use_mlock=False,
                verbose=False,
            )
    return _LLM

def chat_sanitize(messages: list[dict], max_tokens: int = 256) -> str:
    """只用于 PII 脱敏的 chat 补全,带严格 stop 词。"""
    llm = get_llm()
    out = llm.create_chat_completion(
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.0,
        repeat_penalty=1.05,
        stop=["文本:", "---", "用户:", "Assistant:", "助手:", "请脱敏:"],
    )
    return out["choices"][0]["message"]["content"].strip()
