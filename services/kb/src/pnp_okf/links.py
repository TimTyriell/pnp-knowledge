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

    def __init__(
        self,
        concept_ids: Iterable[str],
        names: dict[str, str] | None = None,
        spellings: dict[str, str] | None = None,
    ) -> None:
        """``names`` maps a display name or alias to its concept id.

        The synthesis links to whatever the prose calls a thing, not to its
        concept id — ``npcs/vasul.md`` for ``deities/vharzul``. Without the
        name map those links are simply dropped, which cost the bundle 161
        edges on the v5 run.

        ``spellings`` is ``entity_rules.yaml``'s ``spelling:`` map (mishearing
        -> canon text), applied to prose by :func:`normalize_body` — see
        :func:`apply_spellings`.
        """

        self.ids: set[str] = set(concept_ids)
        self.spellings: dict[str, str] = spellings or {}
        self._by_basename: dict[str, set[str]] = defaultdict(set)
        for cid in self.ids:
            self._by_basename[slugify(cid.rsplit("/", 1)[-1])].add(cid)
        self._by_name: dict[str, set[str]] = defaultdict(set)
        for name, cid in (names or {}).items():
            slug = slugify(name)
            if slug and slug not in self._by_basename:
                self._by_name[slug].add(cid)
        # A first-name link ("lunara" for lunara_velora) resolves only when
        # exactly one concept slug extends it — otherwise it is a guess.
        self._by_prefix: dict[str, set[str]] = defaultdict(set)
        # The model also drops the word separator ("lindolaut"), which no
        # amount of slugifying the target recovers.
        self._by_compact: dict[str, set[str]] = defaultdict(set)
        for cid in self.ids:
            slug = cid.rsplit("/", 1)[-1]
            head = slug.split("_", 1)[0]
            if head != slug:
                self._by_prefix[head].add(cid)
                self._by_compact[slug.replace("_", "")].add(cid)
        for slug, cids in self._by_name.items():
            if "_" in slug:
                self._by_compact[slug.replace("_", "")].update(cids)

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

        # 3. The name the prose uses ("Vasul" -> deities/vharzul). The
        #    directory hint is untrustworthy here — the model guesses the
        #    directory from the name it chose — so a unique name wins outright.
        for table in (self._by_name, self._by_compact, self._by_prefix):
            candidates = table.get(base)
            if not candidates:
                continue
            if len(candidates) == 1:
                return next(iter(candidates))
            if dir_hint:
                preferred = {c for c in candidates if c.startswith(f"{dir_hint}/")}
                if len(preferred) == 1:
                    return next(iter(preferred))

        # 4. Last resort: naive singularization (``cookies`` -> ``cookie``).
        if base.endswith("s"):
            singular = self._by_basename.get(base[:-1])
            if singular and len(singular) == 1:
                return next(iter(singular))

        return None


_BELEGE_HEADING_RE = re.compile(r"^#{1,6}\s*Belege\s*$", re.IGNORECASE | re.MULTILINE)
_LINK_TARGET_RE = re.compile(r"(\]\([^)\s]*\.md\))")


def apply_spellings(body: str, spellings: dict[str, str]) -> str:
    """Rewrite prose occurrences of a mishearing to its GM-ruled canon text.

    ``entity_rules.yaml``'s ``canonical_name:`` only pins a concept's
    *title* — nothing otherwise rewrites synthesized body text, so a
    mishearing that made it into prose survives every re-run untouched even
    after the title is corrected. This closes that gap deterministically, no
    LLM call: a word-boundary substitution applied to prose only.

    Never touches a link *target* (the part inside ``(...)`` ) or anything
    past the ``# Belege`` heading (citations, not prose) — a substitution
    there could mangle a URL or a slug. A link *label* is prose like any
    other, so ``[Willoch](/locations/willauch.md)`` becomes
    ``[Willauch](/locations/willauch.md)``.
    """

    if not spellings:
        return body

    match = _BELEGE_HEADING_RE.search(body)
    head, tail = (body[: match.start()], body[match.start() :]) if match else (body, "")

    # Longer keys first, so a phrase rule ("Festung Zebras") is applied
    # before a bare-token rule ("Zebras") could partially pre-empt it.
    rules = sorted(spellings.items(), key=lambda kv: len(kv[0]), reverse=True)
    # Splitting on link targets keeps every substitution outside `](...)`.
    parts = _LINK_TARGET_RE.split(head)
    for old, new in rules:
        pattern = re.compile(rf"(?<!\w){re.escape(old)}(?!\w)")
        for i in range(0, len(parts), 2):  # even indices are outside targets
            parts[i] = pattern.sub(new, parts[i])
    return "".join(parts) + tail


def normalize_body(
    body: str, index: ConceptIndex, *, drop_unresolved: bool = True, self_id: str | None = None
) -> tuple[str, list[str]]:
    """Rewrite bundle-relative links in ``body`` against ``index``.

    Resolvable links are rewritten to their canonical ``/dir/slug.md`` form.
    Unresolvable links are collected and, when ``drop_unresolved`` is set,
    replaced by their plain-text label so the bundle contains no dead links.
    A link that resolves to ``self_id`` — the document's own concept —  is
    degraded the same way: a body linking its own page (e.g. a stray "Ringtal"
    mention resolving back to the page it's written on) is not a citation,
    it is a self-reference the synthesis should not have produced.

    ``index.spellings`` is applied first (see :func:`apply_spellings`), so
    every caller of ``normalize_body`` — session emission, entity emission,
    and ``pnp validate --fix`` — gets prose-spelling fixes for free.

    Returns ``(new_body, unresolved_targets)``.
    """

    body = apply_spellings(body, index.spellings)
    unresolved: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        label, target = match.group(1), match.group(2)
        cid = index.resolve(target)
        if cid is not None and cid != self_id:
            return f"[{label}](/{cid}.md)"
        if cid is None:
            unresolved.append(target)
        return label if (cid is None and drop_unresolved) or (cid is not None and cid == self_id) else match.group(0)

    return _LINK_RE.sub(_replace, body), unresolved
