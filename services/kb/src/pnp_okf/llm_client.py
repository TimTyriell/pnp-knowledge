from __future__ import annotations

from openai import OpenAI

from pnp_okf.config import DeepSeekConfig


def build_client(cfg: DeepSeekConfig) -> OpenAI:
    """Create an OpenAI-compatible client pointed at the DeepSeek API."""
    return OpenAI(base_url=cfg.base_url, api_key=cfg.api_key)
