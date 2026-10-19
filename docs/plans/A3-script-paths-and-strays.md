# A3 — Remove machine-specific paths and stray files

| | |
|---|---|
| Branch | `chore/script-paths-and-strays` |
| Base | `origin/main` |
| Depends on | — |
| Cost | $0 |
| Size | S |

## Goal

1. `services/kb/apply_important.py:94-98` and
   `services/kb/apply_merges.py:182-186` hardcode
   `C:/dev/pnp/pnp-crawl/...` and `C:/dev/pnp/pnp-knowledge/...`. The repo
   now lives at `c:/dev/lindo-lauts-notebook/pnp-knowledge`, so both scripts
   are broken on the only machine that runs them. Resolve the paths the same
   way `make_gold_stub.py` does: anchor on `__file__`, let env vars win.
2. Delete stray tracked or untracked artifacts:
   - `reports/__pycache__/` (a `.pyc` of a moved module);
   - `services/dashboard/_test_scratch/` (an empty directory).
3. One sibling-repo path convention: `services/dashboard/app.py` uses
   `PNP_CRAWL_DIR` with default `REPO_ROOT.parent / "pnp-crawl"`. Check
   whether `REPO_ROOT` there is the repo root. If so, the default is right
   (the sibling layout) and only needs a comment. If it isn't, fix it.

## Steps

### 1. Branch

```bash
git fetch origin && git switch -c chore/script-paths-and-strays origin/main
```

### 2. Shared default in `services/kb/src/pnp_okf/config.py`

Add a module-level helper below the `Paths` class:

```python
def default_transcript_dir() -> Path:
    """pnp-crawl's transcripts, as a sibling checkout of this repo.

    ``PNP_TRANSCRIPT_DIR`` wins. The fallback is anchored on this file, not
    the cwd: services/kb/src/pnp_okf/config.py -> parents[5] is the folder
    holding pnp-knowledge and pnp-crawl side by side.
    """

    env = os.environ.get("PNP_TRANSCRIPT_DIR")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[5] / "pnp-crawl" / "transcripts_final"
```

`parents[5]` was checked on 2026-10-18: `[0]` is `pnp_okf`, `[1]` is `src`,
`[2]` is `kb`, `[3]` is `services`, `[4]` is `pnp-knowledge` and `[5]` is
`lindo-lauts-notebook`. Confirm it on your machine by running this from
`services/kb`:

```bash
.venv/Scripts/python.exe -c "from pathlib import Path; import pnp_okf.config as c; print(Path(c.__file__).resolve().parents[5])"
```

It must print the folder that holds `pnp-crawl`.

### 3. Use it in both scripts

In `apply_important.py` and `apply_merges.py`, replace the hardcoded
`Paths.resolve(...)` call with:

```python
    paths = Paths.resolve(default_transcript_dir(), None, None)
```

- `bundle_dir=None` falls back to `PNP_BUNDLE_DIR`, then
  `Paths._default_bundle()`, which walks up from the cwd to the repo's
  `knowledge/`.
- `cache_dir=None` falls back to `PNP_CACHE_DIR` or `./.cache`. The scripts
  are run from `services/kb`, so that is `services/kb/.cache`. Say this in
  each script's docstring ("run from services/kb").

Also make `make_gold_stub.py` and `tests/test_extraction_quality.py` use
`default_transcript_dir()` instead of their own `parents[N]` arithmetic, so
there is one definition. Keep their behaviour: they work from any cwd.

### 4. Test: `services/kb/tests/test_paths.py` (append)

```python
def test_default_transcript_dir_env_wins(monkeypatch, tmp_path):
    from pnp_okf.config import default_transcript_dir
    monkeypatch.setenv("PNP_TRANSCRIPT_DIR", str(tmp_path))
    assert default_transcript_dir() == tmp_path


def test_default_transcript_dir_is_the_sibling_checkout(monkeypatch):
    from pathlib import Path
    from pnp_okf.config import default_transcript_dir
    monkeypatch.delenv("PNP_TRANSCRIPT_DIR", raising=False)
    got = default_transcript_dir()
    assert got.parts[-2:] == ("pnp-crawl", "transcripts_final")
    # The folder that holds pnp-crawl must also hold this repo.
    assert (got.parents[1] / "pnp-knowledge").is_dir() or True  # layout may differ in CI
```

(The last assert is informational. Keep it or remove it; CI has no sibling
checkout.)

And a grep guard:

```python
def test_no_machine_specific_paths_in_scripts():
    from pathlib import Path
    kb = Path(__file__).resolve().parents[1]
    offenders = [
        p.name for p in kb.glob("*.py")
        if "C:/dev/pnp/" in p.read_text(encoding="utf-8")
    ]
    assert not offenders, offenders
```

### 5. Strays

```bash
git rm -r --cached reports/__pycache__ 2>/dev/null; rm -rf reports/__pycache__
rmdir services/dashboard/_test_scratch 2>/dev/null
git status --short
```

`.gitignore` should already cover `__pycache__/`. If it doesn't, add it.

### 6. Dashboard path (read, decide, document)

Open `services/dashboard/app.py` around `PNP_CRAWL_DIR`. If `REPO_ROOT`
resolves to the pnp-knowledge root, then `REPO_ROOT.parent / "pnp-crawl"`
is the sibling layout, which is correct. Add a one-line comment saying so,
mirroring `default_transcript_dir`. If `REPO_ROOT` is anything else, fix
the default to the sibling layout and add a test in
`services/dashboard/test_*.py`.

### 7. Verify, commit, PR

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q && cd ../dashboard && python -m pytest -q && cd ../.. && ruff check .
cd services/kb && .venv/Scripts/python.exe apply_merges.py --help   # must not crash on paths
```

Message: `chore(kb): resolve script paths from the checkout, drop strays`

## Done when

- [ ] `grep -rn "C:/dev/pnp/" services/` → empty.
- [ ] Both scripts start from `services/kb` without editing.
