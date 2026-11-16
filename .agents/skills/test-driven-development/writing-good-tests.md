# Writing Good Tests

**Load this reference when:** writing or changing tests, adding mocks, or
adding cleanup/helper methods for tests.

Adapted for Python/pytest from [obra/superpowers](https://github.com/obra/superpowers) (MIT).

## Overview

A test exists to catch a specific break. Two principles govern everything
here:

```
1. Every test names the break it catches
2. Every test exercises the real thing
```

Strict TDD produces both naturally: a test written first and watched
failing against real code has already proven it can fail, and only earns
a mock when the real dependency proves slow or external.

## Principle 1: Name the Break

Before writing the test body, answer: **what production change should
make this test fail — and is that change a bug or a decision?** A test
earns its place by catching a wrong branch, missing side effect, wrong
argument, boundary case, or broken contract.

**Derive expectations independently.** Use literals and hand-checked
fixtures; parametrized tests with literal expected values are the
preferred shape. An expectation computed by the code under test — or its
helpers — passes no matter what that code does:

```python
# Mirror assertion: the same builder computes both sides — always true
expected = build_search_query(tag="urgent")
assert build_search_query(tag="urgent") == expected

# Hand-derived literal
assert build_search_query(tag="urgent") == 'tag:"urgent"'
```

**No change detectors.** If only intentional decisions can fail a test —
a constant's value, exact message wording, private structure — it fires
on redesign and sleeps through bugs. Test the behavior that depends on
the decision: not `assert MAX_RETRIES == 5` but "a failing call is
retried 5 times and the 6th attempt never happens."

**Behavior, not text.** Asserting that a script, skill, or config
contains an exact line proves only that the source is the source. Run
scripts against controlled inputs and assert outputs, side effects, or
exit codes — e.g. call `pnp_okf.cli.main()` with args and check the
emitted bundle, not that `cli.py` contains a particular string. Prose for
humans (`CLAUDE.md`, `docs/architecture/*`) earns no test at all.

**Your code, not the framework.** Test the contract your code makes at
its boundaries — the FastAPI route you register, the OKF record you
emit, the Cypher/HTTP payload you produce. Upstream mechanics (FastAPI's
routing, pydantic's validation) are their maintainers' tests to write —
don't assert that `TestClient` invokes your handler, assert what your
handler returns. When upstream behavior genuinely surprised you, write
one narrow characterization test naming the assumption.

### Gate Function

```
BEFORE writing the test body:
  Name the production change that would make this test fail.

  Cannot name one            → redesign around an observable behavior
  "The source text changed"  → run the artifact and assert its effects
  Only intentional decisions → change detector; test the behavior
                               that depends on the decision

  Confirm the expected value is derived without the code under test.
  IF it reuses the code's logic or helpers:
    Replace it with a literal or hand-checked fixture
```

## Principle 2: Exercise the Real Thing

**The mock earns no assertions.** A mock assertion passes when the mock
is present and fails when it is absent — it says nothing about the
component. Assert the real component's behavior; if the mock is what you
are checking, unmock it or delete the assertion.

```python
# Real behavior
resp = client.get("/entities/CHAR_lenra")
assert resp.json()["name"] == "Lenra"

# Mock existence — proves nothing
mock_resolve.assert_called_once()
```

**Are we testing the behavior of a mock?** — ask this before trusting the assertion.

**Mock at the right level.** Learn every side effect of the real method
before replacing it; mock the slow or external operation (the DeepSeek
API call in `llm_client.py`) and keep what the test depends on real
(the OKF validation/merge logic that reads the LLM's output). When
unsure, run the test against the real implementation first and observe
what actually needs to happen.

```python
# The mock swallows the state write that dedup later reads
monkeypatch.setattr("pnp_okf.ingest.write_state", lambda *a: None)

# Mock only the slow/external LLM call; the state write stays real
monkeypatch.setattr("pnp_okf.llm_client.call_deepseek", fake_llm_response)
```

**Make doubles specific.** When arguments, call counts, or ordering are
part of the contract, assert them — a `MagicMock()` that accepts anything
verifies nothing. Give each branch (success, error, malformed) its own
fixture or spy, so the wrong branch cannot satisfy the expectation.

**Mirror real data completely.** Mock the complete structure as it exists
in reality — all documented fields — not just the ones your test reads.
Partial mocks fail silently when downstream code reads an omitted field:
the test passes while integration breaks.

**Production classes carry production methods only.** Cleanup that only
tests need lives in `conftest.py` fixtures, never as a `teardown()` on
the production class. Ask: is this method called only from tests? Does
this class own this resource's lifecycle? Wrong answers → test utility.

**Prefer real components over complex mocks.** When mock setup outgrows
the test logic, mocks miss methods the real components have, or tests
break when the mock changes, switch to an integration test with real
components (e.g. FastAPI's `TestClient` against the real app instead of
mocking the router). **Ask: do we need to be using a mock here?**

### Gate Function

```
BEFORE adding a mock or test helper:
  List the real method's side effects; keep the ones the test
  depends on real — mock the slow/external level below them.

  Mock responses mirror the complete real structure.

  A method only tests call lives in a conftest.py fixture, not production.

  About to assert on the mock itself?
    Unmock it or delete the assertion.
```

## Tests Ship With the Implementation

The TDD cycle — failing test, minimal implementation, refactor — is what
"complete" means. Ship the tests the behavior needs and only those:
trivial code and human prose earn none, and a test written to satisfy
process costs maintenance forever.

## The Mutation Check

Before finishing, mentally mutate the production code; at least one test
should fail for each realistic mutation:

- Wrong constant or argument
- Wrong branch handler
- Missing state change or side effect
- Empty or default return
- Missing validation for zero, empty, None, unauthorized, or malformed input

A mutation nothing catches marks the behavior as unprotected — or the
test as tautological.

## Quick Reference

| When you... | Do |
|-------------|-----|
| Write any test | Name the break it catches — a bug, not a decision |
| Build an expected value | Derive it by hand; never with the code under test |
| Test a script or document | Run it / pressure-test its consumer; never grep its text |
| Reach for a dependency test | Test your boundary contract, not their documented mechanics |
| Want to assert on a mocked element | Test the real component, or unmock it |
| Are about to mock something | Learn its side effects; mock the slow/external level |
| Build a mock response | Mirror the real structure completely |
| Need cleanup only tests use | Put it in a `conftest.py` fixture |
| Watch mock setup balloon | Switch to an integration test with real components |
| Finish a test file | Run the mutation check |

## Warning Signs

- Setup and assertion share the same object, guaranteeing equality
- The test can fail only through a crash or missing attribute
- The test fails on every intentional change, never on accidental breakage
- Expected values are hidden behind loops, builders, or helpers
- The test greps source text, or asserts a removed symbol stays removed
- The test would still matter if only the framework remained
- The test exists for coverage, checking no side effect or outcome
- An assertion checks `mock.called` with no argument/count specificity
- A method is called only from test files
- Mock setup is more than half the test, or you can't explain why the mock is needed
- Mocking "just to be safe"
