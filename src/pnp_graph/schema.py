"""Pydantic schema the local LLM fills via structured output."""

from typing import Literal

from pydantic import BaseModel, Field


class Character(BaseModel):
    name: str
    player: str | None = None
    # named "role" not "type": a property literally named "type" collides with
    # the JSON-Schema keyword of the same name under DeepSeek's strict-mode
    # grammar — it silently renamed the key to "entity_type" in every tool
    # call, so extraction always failed Pydantic validation (Field required: type).
    role: str = Field(description="PC or NPC")
    is_named_character: bool = Field(  # REQUIRED (no default) = pay-to-mint, like Item/Event
        description="True ONLY for a named, plot-relevant individual (a specific "
        "recurring NPC with a name, e.g. 'Berthold', 'Leandra'). False for generic "
        "adversaries/extras: 'ein Goblin', 'die Wachen', 'Skelett-Nahkämpfer', "
        "'Bugbear-Anführer' — each is a different instance, NOT a stable entity, so "
        "they are NOT nodes (the horde is a Faction, the fight an Event).")
    aliases: list[str] = []
    description: str = Field(
        default="", description="Recurring personality, habits, or quirks — "
        "not one-off happenings, e.g. 'spielt oft Musik, misstraut Fremden'")


class Location(BaseModel):
    name: str
    is_named_location: bool = Field(  # REQUIRED (no default) = pay-to-mint, like Item/Character
        description="True ONLY for a named, macro-structural place — a town, "
        "dungeon, landmark, or region with its own identity (e.g. 'Breschka', "
        "'Goblinlager', 'die Krypta'). False for generic stage-dressing that is "
        "just where a beat happens: 'der Wald', 'ein Baum', 'die Tür', 'der "
        "Raum', 'die Mauer' — those are NOT nodes.")
    description: str = ""


class Item(BaseModel):
    name: str
    is_named_artifact: bool = Field(  # REQUIRED (no default) = pay-to-mint, like Event
        description="True ONLY for a unique, named, plot-significant artifact "
        "(e.g. 'Schwert des Veritas', 'Sigille'). False for generic/consumable "
        "loot: torches, gold, arrows, potions, standard weapons — those are NOT nodes.")
    owner: str | None = None
    status: str = Field(default="", description="e.g. looted, used")


class Quest(BaseModel):
    name: str
    status: str = Field(default="open", description="new, open, or completed")


class Event(BaseModel):
    # "label" not "title": pydantic auto-adds a JSON-Schema "title" annotation to
    # every property (e.g. properties.title.title == "Title") — a field literally
    # named "title" hits the same DeepSeek strict-mode key-collision bug as
    # Character.role above (was silently renamed to "event_name" in tool calls).
    label: str
    summary: str = ""
    participants: list[str] = []
    location: str | None = None
    narrative_significance_reasoning: str = Field(  # REQUIRED (no default) = pay-to-mint
        description="Justify why this scene alters world state (a death, quest "
        "change, ownership change, alliance/betrayal, a major roll outcome). "
        "Name the single most consequential change of the scene — an event that "
        "changes nothing is not a macro-event.")


class Faction(BaseModel):
    name: str
    description: str = ""


class RuleEntity(BaseModel):
    """A game-rules object referenced at the table (class, subclass, ancestry, domain card, feature...)."""

    name: str
    subtype: str = Field(description="Class, Subclass, Ancestry, Community, DomainCard, ClassFeature, Adversary, or System")


class SceneBoundary(BaseModel):
    """One logical scene in a session (docs/evolution/13, WP13.1): a contiguous
    span of transcript segments the semantic-chunking pre-pass groups together
    so extraction sees a whole narrative arc, never a battle split in half."""

    start_segment: int = Field(description="Inclusive index of the first segment in this scene")
    end_segment: int = Field(description="Inclusive index of the last segment in this scene")
    label: str = Field(default="", description="Short scene label, for logging")  # not "title", see Event.label


class SceneSegmentation(BaseModel):
    """The pre-pass output (WP13.1): the whole session partitioned into scenes,
    in order, covering every segment exactly once."""

    scenes: list[SceneBoundary] = []


class Relationship(BaseModel):
    """Arbitrary lore/social/causal connection between two already-extracted entities."""

    subject: str = Field(description="Name of a character, NPC, location, item, quest, event, or faction extracted above")
    predicate: str = Field(description="Short relation type, 1-3 words, UPPER_SNAKE_CASE, e.g. MEMBER_OF, HOSTILE_TO")
    object: str = Field(description="Name of a character, NPC, location, item, quest, event, or faction extracted above")
    confidence: Literal["high", "medium", "low"] = Field(
        description="How directly the transcript supports this relationship: high = stated outright, "
        "medium = reasonably inferred, low = speculative/ambiguous"
    )
    description: str = Field(
        default="", description="Free-text nuance the predicate alone can't carry, e.g. "
        "'trusts him only reluctantly, since the incident in the forest'"
    )
    evidence: int = 0  # chunk index this relationship was extracted from; set programmatically, not by the model


class SceneExtraction(BaseModel):
    """Everything extracted from one scene chunk in a single structured-output
    call (docs/evolution/13, WP13.6): entities, rules, the one capsule macro
    event (WP13.2) and relationships. Supersedes the WP7
    two-pass entity/event split — that split existed to keep a 14B reliable
    on a smaller schema; on the flagship profile (and with scenes now
    pre-segmented, so each call is already scoped to one coherent unit) one
    combined call halves the API calls per session at no quality cost."""

    characters: list[Character] = []
    locations: list[Location] = []
    items: list[Item] = []
    quests: list[Quest] = []
    factions: list[Faction] = []
    rule_entities: list[RuleEntity] = []
    macro_scene_event: Event
    relationships: list[Relationship] = []


class GraphExtraction(BaseModel):
    characters: list[Character] = []
    locations: list[Location] = []
    items: list[Item] = []
    quests: list[Quest] = []
    events: list[Event] = []
    factions: list[Faction] = []
    rule_entities: list[RuleEntity] = []
    relationships: list[Relationship] = []
