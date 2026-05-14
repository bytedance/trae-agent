---
"trae-agent": minor
---

### New Features

- **DeepSeek Provider**: Add `DeepSeekClient` via OpenAI-compatible base with default endpoint `https://api.deepseek.com`.
  - Supports V3 (`deepseek-chat`) and R1/V4 (`deepseek-reasoner`) models.
  - `SupportsToolCalling` auto-detection: enabled for non-reasoning models, disabled for R1.
  - Registered in `LLMProvider` enum and `LLMClient` dispatch.
