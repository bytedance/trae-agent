"""
本地小模型封装 - 线程安全的 llama-cpp 加载器
对外只暴露 chat_sanitize(messages, max_tokens) 一个函数,固定走 chat 格式。
"""
from __future__ import annotations
import logging
import os
import threading
from llama_cpp import Llama

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_LLM: Llama | None = None

DEFAULT_GGUF = os.environ.get(
    "LOCAL_MODEL_PATH",
    "/workspace/mimo-gateway/.cache/models/Qwen--Qwen2.5-0.5B-Instruct-GGUF/snapshots/master/qwen2.5-0.5b-instruct-q4_k_m.gguf",
)


def _check_gpu_available() -> bool:
    """检测是否有可用的 NVIDIA GPU (通过 nvidia-smi 或环境变量)。"""
    # 方法 1: 检查 CUDA_VISIBLE_DEVICES 环境变量
    cuda_devices = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if cuda_devices and cuda_devices.strip() != "":
        return True
    # 方法 2: 检查 nvidia-smi 是否可用
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return False


def get_llm() -> Llama:
    global _LLM
    if _LLM is not None:
        return _LLM
    with _LOCK:
        if _LLM is None:
            n_ctx = int(os.environ.get("LOCAL_MODEL_CTX", "2048"))
            # P2 修复:原写死 n_threads=2,单核以外的机器白白浪费 CPU。
            # 默认用 os.cpu_count(),可通过 LOCAL_MODEL_THREADS 覆盖。
            n_threads = int(os.environ.get("LOCAL_MODEL_THREADS", str(os.cpu_count() or 4)))
            # P2 修复:原写死 n_gpu_layers=0(纯 CPU)。改为 -1 让 llama-cpp
            # 自动把能 offload 的层放到 GPU;无 GPU 时回退到 CPU,不影响运行。
            n_gpu_layers = int(os.environ.get("LOCAL_MODEL_GPU_LAYERS", "-1"))

            # Issue 15: n_gpu_layers=-1 时检查 GPU 是否真正可用。
            # llama-cpp 在 GPU 内存不足时会静默 fallback 到 CPU,没有任何提示,
            # 用户可能不知道模型实际在 CPU 上跑(性能差 10-100 倍)。
            if n_gpu_layers == -1 and not _check_gpu_available():
                logger.warning(
                    "n_gpu_layers=-1 (auto offload) but no NVIDIA GPU detected. "
                    "The model will run on CPU only, which may be significantly slower. "
                    "Set LOCAL_MODEL_GPU_LAYERS=0 to suppress this warning, or "
                    "ensure CUDA drivers are installed for GPU acceleration."
                )

            _LLM = Llama(
                model_path=DEFAULT_GGUF,
                n_ctx=n_ctx,
                n_threads=n_threads,
                n_gpu_layers=n_gpu_layers,
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
