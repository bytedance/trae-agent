"""Multimodal image loading for trae-agent."""
from __future__ import annotations

import base64
import mimetypes
from pathlib import Path


def load_images(paths: list[str]) -> list[dict]:
    """Load image files and return them as content parts for the LLM API.

    Returns a list of dicts with ``type`` and ``image_url`` fields, suitable
    for OpenAI-compatible multimodal APIs.
    """
    images = []
    for p in paths:
        path = Path(p).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")
        mime, _ = mimetypes.guess_type(str(path))
        if not mime or not mime.startswith("image/"):
            raise ValueError(f"Unsupported file type: {path.suffix}")
        data = path.read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        images.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:{mime};base64,{b64}",
            },
        })
    return images
