from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


def format_timestamp(seconds: float) -> str:
    """Render a segment offset (seconds) as ``HH:MM:SS``."""

    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


class EntityType(str, Enum):
    """OKF concept types used for the campaign bundle.

    Values double as the frontmatter ``type`` and the bundle subdirectory
    (pluralized in :data:`TYPE_DIR`).
    """

    CHARACTER = "Character"
    NPC = "NPC"
    LOCATION = "Location"
    FACTION = "Faction"
    ITEM = "Item"
    EVENT = "Event"
    DEITY = "Deity"
    DOMAIN = "Domain"


# Subdirectory (concept-id prefix) for each entity type.
TYPE_DIR: dict[EntityType, str] = {
    EntityType.CHARACTER: "characters",
    EntityType.NPC: "npcs",
    EntityType.LOCATION: "locations",
    EntityType.FACTION: "factions",
    EntityType.ITEM: "items",
    EntityType.EVENT: "events",
    EntityType.DEITY: "deities",
    EntityType.DOMAIN: "domains",
}


# Reverse lookup: concept-id prefix -> entity type. Used so a merge that folds
# a mention into a concept in a different directory adopts that directory's
# type (keeping ``type`` and the concept-id prefix consistent).
DIR_TO_TYPE: dict[str, EntityType] = {d: t for t, d in TYPE_DIR.items()}


# Typed-ID prefix per entity type — the pnp-report vocabulary (CHAR_/NPC_/
# LOC_/FACTION_/EVENT_) shared across the campaign toolchain. The frontmatter
# ``id`` built from these is the canonical merge key across re-runs.
ID_PREFIX: dict[EntityType, str] = {
    EntityType.CHARACTER: "CHAR",
    EntityType.NPC: "NPC",
    EntityType.LOCATION: "LOC",
    EntityType.FACTION: "FACTION",
    EntityType.ITEM: "ITEM",
    EntityType.EVENT: "EVENT",
    EntityType.DEITY: "DEITY",
    EntityType.DOMAIN: "DOMAIN",
}


# Character and NPC are one identity space: the same person is routinely
# extracted as PC in one session and NPC in another, and the observed bundle
# dupes (esterossa vs esterossa_torbhalm) live across these two directories.
PERSON_TYPES = {EntityType.CHARACTER, EntityType.NPC}


# --- Raw transcript ---------------------------------------------------------


class Segment(BaseModel):
    """A single diarized transcript segment."""

    start: float
    end: float
    speaker: str = ""
    text: str = ""

    @property
    def timestamp(self) -> str:
        return format_timestamp(self.start)


class SessionTranscript(BaseModel):
    """One session's transcript plus source metadata."""

    session_id: str
    date: str
    url: str
    title: str = ""
    language: str = "de"
    segments: list[Segment] = Field(default_factory=list)

    @property
    def word_count(self) -> int:
        return sum(len(s.text.split()) for s in self.segments)

    @property
    def unsicher_ratio(self) -> float:
        """Fraction of words spoken by an unmapped ``SPEAKER_XX`` label.

        pnp-crawl leaves below-threshold diarization matches as literal
        ``SPEAKER_XX`` placeholders instead of guessing — that is the
        machine-readable "unsicher" signal.
        """

        total = self.word_count
        if not total:
            return 0.0
        unsure = sum(
            len(s.text.split())
            for s in self.segments
            if s.speaker.startswith("SPEAKER_")
        )
        return unsure / total

    @property
    def quality(self) -> str:
        """Session data-quality score: hoch / mittel / niedrig.

        Derived from the unmapped-speaker ratio at ingest time rather than
        emitted by pnp-crawl — same signal, no cross-repo change needed.
        """

        # ponytail: thresholds are a first guess; tune against the QA audit
        # scripts in pnp-crawl if they disagree.
        ratio = self.unsicher_ratio
        if ratio < 0.05:
            return "hoch"
        if ratio < 0.20:
            return "mittel"
        return "niedrig"

    def render_dialogue(self) -> str:
        """Render segments as ``[HH:MM:SS] Speaker: text`` lines for the LLM."""

        lines = [
            f"[{seg.timestamp}] {seg.speaker}: {seg.text.strip()}"
            for seg in self.segments
            if seg.text.strip()
        ]
        return "\n".join(lines)


# --- Stage 1: extraction (LLM structured output) ----------------------------


class EntityMention(BaseModel):
    """A single mention of an entity found within one session."""

    name: str = Field(description="Name of the entity as it appears in the session.")
    type: EntityType
    note: str = Field(
        description="German summary of what this session reveals about the "
        "entity. Depth depends on the entity's role in THIS session: 4-8 "
        "sentences with concrete details (actions, decisions, dialogue, "
        "changes, relationships) for entities central to the session; 1-2 "
        "sentences for incidental mentions."
    )
    citation_ts: str = Field(
        description="Timestamp HH:MM:SS of the moment supporting the note."
    )


class SessionExtraction(BaseModel):
    """Structured output produced by the map/extraction stage for a session."""

    recap: str = Field(
        description="A detailed German recap (500-900 words) of this session: "
        "an opening plain-prose paragraph with no heading, followed by the "
        "chronological course of play split into scenes, each under a '## ' "
        "heading."
    )
    entities: list[EntityMention] = Field(default_factory=list)


# --- Stage 2: entity resolution ---------------------------------------------


class MentionRef(BaseModel):
    """A back-reference from a canonical entity to a source mention."""

    session_id: str
    date: str
    url: str
    citation_ts: str
    note: str
    quality: str = "hoch"  # source session's transcript quality


class CanonicalEntity(BaseModel):
    """A resolved, deduplicated entity that becomes one OKF concept."""

    concept_id: str  # e.g. "characters/lindo_laut"
    type: EntityType
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    mentions: list[MentionRef] = Field(default_factory=list)
    important: bool = False  # hand-set in the registry; forces the deep tier

    @property
    def entity_id(self) -> str:
        """Typed canonical ID in the pnp-report vocabulary, e.g. ``NPC_HEXE``."""

        slug = self.concept_id.rsplit("/", 1)[-1]
        return f"{ID_PREFIX[self.type]}_{slug.upper()}"

    @property
    def tier(self) -> str:
        """Synthesis depth tier: ``deep``, ``standard`` or ``brief``.

        Mention count alone is a poor importance signal — a pivotal NPC whose
        name was transcribed three different ways shows up as three concepts
        with one mention each. So the deep tier is the union of three rules:
        the hand-set ``important`` flag from the registry (for exactly those
        cases), the small closed types that always matter (player characters
        and deities), and a high mention count.
        """

        if self.important or self.type in ALWAYS_DEEP_TYPES:
            return "deep"
        if len(self.mentions) >= DEEP_MENTION_THRESHOLD:
            return "deep"
        if len(self.mentions) >= 2 or self.type in ALWAYS_STANDARD_TYPES:
            return "standard"
        return "brief"


# Types whose members are always worth a full entry: player characters are the
# spine of the campaign, and deities are a small, lore-heavy closed set.
ALWAYS_DEEP_TYPES = {EntityType.CHARACTER, EntityType.DEITY}

# Small closed sets that deserve more than a stub even on a single mention.
ALWAYS_STANDARD_TYPES = {EntityType.DOMAIN, EntityType.FACTION}

DEEP_MENTION_THRESHOLD = 8
