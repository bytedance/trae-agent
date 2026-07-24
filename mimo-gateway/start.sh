#!/usr/bin/env bash
# MiMo 本地隐私网关 - 启动脚本
# 用法:
#   cp .env.example .env && 编辑填入 MIMO_API_KEY
#   bash start.sh
set -euo pipefail
cd "$(dirname "$0")"

# 加载 .env
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -z "${MIMO_API_KEY:-}" ]]; then
  echo "[FATAL] MIMO_API_KEY 未设置。请 cp .env.example .env 并填入。" >&2
  exit 1
fi

# 探测 GGUF
if [[ ! -f "${LOCAL_MODEL_PATH}" ]]; then
  echo "[FATAL] 本地模型文件不存在: ${LOCAL_MODEL_PATH}" >&2
  echo "  请运行: python3 -c \"from modelscope import snapshot_download; snapshot_download('Qwen/Qwen2.5-0.5B-Instruct-GGUF', allow_patterns=['qwen2.5-0.5b-instruct-q4_k_m.gguf'])\"" >&2
  exit 1
fi

echo "[start] local model: ${LOCAL_MODEL_PATH}"
echo "[start] sanitize mode: ${SANITIZE_MODE:-hybrid}"
echo "[start] upstream: ${MIMO_BASE_URL} (${MIMO_MODEL})"
echo "[start] listen: http://${GATEWAY_HOST:-0.0.0.0}:${GATEWAY_PORT:-8080}"
exec python3 app.py
