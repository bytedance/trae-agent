# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Image generation tool — supports multiple backends (SiliconFlow, OpenAI, Doubao)."""

import base64
import os
from datetime import datetime
from pathlib import Path
from typing_extensions import override

import openai

from trae_agent.tools.base import Tool, ToolCallArguments, ToolExecResult, ToolParameter
from trae_agent.utils.output_manager import generate_output_path


class ToolError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ImageGenTool(Tool):
    """Generate images from text prompts.

    Supported backends (set via IMAGE_GEN_PROVIDER env var):
    - siliconflow (default): SiliconFlow 免费图片生成, 支持 Flux/Stable Diffusion
    - openai: OpenAI DALL-E 3
    - doubao: 火山引擎 Doubao Seedream (需要单独开通图片生成 endpoint)

    Usage:
        trae-cli run "画一只猫"
        IMAGE_GEN_PROVIDER=openai trae-cli run "生成风景图"
    """

    def __init__(self, model_provider: str | None = None):
        super().__init__(model_provider)
        self._client: openai.OpenAI | None = None
        self._model: str = ""

    def _ensure_client(self):
        if self._client is not None:
            return

        provider = os.environ.get("IMAGE_GEN_PROVIDER", "siliconflow").lower()

        if provider == "siliconflow":
            api_key = os.environ.get("SILICONFLOW_API_KEY", "")
            if not api_key:
                raise ToolError(
                    "SiliconFlow requires SILICONFLOW_API_KEY env var. "
                    "Get free key at: https://cloud.siliconflow.cn/"
                )
            self._client = openai.OpenAI(
                api_key=api_key,
                base_url="https://api.siliconflow.cn/v1",
            )
            self._model = os.environ.get("IMAGE_GEN_MODEL", "black-forest-labs/FLUX.1-schnell")

        elif provider == "openai":
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key:
                raise ToolError("OpenAI requires OPENAI_API_KEY for DALL-E image generation.")
            self._client = openai.OpenAI(api_key=api_key)
            self._model = os.environ.get("IMAGE_GEN_MODEL", "dall-e-3")

        elif provider == "doubao":
            api_key = os.environ.get("DOUBAO_API_KEY", "")
            base_url = "https://ark.cn-beijing.volces.com/api/v3"
            if not api_key:
                try:
                    from trae_agent.utils.config import Config
                    config = Config.create(config_file="trae_config.yaml")
                    if config.trae_agent:
                        api_key = config.trae_agent.model.model_provider.api_key
                        base_url = config.trae_agent.model.model_provider.base_url or base_url
                except Exception:
                    pass
            if not api_key:
                raise ToolError("Doubao requires DOUBAO_API_KEY or config in trae_config.yaml.")
            self._client = openai.OpenAI(api_key=api_key, base_url=base_url)
            self._model = os.environ.get("IMAGE_GEN_MODEL", "doubao-seedream-3.0")
        else:
            raise ToolError(f"Unknown IMAGE_GEN_PROVIDER: {provider}. Use: siliconflow, openai, doubao")

    @override
    def get_name(self) -> str:
        return "image_gen"

    @override
    def get_description(self) -> str:
        return """Generate an image from a text description.
The generated image is saved to a file and its path is returned.
Use this tool when the user asks to create, generate, draw, or design an image.
Examples: "画一个登录页面的线框图", "生成一张日落风景图", "create a logo for my startup" """

    @override
    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="prompt",
                type="string",
                description="Detailed text description of the image to generate.",
                required=True,
            ),
            ToolParameter(
                name="output_path",
                type="string",
                description="File path to save the generated image. Defaults to ./generated_<timestamp>.png",
                required=False,
            ),
            ToolParameter(
                name="size",
                type="string",
                description="Image size. Options: '1024x1024', '1792x1024', '1024x1792'. Default: '1024x1024'",
                required=False,
            ),
        ]

    @override
    async def execute(self, arguments: ToolCallArguments) -> ToolExecResult:
        prompt = str(arguments.get("prompt", ""))
        if not prompt:
            return ToolExecResult(error="prompt is required", error_code=-1)

        output_path = str(arguments.get("output_path", ""))
        size = str(arguments.get("size", "1024x1024"))

        try:
            self._ensure_client()

            response = self._client.images.generate(
                model=self._model,
                prompt=prompt,
                size=size,
                n=1,
            )

            image_data = response.data[0]
            image_url = getattr(image_data, "url", None)
            image_b64 = getattr(image_data, "b64_json", None)

            # Use output manager to organize files by project on Desktop
            if output_path:
                out = Path(output_path)
                out.parent.mkdir(parents=True, exist_ok=True)
            else:
                out = generate_output_path(extension=".png")

            if image_b64:
                out.write_bytes(base64.b64decode(image_b64))
            elif image_url:
                import urllib.request
                urllib.request.urlretrieve(image_url, str(out))
            else:
                return ToolExecResult(error="No image data in API response", error_code=-1)

            provider = os.environ.get("IMAGE_GEN_PROVIDER", "siliconflow")
            return ToolExecResult(
                output=f"Image saved to: {out.resolve()}\nPrompt: {prompt}\nSize: {size}\nProvider: {provider}"
            )

        except openai.BadRequestError as e:
            return ToolExecResult(error=f"Image generation failed: {e}", error_code=-1)
        except Exception as e:
            return ToolExecResult(error=f"Image generation error: {e}", error_code=-1)
