#!/bin/bash
# trae-agent 启动脚本
#
# 已解决的网络问题:
# 1. httpx 0.28 与 Shadowrocket 系统代理格式不兼容 → 运行时清空代理
# 2. Playwright MCP 通过 node 直接从本地 node_modules 加载,不再经过 npx 远程下载
# 3. 默认模型:火山引擎 Doubao (在线推理,质量最优)
# 4. 备选模型:本地 Ollama (纯本地,免费)
#
# P2-15 修复:不再强制清空所有代理。如果 TRAE_KEEP_PROXY=1 就保留系统
# 代理(给需要访问 OpenAI/Anthropic API 的国内用户用)。默认仍然清
# 代理,因为多数用户是 macOS + Shadowrocket,这个 workaround 必要。

cd "$(dirname "$0")"

# 激活 Python venv
source .venv/bin/activate

# 默认清代理(httpx/Shadowrocket 兼容性);TRAE_KEEP_PROXY=1 时保留
if [ "${TRAE_KEEP_PROXY:-0}" != "1" ]; then
    unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
    export NO_PROXY='*'
fi

echo "trae-agent 交互模式"
echo "默认模型: 火山引擎 Doubao-Seed-2.0-mini (在线推理)"
echo "备选模型: 本地 Ollama (通过 --provider ollama --model qwen2.5-coder:7b 切换)"
echo "浏览器工具: Playwright MCP (本地加载)"
echo "代理: ${TRAE_KEEP_PROXY:+保留系统} ${TRAE_KEEP_PROXY:-已清空 (httpx 兼容模式)}"
echo ""

# 交互模式启动(默认用 Doubao)
trae-cli interactive --provider doubao "$@"
