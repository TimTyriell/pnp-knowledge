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


# Where the cache lived before it moved into the bundle repo (C1). Anchored on
# this file: src/pnp_okf/config.py -> parents[2] is services/kb.
LEGACY_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"


# Quality carries the pipeline: extraction is the ceiling for everything
# downstream, and the deep-tier entries are the ones meant to be thorough.
# The long tail of one-mention stubs is supposed to stay short, so it runs on
# the cheaper model.
DEFAULT_MODEL = "deepseek-v4-pro"
DEFAULT_LIGHT_MODEL = "deepseek-v4-flash"


AGENT_PREFIX = "agent:"


def is_agent(model: str) -> bool:
    """True for a model label answered by a Claude/Codex agent, not the API."""
    return model.startswith(AGENT_PREFIX)


@dataclass(frozen=True)
class DeepSeekConfig:
    """DeepSeek API connection settings (OpenAI-compatible endpoint)."""

    base_url: str
    model: str
    api_key: str
    light_model: str = DEFAULT_LIGHT_MODEL
    extract_model: str = DEFAULT_MODEL
    state_model: str = DEFAULT_MODEL
    dedup_model: str = DEFAULT_LIGHT_MODEL
    # Which pipeline step this config serves ("extract", "deep", ...). Set by
    # for_tier(); the agent queue is keyed by it.
    step: str = ""

    @classmethod
    def from_env(cls) -> DeepSeekConfig:
        def env(*names: str, default: str = "") -> str:
            # First non-empty of the names, so PNP_MODEL_<STEP> (what --model
            # sets) wins over the older variable it supersedes.
            for name in names:
                value = os.environ.get(name, "").strip()
                if value:
                    return value
            return default

        base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
        model = env("PNP_MODEL_DEEP", "DEEPSEEK_MODEL", default=DEFAULT_MODEL)
        light = env("PNP_MODEL_STANDARD", "DEEPSEEK_LIGHT_MODEL", default=DEFAULT_LIGHT_MODEL)
        extract = env("PNP_MODEL_EXTRACT", "DEEPSEEK_EXTRACT_MODEL", default=model)
        state = env("PNP_MODEL_STATE", "DEEPSEEK_STATE_MODEL", default=model)
        dedup = env("PNP_MODEL_DEDUP", default=light)
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()

        cfg = cls(
            base_url=base_url,
            model=model,
            api_key=api_key,
            light_model=light,
            extract_model=extract,
            state_model=state,
            dedup_model=dedup,
        )
        # The key is only needed if some step still calls the API.
        if not api_key and not all(is_agent(m) for m in cfg.step_models().values()):
            raise ConfigError("Missing required environment variable: DEEPSEEK_API_KEY")
        return cfg

    def step_models(self) -> dict[str, str]:
        """The model each pipeline step runs on (an API model or an agent label)."""
        return {
            "extract": self.extract_model,
            "deep": self.model,
            "standard": self.light_model,
            "state": self.state_model,
            "dedup": self.dedup_model,
        }

    def for_tier(self, tier: str) -> DeepSeekConfig:
        """Config for one pipeline tier — the strong model only where it pays.

        ``extract`` defaults to the strong model (``DEEPSEEK_MODEL``) and is
        overridable on its own via ``DEEPSEEK_EXTRACT_MODEL``. Extraction is
        roughly a quarter of a rebuild's bill, so whether it can run cheaper
        should be a configuration decision rather than a code change --  but
        moving it also resamples every entity name, so treat a change here as
        a budgeted event (docs/architecture/PIPELINE.md section 6).
        """

        if tier == "extract":
            return replace(self, model=self.extract_model, step=tier)
        if tier == "state":
            return replace(self, model=self.state_model, step=tier)
        if tier == "dedup":
            return replace(self, model=self.dedup_model, step=tier)
        if tier == "deep" or self.model == self.light_model:
            return replace(self, step=tier)
        return replace(self, model=self.light_model, step=tier)


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
    def knowledge_root(self) -> Path:
        return self._knowledge_root

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
    def frozen_dir(self) -> Path:
        """Per-season ground truth (see :mod:`pnp_okf.frozen`). Sibling of the registry."""
        return self._knowledge_root / "frozen"

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

    @staticmethod
    def _default_cache(bundle: Path) -> str:
        """knowledge/cache when a real knowledge root sits behind the bundle.

        The cache is paid, unreproducible output keyed to this campaign, so it is
        versioned with the bundle (private repo) instead of beside the public code.
        Without a registry the root is not a campaign checkout; keep the old
        cwd-relative default so ad-hoc runs never write into a stranger's tree.
        """
        root = bundle.parent.parent if bundle.parent.name == "bundle" else bundle.parent
        if (root / "entity_registry.yaml").is_file():
            return str(root / "cache")
        return "./.cache"

    @classmethod
    def resolve(
        cls,
        transcript_dir: str | os.PathLike[str] | None = None,
        bundle_dir: str | os.PathLike[str] | None = None,
        cache_dir: str | os.PathLike[str] | None = None,
    ) -> Paths:
        transcripts = (
            transcript_dir
            or os.environ.get("PNP_TRANSCRIPT_DIR")
            or default_transcript_dir()
        )
        bundle = (
            bundle_dir
            or os.environ.get("PNP_BUNDLE_DIR")
            or (
                str(Path(os.environ["PNP_KNOWLEDGE_DIR"]).expanduser() / "bundle" / "splitter_des_ewigen")
                if os.environ.get("PNP_KNOWLEDGE_DIR") else None
            )
            or cls._default_bundle()
        )
        cache = cache_dir or os.environ.get("PNP_CACHE_DIR") or cls._default_cache(Path(bundle).expanduser())
        return cls(
            transcript_dir=Path(transcripts).expanduser(),
            bundle_dir=Path(bundle).expanduser(),
            cache_dir=Path(cache).expanduser(),
        )


def default_transcript_dir() -> Path:
    """Shared transcript data inside this repo, unless explicitly overridden."""

    env = os.environ.get("PNP_TRANSCRIPT_DIR")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[4] / "data" / "transcripts_final"
