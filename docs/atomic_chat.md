# Atomic Chat (local provider)

[Atomic Chat](https://atomic.chat/) runs models on your machine and exposes an **OpenAI-compatible** HTTP API.

Trae Agent uses the `atomic_chat` provider (Chat Completions API at `/v1/chat/completions`).

## Prerequisites

1. Install and open Atomic Chat.
2. Load a model in the app.
3. Enable the **local API server** (default `http://127.0.0.1:1337/v1`).
4. Verify:

```bash
curl http://127.0.0.1:1337/v1/models
```

Use a model `id` from that response as `--model`.

## CLI

```bash
trae-cli run "Add a README section" \
  --provider atomic_chat \
  --model gemma-4-E4B-it-IQ4_XS \
  --model-base-url http://127.0.0.1:1337/v1
```

Optional environment variables:

- `ATOMIC_CHAT_API_KEY` — only if your server requires auth (default config uses `noop`)
- `ATOMIC_CHAT_BASE_URL` — overrides base URL

## Legacy JSON config (`trae_config.json`)

```json
{
  "default_provider": "atomic_chat",
  "model_providers": {
    "atomic_chat": {
      "api_key": "noop",
      "base_url": "http://127.0.0.1:1337/v1",
      "model": "gemma-4-E4B-it-IQ4_XS",
      "max_tokens": 8192,
      "temperature": 0.5,
      "top_p": 1,
      "top_k": 0,
      "max_retries": 10
    }
  }
}
```

## YAML config

See `trae_config.yaml.example` — entries `atomic_chat` under `model_providers` and `atomic_chat_model` under `models`.

Point `agents.trae_agent.model` at `atomic_chat_model` to use Atomic Chat as the agent model.

## Tool calling

Trae Agent enables tools when the model name matches common coding-model patterns (qwen, llama, gemma, etc.). Set `supports_tool_calling: false` on the model in YAML if tools fail against your endpoint.

## Troubleshooting

- **Connection refused** — start Atomic Chat and enable the API server.
- **Model not found** — model id must match `GET /v1/models` exactly.
- **Tools fail** — try a model with tool support or disable `parallel_tool_calls` in config.
