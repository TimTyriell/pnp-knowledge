"""Move harvested wiki prose into knowledge/sources/wiki/ without losing its entity.

`pnp-export-data` stage 3 writes the hand-edited KI region of a live wiki page
to `harvest/<concept>.md` — the concept_id is already in the filename
(`characters_lindo_laut.md`). That repo never writes into this one, so a human
carries the text across.

Done by hand, that step is where the binding died: four harvest files were
concatenated into one `Wiki_Team_Text.md` under `## Kaya` / `## Sange` / …
headings, and an `##` heading whose body is empty (a `###` follows it directly)
is dropped by load_sources. All 43 KB of it reached zero entities — including
the four deep-tier player characters it was written about.

This script does the copy mechanically instead: one file per entity, the
concept_id recovered from the filename and written out as an explicit
`<!-- okf: entity=... -->` directive, so routing never depends on a name
happening to match. It also drops what must not reach a synthesis prompt: the
`== Belege ==` section and the bare `[n]` citation markers, which collide with
the prompt's own evidence numbering ("[n]" there means the nth mention of *this*
entity, so a copied number is relabelled into a confidently wrong episode).

Re-runnable: output is derived from harvest/ and overwritten in place.

    python sync_harvest.py [--harvest ../../../pnp-export-data/harvest] [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent  # services/kb
KNOWLEDGE = ROOT.parent.parent / "knowledge"
REGISTRY = KNOWLEDGE / "entity_registry.yaml"
OUT_DIR = KNOWLEDGE / "sources" / "wiki"

# harvest/ is gitignored in pnp-export-data, so this is a local pre-PR step.
DEFAULT_HARVEST = ROOT.parent.parent.parent / "pnp-export-data" / "harvest"

sys.path.insert(0, str(ROOT / "src"))
from pnp_okf.models import DIR_TO_TYPE  # noqa: E402

_BANNER_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_HEADING_RE = re.compile(r"^=+\s*(.+?)\s*=+\s*$", re.MULTILINE)
_MEDIA_RE = re.compile(r"^\[\[(?:Datei|File|Bild|Image):[^\]]*\]\]\s*$", re.MULTILINE)
_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")
_BOLD_RE = re.compile(r"'''(.+?)'''")
_CITE_RE = re.compile(r"[ \t]*\[\d+\]")
_BLANK_RE = re.compile(r"\n{3,}")

# Evidence list harvested along with the prose. Its numbering is the wiki
# page's, not this entity's mention order — never grounding, always a trap.
_BELEGE_HEADINGS = {"belege", "quellen", "einzelnachweise"}


def concept_id_for(stem: str) -> str | None:
    """``characters_lindo_laut`` -> ``characters/lindo_laut``.

    Split at the *first* underscore: no TYPE_DIR value contains one, so the
    split is unambiguous even for a multi-word entity slug.
    """

    prefix, _, rest = stem.partition("_")
    return f"{prefix}/{rest}" if rest and prefix in DIR_TO_TYPE else None


def wikitext_to_markdown(text: str) -> str:
    """Enough of a converter for the KI region: headings, links, bold, media."""

    text = _BANNER_RE.sub("", text)
    text = _MEDIA_RE.sub("", text)
    # Sections nest under the file's own "## <entity>" anchor.
    text = _HEADING_RE.sub(lambda m: f"### {m.group(1)}", text)
    # A link's label is the prose; the target is a wiki page, not a concept id.
    text = _LINK_RE.sub(lambda m: (m.group(2) or m.group(1)).strip(), text)
    text = _BOLD_RE.sub(r"**\1**", text)
    text = _CITE_RE.sub("", text)
    return text


def drop_belege(text: str) -> str:
    """Remove a ``### Belege`` section and everything under it."""

    out, skipping = [], False
    for line in text.splitlines():
        m = re.match(r"^###\s+(.+?)\s*$", line)
        if m:
            skipping = m.group(1).strip().lower() in _BELEGE_HEADINGS
        if not skipping:
            out.append(line)
    return "\n".join(out)


def canonical_names() -> dict[str, str]:
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    return {e["concept_id"]: e["canonical_name"] for e in (data.get("entities") or [])}


def convert(path: Path, names: dict[str, str]) -> tuple[str, str] | None:
    concept_id = concept_id_for(path.stem)
    if not concept_id:
        print(f"  SKIP  {path.name} — no type-dir prefix, cannot recover a concept_id")
        return None
    if concept_id not in names:
        print(f"  SKIP  {path.name} — {concept_id} is not in entity_registry.yaml")
        return None

    body = drop_belege(wikitext_to_markdown(path.read_text(encoding="utf-8"))).strip()
    if not body:
        print(f"  SKIP  {path.name} — nothing left after conversion")
        return None

    doc = (
        f"## {names[concept_id]}\n"
        f"<!-- okf: entity={concept_id} -->\n\n"
        f"Aus dem von Hand bearbeiteten KI-Abschnitt der Wiki-Seite "
        f"(`pnp-export-data/harvest/{path.name}`). Hintergrundwissen für die "
        f"Synthese, kein Kanon-Ruling.\n\n"
        f"{_BLANK_RE.sub(chr(10) * 2, body)}\n"
    )
    return path.name, doc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--harvest", type=Path, default=DEFAULT_HARVEST)
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()

    if not args.harvest.is_dir():
        print(f"no harvest dir at {args.harvest} — nothing to sync")
        return 1

    names = canonical_names()
    written = 0
    print(f"# Harvest sync — {args.harvest}\n")
    for path in sorted(args.harvest.glob("*.md")):
        result = convert(path, names)
        if not result:
            continue
        name, doc = result
        out = OUT_DIR / name
        if args.dry_run:
            print(f"  WOULD WRITE  {out.relative_to(KNOWLEDGE.parent)}  ({len(doc)} chars)")
        else:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            out.write_text(doc, encoding="utf-8")
            print(f"  wrote  {out.relative_to(KNOWLEDGE.parent)}  ({len(doc)} chars)")
        written += 1

    print(f"\n{written} file(s){' (dry run)' if args.dry_run else ''}")
    if written and not args.dry_run:
        print("Run sources_doctor.py to confirm each one reaches its entity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
