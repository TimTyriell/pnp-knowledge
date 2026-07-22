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


# Subdirectory (concept-id prefix) for each entity type.
TYPE_DIR: dict[EntityType, str] = {
    EntityType.CHARACTER: "characters",
    EntityType.NPC: "npcs",
    EntityType.LOCATION: "locations",
    EntityType.FACTION: "factions",
    EntityType.ITEM: "items",
    EntityType.EVENT: "events",
}


# Reverse lookup: concept-id prefix -> entity type. Used so a merge that folds
# a mention into a concept in a different directory adopts that directory's
# type (keeping ``type`` and the concept-id prefix consistent).
DIR_TO_TYPE: dict[str, EntityType] = {d: t for t, d in TYPE_DIR.items()}


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
        description="One or two German sentences summarizing what this session "
        "reveals about the entity."
    )
    citation_ts: str = Field(
        description="Timestamp HH:MM:SS of the moment supporting the note."
    )


class SessionExtraction(BaseModel):
    """Structured output produced by the map/extraction stage for a session."""

    recap: str = Field(
        description="A concise German recap (5-10 sentences) of what happened "
        "in this session."
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


class CanonicalEntity(BaseModel):
    """A resolved, deduplicated entity that becomes one OKF concept."""

    concept_id: str  # e.g. "characters/lindo_laut"
    type: EntityType
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    mentions: list[MentionRef] = Field(default_factory=list)
