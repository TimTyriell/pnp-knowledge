from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # optional convenience: load a .env if python-dotenv is present
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass


class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""


@dataclass(frozen=True)
class DeepSeekConfig:
    """DeepSeek API connection settings (OpenAI-compatible endpoint)."""

    base_url: str
    model: str
    api_key: str

    @classmethod
    def from_env(cls) -> "DeepSeekConfig":
        base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
        model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip()
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()

        if not api_key:
            raise ConfigError("Missing required environment variable: DEEPSEEK_API_KEY")
        return cls(base_url=base_url, model=model, api_key=api_key)


@dataclass(frozen=True)
class Paths:
    """Filesystem locations used by the pipeline."""

    transcript_dir: Path
    bundle_dir: Path
    cache_dir: Path

    @property
    def conflicts_dir(self) -> Path:
        """Open-conflict queue, sibling of the bundle tree.

        For the monorepo layout ``knowledge/bundle/<name>`` this resolves to
        ``knowledge/conflicts`` (per ARCHITECTURE §3.0); for a free-standing
        bundle it sits next to the bundle directory.
        """

        if self.bundle_dir.parent.name == "bundle":
            return self.bundle_dir.parent.parent / "conflicts"
        return self.bundle_dir.parent / "conflicts"

    @classmethod
    def resolve(
        cls,
        transcript_dir: str | os.PathLike[str] | None = None,
        bundle_dir: str | os.PathLike[str] | None = None,
        cache_dir: str | os.PathLike[str] | None = None,
    ) -> "Paths":
        transcripts = (
            transcript_dir
            or os.environ.get("PNP_TRANSCRIPT_DIR")
            or "./transcript"
        )
        bundle = (
            bundle_dir
            or os.environ.get("PNP_BUNDLE_DIR")
            or "./bundle/splitter_des_ewigen"
        )
        cache = cache_dir or os.environ.get("PNP_CACHE_DIR") or "./.cache"
        return cls(
            transcript_dir=Path(transcripts).expanduser(),
            bundle_dir=Path(bundle).expanduser(),
            cache_dir=Path(cache).expanduser(),
        )
