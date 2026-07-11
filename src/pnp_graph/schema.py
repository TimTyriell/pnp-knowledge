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


class RuleEntity(BaseModel):
    """A game-rules object referenced at the table (class, subclass, ancestry, domain card, feature...)."""

    name: str
    subtype: str = Field(description="Class, Subclass, Ancestry, Community, DomainCard, ClassFeature, Adversary, or System")


class RollEvent(BaseModel):
    """A dice roll and its result."""

    name: str = Field(description="Short label for the roll, e.g. 'Dodo attack roll vs monster'")
    roller: str | None = Field(default=None, description="Character who rolled")
    trait_or_action: str = Field(default="", description="Trait or action rolled, e.g. Agility, attack")
    outcome: str = Field(default="", description="e.g. success_with_hope, success_with_fear, failure, crit")
    target: str | None = Field(default=None, description="What the roll targeted, if anything")
    confidence: Literal["high", "medium", "low"] = "medium"


class Decision(BaseModel):
    """A deliberate, weighty player or GM choice."""

    name: str = Field(description="Short label for the decision")
    decided_by: str | None = Field(default=None, description="Character who decided")
    quote: str = Field(default="", description="Short verbatim quote if available")
    consequence: str = Field(default="", description="What the decision led to")
    confidence: Literal["high", "medium", "low"] = "medium"


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
    rule_entities: list[RuleEntity] = []
    roll_events: list[RollEvent] = []
    decisions: list[Decision] = []
    relationships: list[Relationship] = []
