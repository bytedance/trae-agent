#!/usr/bin/env python3
"""Smoke-test runner for layered prompt engine debug endpoint

Reads `high_value_prompts_registry_full.yaml` and tries to render a few templates
using the debug endpoint. The script is resilient if the service is down.

Usage:
  python3 additions/smoke_test_render.py --host http://127.0.0.1:8001 --count 5

Outputs JSON logs to /tmp/layered_prompt_smoke_results.json
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlencode

import requests
import yaml

REGISTRY = Path(__file__).resolve().parents[0] / 'high_value_prompts_registry_full.yaml'
OUT_PATH = '/tmp/layered_prompt_smoke_results.json'


def load_registry(path: Path):
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data.get('prompt_catalog', [])


def build_query_vars(entry):
    tpl = entry['variants']['template']
    # minimal sample mapping to exercise common placeholders
    sample = dict(
        input='Sample input for quick smoke test',
        user_question='Please analyze these two short survey summaries',
        assistant1_response='Assistant1 sample',
        assistant2_response='Assistant2 sample',
        code_snippet='def foo(): return 42',
        dataset1='df_survey_a.csv',
        dataset2='df_survey_b.csv',
        documents='docA\ndocB',
    )
    # return the rendered prompt (best-effort)
    try:
        rendered = tpl.format(**sample)
    except Exception:
        rendered = tpl
    return rendered


def run_one(host, entry):
    prompt_text = build_query_vars(entry)
    params = dict(user_input=prompt_text, system_role='analyst')
    url = f"{host.rstrip('/')}/api/layered/debug/prompt?{urlencode(params)}"
    try:
        r = requests.get(url, timeout=8)
    except Exception as e:
        return dict(id=entry['id'], ok=False, error=str(e), url=url)
    try:
        j = r.json()
    except Exception:
        j = dict(text=r.text[:400])
    return dict(id=entry['id'], ok=r.ok, status_code=r.status_code, url=url, resp=j)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='http://127.0.0.1:8001')
    parser.add_argument('--count', type=int, default=6)
    args = parser.parse_args()

    if not REGISTRY.exists():
        print('Registry not found:', REGISTRY, file=sys.stderr)
        sys.exit(2)

    catalog = load_registry(REGISTRY)
    if not catalog:
        print('No prompts found in registry', file=sys.stderr); sys.exit(3)

    results = []
    for entry in catalog[: args.count]:
        info = run_one(args.host, entry)
        print('[%s] -> %s %s' % (entry['id'], info.get('ok'), info.get('error','')))
        results.append(info)

    with open(OUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print('\nSaved results to', OUT_PATH)


if __name__ == '__main__':
    main()
