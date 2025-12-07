# High-value prompts additions

This folder contains additional handcrafted and curated prompts collected from the last year's data and project artifacts.

Files:
- high_value_prompts_registry.yaml — small example (partial)
- high_value_prompts_registry_full.yaml — full auto-generated registry (50 prompts, each with short/detailed/template variants)

How to use
1. Inspect the file to find prompt IDs and template variants.
2. To test rendering locally (without starting the service), use a sample renderer script that fills placeholders and prints the final prompt.

Example quick render using Python:

```bash
python3 - <<'PY'
from ruamel.yaml import YAML
yaml=YAML()
with open('additions/high_value_prompts_registry_full.yaml',encoding='utf-8') as f:
    data=yaml.load(f)
entry=data['prompt_catalog'][0]
print('ID:', entry['id'])
print('Short:\n', entry['variants']['short'])
print('\nTemplate (render sample):\n', entry['variants']['template'].format(input='Explain X', assistant1_response='A1', assistant2_response='A2'))
PY
```

How to add to production prompt registry
- Option A (recommended): Keep additions in `additions/` and modify your main loader to merge files from that directory. This is lower-risk and supports staged de
ployment.                                                                                                                                                         - Option B: Copy selected entries into `prompts.yaml` under an appropriate category and deploy.

If you'd like, I can:
- Create a PR that adds these entries to your `prompts.yaml` (one-by-one or as a merged section), or
- Create a script that loads the YAML and calls `/api/layered/debug/prompt` for smoke testing (requires the service running locally or on a host).
