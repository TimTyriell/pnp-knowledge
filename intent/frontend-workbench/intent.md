# Intent: local campaign knowledge workbench

Status: draft, awaiting user review

Date: 2026-11-03

Product owner: the requesting user

Acceptance: not yet recorded

## Problem

A nontechnical game master should be able to create and maintain knowledge for
their tabletop role-playing campaign without operating a CLI, editing YAML, or
learning Git. The current dashboard exposes pipeline status and glossary
corrections, but does not provide a complete campaign-authoring workflow.

The application should also serve as a reference project demonstrating clear
React/TypeScript architecture and reliable integration with the knowledge
pipeline. Functionality takes priority over visual polish.

## Requirements confirmed by the user

- One game master runs the application locally.
- Manual authoring and import followed by AI-assisted review are equally
  supported in the first release. Neither is an optional later addition.
- The frontend uses React and TypeScript, shadcn/ui, and Zustand for state
  management.
- Core product behavior is developed in discussion with the user.
- Development follows the linked AI-native SDLC playbook, with reviewable
  artifacts and human decisions at the stage boundaries.

## Intended outcomes

1. Create a campaign or open an existing compatible campaign bundle.
2. Manually create, find, edit, and connect campaign entries such as characters,
   NPCs, locations, factions, items, and events.
3. Add session notes or transcripts as sources and request proposed knowledge
   changes from them.
4. Review additions and updates with their supporting evidence, correct or
   reject suggestions, and explicitly apply the accepted changes.
5. Resolve naming ambiguity and contradictions through understandable controls.
6. Preserve authored content and deliberate GM corrections across later imports
   and regeneration.
7. Export a valid, portable OKF bundle and reopen it without losing supported
   content or links.
8. Recover from failed processing or interrupted editing without corrupting the
   last accepted campaign version.

## Repository constraints

- OKF/Markdown in the campaign's private knowledge repository remains the
  canonical knowledge record; see
  [ADR-001](../../docs/architecture/ADR-001-knowledge-layer.md).
- The KB read API remains compatible with the summary and wiki clients.
- The existing dashboard and its glossary workflow remain available.
- Authored input, generated output, and review decisions need explicit ownership.
  Editing generated Markdown alone is not sufficient protection from regeneration.
- Concept identifiers are not assumed stable across model-generated renames;
  read [PIPELINE.md](../../docs/architecture/PIPELINE.md) before designing writes.
- Public source control must not receive real campaign/player data. Fixtures and
  demonstrations use fictional content.
- Existing edits in the working tree belong to the user and must be preserved.

## Technical direction to evaluate in design

The recommendation is to evolve `services/dashboard`, retain Python/FastAPI,
and reuse the Python knowledge pipeline. A Node application server would need a
specific benefit to justify an additional runtime service.

Zustand owns shared client state. A server-data cache, typed API contract, form
validation, and a worker for processing jobs are proposed supporting choices;
their exact dependencies and persistence design are not yet accepted.

The authoring write path must be designed around reviewed changes. A
nontechnical local approval workflow must explicitly reconcile with the current
private-repository PR and session-tag process before implementation.

Local operation does not imply offline AI. The design must explain when source
material is sent to a model provider and require an explicit action before a
paid processing job. Development and automated tests must use fixtures or mocks
and must not invoke paid model calls.

## Proposed first-release boundaries

- Begin source support with pasted text, Markdown, and plain-text transcripts.
- Provide guided entry fields plus a formatted description editor.
- Review AI suggestions per changed entry, highlighting identity decisions and
  contradictions and linking to evidence.
- Build manual authoring first as an implementation increment, then import and
  review against the same knowledge model. Both increments are required before
  calling the first release complete.
- Keep the local installation and startup understandable for a nontechnical GM;
  choose the packaging mechanism during design.

These boundaries are recommendations for review, not recorded user decisions.

## Observable first-release acceptance

- A GM can create a fictional campaign, add two linked entries, close the app,
  reopen it, and recover their saved content.
- An imported session can propose a new entry and an update to an existing one.
  The GM can inspect evidence, edit the update, reject the addition, and apply
  exactly the accepted result.
- Processing a later session preserves the previously authored entry and its
  accepted correction; duplicate names require an explicit identity decision.
- A failed job leaves the last accepted bundle readable and internally valid;
  its status explains what happened and how to retry.
- Exporting and reopening the test campaign preserves its supported content and
  relationships, and the existing bundle validator accepts the result.
- Existing dashboard behavior and KB read consumers pass relevant regression
  checks.
- Primary authoring and review flows work with keyboard navigation and expose
  understandable loading, validation, empty, and error states.

## Outside the first release

Hosted accounts, simultaneous multiplayer editing, audio transcription, a graph
database, interactive maps, AI chat, and wiki publishing implementation. The
separate `pnp-export-data` project continues to own publishing.

## Decisions requested at intent review

1. Accept or revise the proposed first-release boundaries, especially the guided
   editor and review per changed entry.
2. Confirm whether the first release must directly adopt the existing live
   campaign or may initially work with new/imported campaign workspaces. The
   recommendation is new/imported workspaces, followed by an explicit migration
   for the live campaign once round-trip and preservation checks pass.

## Next review points

After intent acceptance, write `spec.md` covering the two user journeys, editing
and review behavior, ownership and persistence, the Python-versus-Node decision,
and the relationship to current ingestion/release rules. After design review,
write `plan.md` with exact implementation steps and tests. Application changes
start after the implementation plan is accepted.
