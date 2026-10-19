# A1 — Validate concept paths and git refs in the read-only API

| | |
|---|---|
| Branch | `fix/api-input-validation` |
| Base | `origin/main` |
| Depends on | — |
| Cost | $0 |
| Size | S |

## Goal

Close two input-handling holes in `services/kb/src/pnp_okf/api.py`:

1. **Path traversal.** `resolve_concept` returns any `cid` containing `/`
   unchecked. `BundleReader.read` then builds
   `repo_root / f"{rel_bundle}/{concept_path}.md"`, so
   `GET /concepts/..%2F..%2F..%2Fsomething` reads any `*.md` the process can
   reach. The same string goes into `git show {ref}:{rel}`.
2. **Git option injection.** `as_of`, `since` and `until` go straight into
   `git ls-tree`, `git show` and `git diff`. A value starting with `-` is
   parsed as an option (e.g. `--output=<file>` on `git diff` writes a file).

The API binds to 127.0.0.1, so severity is low. Still, it is a portfolio repo
and the fix is ~30 lines.

## Steps

### 1. Branch

```bash
git fetch origin && git switch -c fix/api-input-validation origin/main
```

### 2. Validators in `api.py`

Below `_VIDEO_ID_RE`, add:

```python
# A concept path is "<dir>/<slug>": one directory, one file stem, nothing that
# can climb out of the bundle. Slugs are slugify() output (okf.py) plus the
# session dates ("sessions/2026-01-20"), so this is the whole alphabet.
_CONCEPT_PATH_RE = re.compile(r"^[a-z]+/[a-z0-9][a-z0-9_-]*$")
# A git ref as a user may pass it: a tag (s26), a branch, a sha, HEAD~3. It
# must never start with "-" -- git would read it as an option (git diff
# --output=<file> writes a file). ".." is rejected because callers build the
# range themselves.
_REF_RE = re.compile(r"^(?!-)[A-Za-z0-9._/~^-]{1,100}$")


def _check_concept_path(cid: str) -> str:
    if not _CONCEPT_PATH_RE.match(cid):
        raise HTTPException(status_code=400, detail=f"Invalid concept path {cid!r}")
    return cid


def _check_ref(ref: str | None) -> str | None:
    if ref is None:
        return None
    if ".." in ref or not _REF_RE.match(ref):
        raise HTTPException(status_code=400, detail=f"Invalid git ref {ref!r}")
    return ref
```

### 3. Apply them

- `BundleReader.resolve_concept`: replace `if "/" in cid: return cid` with
  `if "/" in cid: return _check_concept_path(cid)`.
- `BundleReader.read`: as the first line, `_check_concept_path(concept_path)`.
  This is defence in depth, because `read` is also called from the listing
  loop with paths from disk. For the worktree branch, after building `path`,
  add:
  ```python
            if not path.resolve().is_relative_to(self.bundle_dir):
                raise HTTPException(status_code=404, detail=f"No concept {concept_path}")
  ```
- `BundleReader.concept_paths`: `ref = _check_ref(ref)` at the top.
- `BundleReader.read`: `ref = _check_ref(ref)` at the top.
- `BundleReader.changes`: `since = _check_ref(since)` and
  `until = _check_ref(until)` at the top.

The listing loop in `concept_paths` yields paths like
`sessions/2026-01-20` and `npcs/foo`. Check that every real bundle path
passes `_CONCEPT_PATH_RE` (step 5).

### 4. Tests: append to `services/kb/tests/test_api.py`

```python
def test_traversal_in_concept_path_is_rejected(client: TestClient):
    for bad in ("../README", "npcs/../../x", "npcs/..%2F..%2Fx"):
        r = client.get(f"/concepts/{bad}")
        assert r.status_code in (400, 404), (bad, r.status_code)


def test_ref_starting_with_dash_is_rejected(client: TestClient):
    assert client.get("/changes", params={"since": "--output=x"}).status_code == 400
    assert client.get("/concepts/npcs/hexe", params={"as_of": "-p"}).status_code == 400
    assert client.get("/concepts", params={"as_of": "s01..s02"}).status_code == 400


def test_valid_refs_still_work(client: TestClient):
    assert client.get("/concepts/npcs/hexe", params={"as_of": "s01"}).status_code == 200
    assert client.get("/changes", params={"since": "s01", "until": "HEAD"}).status_code == 200
```

### 5. Regression check against the real bundle

```python
# tests/test_api.py -- bundle-gated, like the other real-bundle tests
from pathlib import Path
import pytest
from pnp_okf.api import _CONCEPT_PATH_RE

_BUNDLE = Path(__file__).resolve().parents[3] / "knowledge" / "bundle" / "splitter_des_ewigen"


@pytest.mark.skipif(not _BUNDLE.exists(), reason="no bundle checked out")
def test_every_real_concept_path_passes_the_validator():
    bad = [
        p.relative_to(_BUNDLE).with_suffix("").as_posix()
        for p in _BUNDLE.rglob("*.md")
        if p.name not in ("index.md", "log.md")
        and not _CONCEPT_PATH_RE.match(p.relative_to(_BUNDLE).with_suffix("").as_posix())
    ]
    assert not bad, bad[:10]
```

The skip reason must be **exactly** `"no bundle checked out"`, so CI's
`PNP_REQUIRE_BUNDLE=1` turns a missing bundle into an error (conftest).

If this test fails on real paths (e.g. uppercase or umlauts), widen the
regex **minimally** to admit them, and say so in the PR. Don't drop the
anchors.

### 6. Verify, commit, PR

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q tests/test_api.py && .venv/Scripts/python.exe -m pytest -q
cd ../.. && ruff check .
```

Message: `fix(api): reject path traversal and option-like git refs`

## Done when

- [ ] All three new behaviour tests and the real-bundle test pass.
- [ ] Existing API tests unchanged and green.
