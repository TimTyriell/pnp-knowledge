"""Cross-link normalization for emitted OKF concept bodies.

LLM-synthesized bodies frequently contain markdown links that do not resolve
against the actual concept set: placeholder paths (``/pfad/zu/x.md``), German
directory names (``/charaktere/``, ``/orte/``), a missing directory prefix,
inconsistent casing, or plurals. :class:`ConceptIndex` maps such targets back
to a real concept id; :func:`normalize_body` rewrites every link in a body and
reports the ones that still cannot be resolved.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from pnp_okf.models import TYPE_DIR
from pnp_okf.okf import slugify

# Matches any markdown link to a ``.md`` target: bundle-absolute
# (``/dir/slug.md``), document-relative (``../npcs/x.md``, ``./x.md``) or bare
# (``x.md``). The synthesis prompt asks for relative paths while the emitted
# convention is absolute, so a pattern anchored on a leading "/" silently let
# every relative link through unchecked — unnormalized *and* uncounted by
# validation. External URLs are excluded by the scheme guard.
_LINK_RE = re.compile(r"\[([^\]]+)\]\((?!\w+:)([^)\s]*?\.md)\)")

# Valid top-level concept directories (entity types + reserved ``sessions``).
_VALID_DIRS: set[str] = set(TYPE_DIR.values()) | {"sessions"}

# German (or otherwise wrong) directory segments the model tends to invent,
# mapped to their canonical English concept directory.
_DIR_ALIASES: dict[str, str] = {
    "charaktere": "characters",
    "charakter": "characters",
    "personen": "npcs",
    "person": "npcs",
    "nsc": "npcs",
    "nscs": "npcs",
    "orte": "locations",
    "ort": "locations",
    "gegenstaende": "items",
    "gegenstände": "items",
    "gegenstand": "items",
    "objekte": "items",
    "fraktionen": "factions",
    "organisationen": "factions",
    "organisation": "factions",
    "gilden": "factions",
    "ereignisse": "events",
    "ereignis": "events",
    # Deities and domains got their own directories; these used to point at
    # npcs/ and would now silently mis-resolve a god onto an NPC.
    "gottheiten": "deities",
    "goetter": "deities",
    "götter": "deities",
    "gods": "deities",
    "gott": "deities",
    "reiche": "domains",
    "ebenen": "domains",
    "dimensionen": "domains",
    "planes": "domains",
    "player-characters": "characters",
    "player_characters": "characters",
    "spielercharaktere": "characters",
    "pcs": "characters",
    "monsters": "npcs",
    "creatures": "npcs",
    "kreaturen": "npcs",
    "kenku": "npcs",
    "sessionen": "sessions",
    "sitzungen": "sessions",
}


class ConceptIndex:
    """Resolve a link target string to a canonical concept id."""

    def __init__(self, concept_ids: Iterable[str]) -> None:
        self.ids: set[str] = set(concept_ids)
        self._by_basename: dict[str, set[str]] = defaultdict(set)
        for cid in self.ids:
            self._by_basename[slugify(cid.rsplit("/", 1)[-1])].add(cid)

    def resolve(self, target: str) -> str | None:
        """Return the canonical concept id for ``target`` or ``None``.

        ``target`` is a link href such as ``/charaktere/Cookie.md``.
        """

        t = target.strip().lstrip("/")
        if t.endswith(".md"):
            t = t[:-3]
        if not t:
            return None

        parts = t.split("/")
        # Drop leading "." / ".." segments from document-relative hrefs so the
        # directory hint is the concept directory, not the traversal.
        while parts and parts[0] in (".", ".."):
            parts.pop(0)
        if not parts:
            return None
        base_raw = parts[-1]
        base = slugify(base_raw)

        dir_hint: str | None = None
        if len(parts) >= 2:
            d = parts[0].lower()
            d = _DIR_ALIASES.get(d, d)
            if d in _VALID_DIRS:
                dir_hint = d

        # 1. Direct hit against a known concept id (handles casing / hyphens,
        #    e.g. sessions/2025-04-09 or an already-correct link).
        if dir_hint:
            for cand in (f"{dir_hint}/{base_raw}", f"{dir_hint}/{base_raw.lower()}", f"{dir_hint}/{base}"):
                if cand in self.ids:
                    return cand
        elif "/".join(parts) in self.ids:
            return "/".join(parts)

        # 2. Resolve by (slugified) basename, preferring the hinted directory.
        matches = self._by_basename.get(base)
        if matches:
            if dir_hint:
                preferred = {m for m in matches if m.startswith(f"{dir_hint}/")}
                if len(preferred) == 1:
                    return next(iter(preferred))
            if len(matches) == 1:
                return next(iter(matches))
            return None  # ambiguous across directories

        # 3. Last resort: naive singularization (``cookies`` -> ``cookie``).
        if base.endswith("s"):
            singular = self._by_basename.get(base[:-1])
            if singular and len(singular) == 1:
                return next(iter(singular))

        return None


def normalize_body(
    body: str, index: ConceptIndex, *, drop_unresolved: bool = True
) -> tuple[str, list[str]]:
    """Rewrite bundle-relative links in ``body`` against ``index``.

    Resolvable links are rewritten to their canonical ``/dir/slug.md`` form.
    Unresolvable links are collected and, when ``drop_unresolved`` is set,
    replaced by their plain-text label so the bundle contains no dead links.

    Returns ``(new_body, unresolved_targets)``.
    """

    unresolved: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        label, target = match.group(1), match.group(2)
        cid = index.resolve(target)
        if cid is not None:
            return f"[{label}](/{cid}.md)"
        unresolved.append(target)
        return label if drop_unresolved else match.group(0)

    return _LINK_RE.sub(_replace, body), unresolved
