# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Config files are UTF-8 regardless of the machine's locale.

``open()`` without an explicit ``encoding`` uses the platform's preferred
encoding, which is a legacy codepage on a stock Windows install (cp936 on a
Chinese system, cp1252 on a Western one). A ``trae_config.yaml`` holding any
non-ASCII byte -- a Chinese comment, an accented name in a prompt, an em dash --
then fails to load on those machines while loading fine on Linux/macOS.

Monkeypatching ``locale.getpreferredencoding`` does not reproduce this:
CPython reads the locale encoding at the C level, so ``open()`` ignores the
patched function. Instead ``legacy_default_encoding`` below replaces ``open``
with a shim that supplies a legacy codec exactly where CPython would supply
the locale's -- i.e. only when the caller passed no ``encoding``. Code that
names its encoding is unaffected, so these tests fail on a machine of any
locale when the encoding is missing and pass on a machine of any locale when
it is present.
"""

import builtins
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from trae_agent.utils.config import Config
from trae_agent.utils.legacy_config import LegacyConfig

# A comment and a value that survive UTF-8 but not a legacy codepage.
NON_ASCII_YAML = """\
# 中文注释：模型配置
agents:
  trae_agent:
    enable_lakeview: false
    model: my_model
    max_steps: 42
    tools:
      - bash
model_providers:
  openai:
    api_key: sk-test
    provider: openai
models:
  my_model:
    model_provider: openai
    model: gpt-4o
    max_tokens: 1000
    temperature: 0.5
    top_p: 1
    top_k: 0
    max_retries: 10
    parallel_tool_calls: true
"""

LEGACY_CODEC = "cp936"


@contextmanager
def legacy_default_encoding(codec: str = LEGACY_CODEC):
    """Make encoding-less ``open()`` calls behave as they do under a legacy locale."""
    real_open = builtins.open

    def shim(file, mode="r", *args, **kwargs):
        if "b" not in mode and kwargs.get("encoding") is None and len(args) < 2:
            kwargs["encoding"] = codec
        return real_open(file, mode, *args, **kwargs)

    with patch.object(builtins, "open", shim):
        yield


class TestConfigFileEncoding(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_yaml_config_with_non_ascii_loads_under_legacy_locale(self):
        config_file = self.tmp_path / "trae_config.yaml"
        config_file.write_text(NON_ASCII_YAML, encoding="utf-8")

        with legacy_default_encoding():
            config = Config.create(config_file=str(config_file))

        assert config.trae_agent is not None
        self.assertEqual(config.trae_agent.model.model, "gpt-4o")
        self.assertEqual(config.trae_agent.max_steps, 42)

    def test_ascii_yaml_config_still_loads_under_legacy_locale(self):
        # Guards the fix against regressing the case that already worked.
        config_file = self.tmp_path / "trae_config.yaml"
        config_file.write_text(NON_ASCII_YAML.replace("# 中文注释：模型配置", "# comment"))

        with legacy_default_encoding():
            config = Config.create(config_file=str(config_file))

        assert config.trae_agent is not None
        self.assertEqual(config.trae_agent.model.model, "gpt-4o")

    def test_legacy_json_config_with_non_ascii_is_not_silently_discarded(self):
        # LegacyConfig catches the load error and falls back to defaults, so a
        # decode failure here does not raise -- it silently reverts every
        # setting the user wrote. Assert on the values, not on an exception.
        config_file = self.tmp_path / "trae_config.json"
        config_file.write_text(
            json.dumps(
                {
                    "default_provider": "openai",
                    "max_steps": 42,
                    "model_providers": {
                        "openai": {"api_key": "sk-test", "model": "gpt-4o"},
                    },
                    "备注": "中文配置说明",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        with legacy_default_encoding():
            legacy = LegacyConfig(str(config_file))

        self.assertEqual(legacy.max_steps, 42)
        self.assertEqual(legacy.default_provider, "openai")
        self.assertIn("openai", legacy.model_providers)


if __name__ == "__main__":
    unittest.main()
