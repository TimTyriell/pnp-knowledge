# T2 — Which table saw it: `teams` on every concept

| | |
|---|---|
| Branch | `feat/teams-per-concept` |
| Base | `origin/main` (after T1 merged) |
| Depends on | T1 (complete episodes.yaml makes the data meaningful; the code works without it) |
| Design | [T00 §4.2](T00-tracking-model.md) |
| Cost | $0 code; ~$0.05 warm re-emit, **HUMAN RUN** |
| Size | S |

## Goal

Every entity concept gets `teams: [A, …]`: the sorted, de-duplicated team
letters of the sessions that cite it. Session concepts get `team_letter: A`.
Everything is derived deterministically from `knowledge/episodes.yaml`; no
LLM is involved.

## Why

Four tables (Team-A, Team-B, Team-C, willauch) play in one shared world. The
bundle can't tell whether Team B has met Xenia Rotkam or only Team A has,
which matters for spoiler-safe recaps (summary service) and for the wiki.

## Steps

### 1. Branch

```bash
git fetch origin && git switch -c feat/teams-per-concept origin/main
```

### 2. `services/kb/src/pnp_okf/episodes.py`: load the `teams:` map

`episodes.yaml` already has:

```yaml
teams:
  Team-A: A
  Team-B: B
  Team-C: C
  willauch: W
```

Make these changes:

1. `Episodes.__init__` gets a third optional parameter,
   `teams: dict[str, Any] | None = None`, stored as
   `self._teams = {str(k): str(v) for k, v in (teams or {}).items()}`.
2. In `Episodes.load`, change the return to
   `return cls(data.get("episodes"), data.get("seasons"), data.get("teams"))`.
3. Add a method below `id_for_url`:

```python
    def team_letter_for_url(self, url: str) -> str | None:
        """Team letter ("A") of the session at *url*, or None.

        episodes.yaml stores the pnp-crawl group name per episode ("Team-A")
        and maps it to a letter under ``teams:``. An episode with no team, or
        a team with no letter, yields None rather than a guess.
        """
        entry = self.for_url(url)
        team = (entry or {}).get("team")
        return self._teams.get(str(team)) if team else None
```

4. Add a module-level function below `citation_labels`:

```python
def teams_for(urls: list[str], episodes: Episodes) -> list[str]:
    """Sorted distinct team letters across *urls* (sessions an entity cites).

    Unlike citation_labels this is not all-or-nothing: a session without a
    team contributes nothing, and the others still count -- "seen by Team A"
    stays true even if one citing session is unlabelled.
    """
    return sorted({t for u in urls if (t := episodes.team_letter_for_url(u))})
```

### 3. `services/kb/src/pnp_okf/emit.py`: write the fields

1. Import `teams_for` next to the existing `Episodes` import:
   `from pnp_okf.episodes import Episodes, teams_for`.
2. `emit_entity` gets a new keyword-only parameter
   `teams: list[str] | None = None`. Add one docstring line: "``teams``
   (T2): team letters of the citing sessions; omitted from frontmatter when
   empty."
3. In `emit_entity`, in the `frontmatter = {...}` literal, add
   `**({"teams": teams} if teams else {}),` directly after the `subtype`
   line.
4. In `emit_sessions`, after the `if episode: frontmatter |= {...}` block,
   add:

```python
        letter = episodes.team_letter_for_url(transcript.url)
        if letter:
            frontmatter["team_letter"] = letter
```

### 4. `services/kb/src/pnp_okf/cli.py`: pass it through

In `_run_pipeline`, in the loop that calls `emit_entity(...)`, add the
argument:

```python
            teams=teams_for([m.url for m in entity.mentions], episodes),
```

Import `teams_for` from `pnp_okf.episodes` where `citation_labels` is
imported.

### 5. Tests

`services/kb/tests/test_episodes.py`, appended:

```python
TEAM_EPISODES = Episodes(
    [
        {"video_id": "umGyKLkefJI", "id": "S1-01-A", "team": "Team-A"},
        {"video_id": "0HyPHao8s_k", "id": "S1-03-B", "team": "Team-B"},
        {"video_id": "zzzzzzzzzzz", "id": "S1-09-X", "team": "Unbekannt"},
    ],
    teams={"Team-A": "A", "Team-B": "B"},
)


def test_team_letter_for_url():
    assert TEAM_EPISODES.team_letter_for_url(URL_A) == "A"
    assert TEAM_EPISODES.team_letter_for_url(URL_B) == "B"
    # A team with no letter in the map yields None, not the raw name.
    assert TEAM_EPISODES.team_letter_for_url(URL_UNKNOWN) is None


def test_teams_for_is_sorted_distinct_and_tolerates_gaps():
    from pnp_okf.episodes import teams_for

    urls = [URL_B, URL_A, URL_B, "https://www.youtube.com/watch?v=nope"]
    assert teams_for(urls, TEAM_EPISODES) == ["A", "B"]
    assert teams_for([], TEAM_EPISODES) == []


def test_load_reads_the_teams_map(tmp_path):
    path = tmp_path / "episodes.yaml"
    path.write_text(
        textwrap.dedent(
            """\
            teams:
              Team-A: A
            episodes:
              - video_id: umGyKLkefJI
                id: S1-01-A
                team: Team-A
            """
        ),
        encoding="utf-8",
    )
    assert Episodes.load(path).team_letter_for_url(URL_A) == "A"
```

`services/kb/tests/test_okf_v02.py`, appended:

```python
def test_teams_written_when_given(tmp_path: Path):
    assert _frontmatter(tmp_path, labels=["P-08"], teams=["A", "B"])["teams"] == ["A", "B"]


def test_teams_omitted_when_empty(tmp_path: Path):
    assert "teams" not in _frontmatter(tmp_path, labels=["P-08"], teams=[])
```

### 6. Verify

```bash
cd services/kb && .venv/Scripts/python.exe -m pytest -q && cd ../.. && ruff check .
```

### 7. Commit and PR

Message: `feat(kb): record which tables saw each concept`

## HUMAN RUN

Run a warm re-emit (same procedure as T1, HUMAN RUN step 2) and commit the
bundle. Spot-check with:

```bash
grep -l "teams:" knowledge/bundle/splitter_des_ewigen/npcs/*.md | wc -l
grep -A2 "^teams:" knowledge/bundle/splitter_des_ewigen/npcs/xenia_rotkam.md
```

Expect Xenia to show `B`. A Team-A-only NPC like Belorus should show `A`.

## Done when

- [ ] Tests green; bundle re-emitted; 5 spot-checks match expectation.
- [ ] Session concepts carry `team_letter` wherever episodes.yaml has a team.

## Out of scope

- API filtering by team (`/concepts?team=A`). Add it when the summary or the
  wiki actually asks for it (T9 decides).
