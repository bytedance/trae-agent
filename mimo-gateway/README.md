# MiMo 本地隐私网关 (方案 A)

## 目标

你的云端数据**敏感字段永远不离开本机**:
- 客户端用 OpenAI 协议打 `localhost:8080`
- 网关先用本地小模型 + 正则做 **PII 脱敏**(原始数据不出本进程)
- 再把脱敏后的请求转发到 **MiMo-V2.5-Pro 远端 API**
- 远端返回的响应原样回给客户端

> 注:本仓库**不**是 MiMo 本地化部署。MiMo-V2.5-Pro(1.02T MoE)在 3.9GB RAM / 2 CPU / 7GB 磁盘的机器上不可能运行。
> 该方案让云端数据"准不出域",同时获得 MiMo-V2.5-Pro 的全部能力。

## 架构

```
┌──────────────┐    OpenAI 协议    ┌─────────────────────────────────────────────┐
│ 你的应用/客户端 │ ────────────────▶ │  本机:MiMo Privacy Gateway :8080            │
│  (任何客户端)  │                   │  ┌──────────────────────────────────────┐  │
└──────────────┘                   │  │  1. PII 脱敏(正则 + 可选本地 0.5B)    │  │
                                   │  │     EMAIL/PHONE/IDCARD/CARD/IP/      │  │
                                   │  │     JWT/AWSKEY/PRIVKEY/SECRET       │  │
                                   │  └──────────────────────────────────────┘  │
                                   │  ┌──────────────────────────────────────┐  │
                                   │  │  2. 转发脱敏后 payload 到 MiMo API    │  │
                                   │  └──────────────────────────────────────┘  │
                                   └─────────────────┬───────────────────────────┘
                                                     │ HTTPS (仅脱敏后明文)
                                                     ▼
                                       ┌──────────────────────────┐
                                       │ api.xiaomimimo.com/v1    │
                                       │ mimo-v2.5-pro            │
                                       └──────────────────────────┘
```

## 文件结构

```
mimo-gateway/
├── app.py             # FastAPI 网关(OpenAI 兼容入口)
├── sanitizer.py       # PII 脱敏(正则 + 可选 LLM)
├── local_llm.py       # 本地 Qwen2.5-0.5B 封装(llama-cpp-python)
├── mimo_client.py     # 远端 MiMo-V2.5-Pro 客户端(OpenAI 协议)
├── start.sh           # 启动脚本
├── .env.example       # 配置模板
├── .cache/            # 已下载的本地模型(Qwen2.5-0.5B Q4_K_M,491 MB)
└── README.md          # 本文档
```

## 快速开始

### 1. 准备 API Key

去 [https://platform.xiaomimimo.com/](https://platform.xiaomimimo.com/) 申请 `MIMO_API_KEY`。

### 2. 配置

```bash
cd mimo-gateway
cp .env.example .env
# 编辑 .env,把 MIMO_API_KEY 填进去
```

### 3. 启动

```bash
bash start.sh
```

输出:
```
[start] local model: /workspace/mimo-gateway/.cache/.../qwen2.5-0.5b-instruct-q4_k_m.gguf
[start] sanitize mode: regex
[start] upstream: https://api.xiaomimimo.com/v1 (mimo-v2.5-pro)
[start] listen: http://0.0.0.0:8080
```

### 4. 接入任何 OpenAI 客户端

```python
from openai import OpenAI

client = OpenAI(
    api_key="anything",   # 本网关不校验,但 openai SDK 要求非空
    base_url="http://localhost:8080/v1",
)

resp = client.chat.completions.create(
    model="mimo-v2.5-pro-local",   # 任意名,网关会路由到 mimo-v2.5-pro
    messages=[{"role": "user", "content": "请分析这段文本(包含 zhang@xiaomi.com 等)"}],
    stream=False,
)
print(resp.choices[0].message.content)
```

或者直接 curl:
```bash
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "mimo-v2.5-pro-local",
    "messages": [{"role":"user","content":"邮箱 zhang@xiaomi.com,身份证 110101199003078234"}]
  }'
```

## 配置项 (.env)

| 变量 | 默认 | 说明 |
|---|---|---|
| `MIMO_API_KEY` | 必填 | 远端 MiMo API Key |
| `MIMO_BASE_URL` | `https://api.xiaomimimo.com/v1` | 远端基地址 |
| `MIMO_MODEL` | `mimo-v2.5-pro` | 远端模型名 |
| `SANITIZE_MODE` | `regex` | `off` / `regex` / `hybrid` |
| `LOCAL_MODEL_PATH` | 默认 Qwen2.5-0.5B Q4_K_M | 本地模型路径 |
| `GATEWAY_HOST` | `0.0.0.0` | 监听地址 |
| `GATEWAY_PORT` | `8080` | 监听端口 |

## 脱敏模式说明

| 模式 | 速度 | 覆盖率 | 推荐 |
|---|---|---|---|
| `off` | 0 开销 | 无 | ❌ 不推荐,数据原样发远端 |
| `regex` | ~1ms/条 | 结构化 PII(EMAIL/PHONE/IDCARD/CARD/IP/JWT/AWSKEY/PRIVKEY/SECRET/DNI) | ✅ 默认 |
| `hybrid` | ~2-4s/条 | + 上下文 PII(姓名、组织、地址) | ⚠️ 需 ≥1.5B 本地模型 |

**当前 0.5B 模型在 `hybrid` 模式下不可靠**(会反向编辑已脱敏文本、把比较关系弄反)。
若需要 hybrid,推荐换成 `Qwen2.5-1.5B-Instruct-Q4_K_M.gguf`(1.12 GB),改 `LOCAL_MODEL_PATH` 即可。

## API 端点

- `GET  /health`               — 网关状态、脱敏模式、远端信息
- `GET  /v1/models`            — 列出可用模型(对客户端伪装成单模型)
- `POST /v1/chat/completions`  — OpenAI 兼容 chat completions(支持流式)

## 安全说明 / 限制

- **正则模式能挡掉的结构化 PII**:邮箱、手机号、身份证、信用卡(Luhn 校验)、IP、JWT、AWS Key、私钥、`api_key=xxx` 形式的密钥
- **正则模式挡不住的**(可被 MiMo 看到):中文人名、组织名、详细地址(因为本地 0.5B 不可靠)
- **不会泄露的**:原始 email/phone/id/secret(被脱敏为 `[EMAIL]` 等占位符)
- **建议**:对极高敏感场景(医疗/法律/金融),自行在上游先用规则做精细化分类

## 测试

mock 远端的端到端脱敏测试:
```bash
python3 -c "
import sys; sys.path.insert(0, '.')
import app as gw
from app import app
from fastapi.testclient import TestClient

captured = {}
def fake(p, **k): captured['p']=p; return {'id':'x','object':'chat.completion','created':0,'model':p.get('model'),'choices':[{'index':0,'message':{'role':'assistant','content':'ok'},'finish_reason':'stop'}]}
gw.chat_completion = fake
c = TestClient(app)
r = c.post('/v1/chat/completions', json={'model':'mimo-v2.5-pro','messages':[{'role':'user','content':'zhang@xiaomi.com 13800138000 IDCARD 110101199003078234'}]})
print('status:', r.status_code)
for m in captured['p']['messages']: print('  ->', m)
"
```
