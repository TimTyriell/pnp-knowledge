"""Draw a stratified sample of bundle claims for human labelling (B3).

    python claim_sampler.py --n 60 --seed 1234 > tests/data/claims/<date>-1234.yaml

Pure read: the bundle, the transcripts and the *cached* extraction. Nothing
calls DeepSeek. The claim -> citation mapping and the transcript window reuse
the pipeline's own functions (resolve_entities, excerpts_for), so a claim is
checked against the same dialogue the synthesis saw.

Privacy: claim files are committed, so transcript windows are scrubbed before
they are written (scrub_window) and the output is refused if any player first
name survives in a window (assert_no_player_names). Claim sentences are not
scrubbed: each is a verbatim sentence of a committed knowledge/ page, so
scrubbing it hides nothing and only garbles an in-game name that happens to
equal a player's. The scrub is a decision recorded in
docs/plans/B3-claim-level-eval.md, not an accident of this script.
"""

from __future__ import annotations

import argparse
import os
import random
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

from pnp_okf.claims import split_claims  # noqa: E402
from pnp_okf.config import (  # noqa: E402
    DeepSeekConfig,
    Paths,  # noqa: E402
    default_transcript_dir,
)
from pnp_okf.context import _parse_ts, excerpts_for  # noqa: E402
from pnp_okf.extract import load_cached_extraction  # noqa: E402
from pnp_okf.ingest import load_transcripts  # noqa: E402
from pnp_okf.models import CanonicalEntity, MentionRef  # noqa: E402
from pnp_okf.resolve import resolve_entities  # noqa: E402

MIN_PER_TYPE = 5
_CITE = re.compile(r"\[P-\d+\]")
_BELEG = re.compile(r"^(?:\[(P-\d+)\]|\d+\.) Session (\d{4}-\d{2}-\d{2}) @ (\d+:\d+:\d+)", re.M)
_PAREN_LABEL = re.compile(r"^(.+?) \((.+)\)$")
_LINE_LABEL = re.compile(r"^(\[[^\]]+\]) ([^:\n]+): ", re.M)


def scrub_speaker(label: str) -> str:
    """'Marco (Dodo)' -> 'Spieler (Dodo)'; 'SPEAKER_03' -> 'Spieler'.

    The player's name is the part before the parentheses and is always dropped.
    The part in parentheses (character, or 'GM') is kept, so a labeller still
    knows who is speaking in-game.
    """

    m = _PAREN_LABEL.match(label.strip())
    return f"Spieler ({m.group(2)})" if m else "Spieler"


def scrub_names(text: str, names: set[str]) -> str:
    """Replace whole-word player first names with 'Spieler'.

    Labels are not the only place a name survives: players introduce
    themselves in dialogue ("Ich bin Christian"). Only transcript text goes
    through this; claim sentences already live in knowledge/.
    Cost: in a window, an in-game name identical to a player's is scrubbed
    too. The claim beside it keeps the name, so the labeller can still match.
    """

    if not names:
        return text
    alternation = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    return re.sub(rf"\b(?:{alternation})\b", "Spieler", text)


def scrub_window(text: str, names: set[str] = frozenset()) -> str:
    """Apply scrub_speaker to every '[hh:mm:ss] speaker: ...' line, then the names."""

    labelled = _LINE_LABEL.sub(lambda m: f"{m.group(1)} {scrub_speaker(m.group(2))}: ", text)
    return scrub_names(labelled, set(names))


def assert_no_player_names(text: str, names: set[str]) -> None:
    """Fail closed: a single surviving first name blocks the file."""

    hits = []
    for name in sorted(names):
        for line in text.splitlines():
            if re.search(rf"\b{re.escape(name)}\b", line):
                hits.append(f"{name}: {line.strip()[:160]}")
                break
    if hits:
        raise SystemExit("refusing to write, player first name(s) survive:\n  " + "\n  ".join(hits))


def pick_stratified(claims: list[dict], n: int, seed: int, min_per_type: int = MIN_PER_TYPE) -> list[dict]:
    """Draw ``n`` claims: at least ``min_per_type`` per entity type (spread
    across tiers), then fill from the rest. Deterministic for a seed.

    A type with fewer claims than the floor contributes all of them.
    """

    types = {c["type"] for c in claims}
    if types and n < min_per_type * len(types):
        raise ValueError(f"n={n} is below {min_per_type} x {len(types)} types")

    rng = random.Random(seed)
    pool = sorted(claims, key=lambda c: (c["concept"], c["claim"]))
    rng.shuffle(pool)

    by_type: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for i, c in enumerate(pool):
        by_type[c["type"]][c["tier"]].append(i)

    chosen: list[int] = []
    for typ in sorted(by_type):
        queues = [list(by_type[typ][t]) for t in sorted(by_type[typ])]
        taken = 0
        while taken < min_per_type and any(queues):
            for q in queues:
                if q and taken < min_per_type:
                    chosen.append(q.pop(0))
                    taken += 1

    taken_set = set(chosen)
    chosen += [i for i in range(len(pool)) if i not in taken_set][: max(0, n - len(chosen))]
    return [pool[i] for i in chosen[:n]]


