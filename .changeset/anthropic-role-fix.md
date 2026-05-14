---
"trae-agent": patch
---

### Bug Fixes

- **Anthropic Role Alternation**: Add `_normalize_alternation()` to merge consecutive same-role messages before sending — prevents Anthropic API 400 errors when tool call/result sequences fragment the `user`/`assistant` alternation pattern.
