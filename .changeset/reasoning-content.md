---
"trae-agent": minor
---

### New Features

- **Reasoning Content Tracking**: `LLMMessage` carries an optional `reasoning_content: str | None` field for chain-of-thought tracing in reasoning models (DeepSeek R1/V4, OpenAI o1/o3).
  - `OpenAICompatibleClient` extracts `reasoning_content` from both streaming and non-streaming responses.
  - `_is_reasoning_model()` auto-detects o1/o3/R1 models for correct token parameter selection (`max_completion_tokens` vs `max_tokens`).
