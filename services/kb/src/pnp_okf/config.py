from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

try:  # optional convenience: load a .env if python-dotenv is present
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass


class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""


# Quality carries the pipeline: extraction is the ceiling for everything
# downstream, and the deep-tier entries are the ones meant to be thorough.
# The long tail of one-mention stubs is supposed to stay short, so it runs on
# the cheaper model.
DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_LIGHT_MODEL = "deepseek-v4-flash"


@dataclass(frozen=True)
class DeepSeekConfig:
    """DeepSeek API connection settings (OpenAI-compatible endpoint)."""

    base_url: str
    model: str
    api_key: str
    light_model: str = DEFAULT_LIGHT_MODEL

    @classmethod
    def from_env(cls) -> "DeepSeekConfig":
        base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
        model = os.environ.get("DEEPSEEK_MODEL", DEFAULT_MODEL).strip()
        light = os.environ.get("DEEPSEEK_LIGHT_MODEL", DEFAULT_LIGHT_MODEL).strip()
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()

        if not api_key:
            raise ConfigError("Missing required environment variable: DEEPSEEK_API_KEY")
        return cls(base_url=base_url, model=model, api_key=api_key, light_model=light)

    def for_tier(self, tier: str) -> "DeepSeekConfig":
        """Config for one synthesis tier — the strong model only where it pays."""

        if tier == "deep" or self.model == self.light_model:
            return self
        return replace(self, model=self.light_model)


@dataclass(frozen=True)
class Paths:
    """Filesystem locations used by the pipeline."""

    transcript_dir: Path
    bundle_dir: Path
    cache_dir: Path

    @property
    def _knowledge_root(self) -> Path:
        """Directory holding the bundle tree's siblings.

        For the monorepo layout ``knowledge/bundle/<name>`` that is
        ``knowledge/``; for a free-standing bundle it is the bundle's parent.
        """

        if self.bundle_dir.parent.name == "bundle":
            return self.bundle_dir.parent.parent
        return self.bundle_dir.parent

    @property
    def registry_path(self) -> Path:
        """Entity registry — the durable record of merges and importance.

        Must resolve next to ``conflicts/`` and ``sources/``: pointing it at
        the wrong place silently discards every hand-curated merge and starts
        a fresh registry instead.
        """

        return self._knowledge_root / "entity_registry.yaml"

    @property
    def episodes_path(self) -> Path:
        """The campaign's episode list — hand-maintained, read-only here.

        Sibling of the bundle tree like the registry, because an Abenteuername
        is curation, not pipeline output (see :mod:`pnp_okf.episodes`).
        """

        return self._knowledge_root / "episodes.yaml"

    @property
    def sources_dir(self) -> Path:
        """World material injected into synthesis (see :mod:`pnp_okf.context`)."""

        return self._knowledge_root / "sources"

    @property
    def conflicts_dir(self) -> Path:
        """Open-conflict queue, sibling of the bundle tree.

        For the monorepo layout ``knowledge/bundle/<name>`` this resolves to
        ``knowledge/conflicts`` (per ARCHITECTURE §3.0); for a free-standing
        bundle it sits next to the bundle directory.
        """

        return self._knowledge_root / "conflicts"

    @staticmethod
    def _default_bundle() -> str:
        """The repo's own bundle, found by walking up from the cwd.

        Every other knowledge path is derived from the bundle (see
        ``_knowledge_root``), so a cwd-relative default silently produces a
        *different* knowledge root for every directory the CLI is run from —
        and a wrong root does not fail, it starts an empty registry and
        regenerates the campaign from scratch with no rules applied. The
        documented workflow is ``cd services/kb && pnp run``, two levels below
        the bundle, so anchoring on the repo makes that command correct
        instead of merely lucky.
        """

        cwd = Path.cwd()
        for parent in [cwd, *cwd.parents]:
            if (parent / "knowledge" / "entity_registry.yaml").is_file():
                return str(parent / "knowledge" / "bundle" / "splitter_des_ewigen")
        return "./bundle/splitter_des_ewigen"

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
            or cls._default_bundle()
        )
        cache = cache_dir or os.environ.get("PNP_CACHE_DIR") or "./.cache"
        return cls(
            transcript_dir=Path(transcripts).expanduser(),
            bundle_dir=Path(bundle).expanduser(),
            cache_dir=Path(cache).expanduser(),
        )
