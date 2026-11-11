# Product development intents

Keep product decisions beside the code they guide. Each feature has its own
directory, starting with `intent.md`.

This workflow follows the human review points in the
[AI-native SDLC playbook](https://claude.com/de/resources/articles/the-ai-native-sdlc-playbook).
It is applied through this conversation; no new automation is installed.

| Stage | Artifact | Review point |
|---|---|---|
| Plan | `intent.md` | User confirms the problem, outcomes, scope, and open choices |
| Design | `spec.md` | User reviews behavior, architecture, and flagged concerns |
| Build preparation | `plan.md` | User accepts the files, sequence, risks, and verification |
| Build and test | Code, tests, `verification.md` | Compare evidence with the accepted outcomes |
| Local delivery | Run instructions and known limits | User exercises the completed flow |
| Maintain | Reproduction evidence and a new or revised intent | Feed observed failures back into the work |

Record acceptance only after the user gives it, including its date and any
conditions. A draft is not acceptance. Keep later artifacts consistent with
the decisions in earlier ones. Save artifacts in Git at the corresponding
review points, staging only files belonging to that change.

The user may delegate routine product and implementation decisions. Record that
delegation in the intent and proceed without repeatedly requesting stage
approvals; retain the artifacts and verification evidence.

Repository guidance in `AGENTS.md` and applicable architecture decisions still
apply. Local delivery is the target for the frontend workbench; hosted
publication is outside its scope.

Current work: [Frontend workbench](frontend-workbench/intent.md).