def _belege(body: str) -> dict[str, tuple[str, str]]:
    """Citation marker -> (date, timestamp), from the body's Belege list."""

    return {m.group(1): (m.group(2), m.group(3)) for m in _BELEG.finditer(body) if m.group(1)}


def _claims_for_entity(entity: CanonicalEntity, body: str, tmap: dict) -> list[dict]:
    """Claims in one entity body, each tied to exactly one citation.

    A sentence is eligible if it carries a [P-nn] marker that the Belege list
    resolves to one of the entity's mentions, or if the entity has a single
    source (then the sentence has no other place to come from). Anything else
    is not checkable against one window, so it is left out.
    """

    belege = _belege(body)
    out = []
    for sentence in split_claims(body):
        marker = _CITE.search(sentence)
        if marker:
            key = belege.get(marker.group(0)[1:-1])
            if key is None:
                continue
            mentions = [m for m in entity.mentions if (m.date, m.citation_ts) == key]
        elif len(entity.mentions) == 1:
            mentions = entity.mentions
        else:
            continue
        if len(mentions) != 1 or mentions[0].session_id not in tmap:
            continue
        out.append(_record(entity, sentence, mentions[0], tmap))
    return out


def _record(entity: CanonicalEntity, sentence: str, m: MentionRef, tmap: dict) -> dict:
    single = CanonicalEntity(
        concept_id=entity.concept_id, type=entity.type, canonical_name=entity.canonical_name, mentions=[m]
    )
    secs = int(_parse_ts(m.citation_ts) or 0)
    sep = "&" if "?" in m.url else "?"
    return {
        "concept": entity.concept_id,
        "type": entity.type.value,
        "tier": entity.tier,
        "claim": sentence,
        "session": m.session_id,
        "at": m.citation_ts,
        "url_at": f"{m.url}{sep}t={secs}s",
        "window": excerpts_for(single, tmap),
    }


def _player_first_names(transcripts) -> set[str]:
    """First names of the people behind the speaker labels, read from the corpus."""

    names = set()
    for t in transcripts:
        for s in t.segments:
            m = _PAREN_LABEL.match(s.speaker.strip())
            if m and not m.group(1).startswith("Spieler") and m.group(2) != "GM":
                names.add(m.group(1).strip())
    return names


class _Dumper(yaml.SafeDumper):
    pass


def _literal(dumper, data):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_Dumper.add_representer(str, _literal)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--date", default=date.today().isoformat(), help="the 'drawn' stamp in the file")
    args = ap.parse_args(argv)

    # The extraction cache key depends on the model, not on the key; no request
    # is made. from_env() insists on a key, so a placeholder keeps this offline.
    os.environ.setdefault("DEEPSEEK_API_KEY", "unused-offline-sampler")
    cfg = DeepSeekConfig.from_env().for_tier("extract")
    # Paths.resolve falls back to ./transcript when nothing is set, so the
    # transcript default is passed explicitly (same as the pipeline's own).
    paths = Paths.resolve(
        transcript_dir=default_transcript_dir(),
        cache_dir=os.environ.get("PNP_CACHE_DIR") or str(HERE / ".cache"),
    )

    transcripts = load_transcripts(paths.transcript_dir)
    tmap = {t.session_id: t for t in transcripts}
    extractions = {}
    for t in transcripts:
        ex = load_cached_extraction(paths.cache_dir, t, cfg)
        if ex is not None:
            extractions[t.session_id] = ex
    entities = resolve_entities(extractions, tmap, paths.registry_path)

    pool: list[dict] = []
    for entity in entities:
        body_path = paths.bundle_dir / f"{entity.concept_id}.md"
        if not body_path.is_file():
            continue
        text = body_path.read_text(encoding="utf-8")
        body = text.split("\n---\n", 1)[1] if text.startswith("---\n") and "\n---\n" in text else text
        pool += _claims_for_entity(entity, body, tmap)

    drawn = pick_stratified(pool, args.n, args.seed)
    drawn.sort(key=lambda c: (c["type"], c["concept"], _parse_ts(c["at"]) or 0))

    names = _player_first_names(transcripts)
    claims = []
    for i, c in enumerate(drawn, start=1):
        claims.append(
            {
                "id": f"c{i:03d}",
                "concept": c["concept"],
                "type": c["type"],
                "tier": c["tier"],
                "claim": c["claim"],
                "session": c["session"],
                "at": c["at"],
                "url_at": c["url_at"],
                "window": scrub_window(c["window"], names),
                "verdict": "",
                "note": "",
            }
        )

    rendered = yaml.dump(
        {"seed": args.seed, "drawn": args.date, "pool_size": len(pool), "claims": claims},
        Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=10_000,
    )
    assert_no_player_names("\n".join(c["window"] for c in claims), names)
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(rendered)


if __name__ == "__main__":
    main()
