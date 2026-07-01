"""Pydantic schema the local LLM fills via structured output."""

from typing import Literal

from pydantic import BaseModel, Field


class Character(BaseModel):
    name: str
    player: str | None = None
    type: str = Field(description="PC or NPC")
    aliases: list[str] = []


class Location(BaseModel):
    name: str
    description: str = ""


class Item(BaseModel):
    name: str
    owner: str | None = None
    status: str = Field(default="", description="e.g. looted, used")


class Quest(BaseModel):
    name: str
    status: str = Field(default="open", description="new, open, or completed")


class Event(BaseModel):
    title: str
    summary: str = ""
    participants: list[str] = []
    location: str | None = None


class Faction(BaseModel):
    name: str
    description: str = ""


class Relationship(BaseModel):
    """Arbitrary lore/social/causal connection between two already-extracted entities."""

    subject: str = Field(description="Name of a character, NPC, location, item, quest, event, or faction extracted above")
    predicate: str = Field(description="Short relation type, 1-3 words, UPPER_SNAKE_CASE, e.g. MEMBER_OF, HOSTILE_TO")
    object: str = Field(description="Name of a character, NPC, location, item, quest, event, or faction extracted above")
    confidence: Literal["high", "medium", "low"] = Field(
        description="How directly the transcript supports this relationship: high = stated outright, "
        "medium = reasonably inferred, low = speculative/ambiguous"
    )
    evidence: int = 0  # chunk index this relationship was extracted from; set programmatically, not by the model


class GraphExtraction(BaseModel):
    characters: list[Character] = []
    locations: list[Location] = []
    items: list[Item] = []
    quests: list[Quest] = []
    events: list[Event] = []
    factions: list[Faction] = []
    relationships: list[Relationship] = []
