"""Comment-preserving line patcher for knowledge/entity_rules.yaml.

Every edit the Glossar tab makes touches exactly one line inside one of the
top-level blocks (``merge:``, ``canonical_name:``, and the tool-owned
``alias_block:``). Patching line-by-line instead of round-tripping the whole
document through pyyaml keeps the other ~860 lines of hand-written GM-ruling
comments byte-identical, so a sync's git diff shows exactly the rule that
changed.

``alias_block:`` is the exception: it's entirely tool-owned (nothing hand-
written lives inside it beyond the one header comment above the key, which
sits outside the block and is therefore never touched), so it's simpler and
just as safe to re-serialize that one block wholesale on every edit.
"""

from __future__ import annotations

import difflib
from typing import Any

import yaml

ALIAS_BLOCK_HEADER = (
    "# alias_block: Anzeigenamen, die NICHT mehr als Alias eines Konzepts\n"
    "# erscheinen sollen. Rein kosmetisch: die Zuordnung (merge/never_merge)\n"
    "# bleibt unberuehrt, die Schreibweise verschwindet nur aus Registry,\n"
    "# Frontmatter und Synthese. Geschrieben vom Glossar-Sync.\n"
)


class EditConflict(Exception):
    """An edit that would need a human decision, or is invalid outright."""


def block_bounds(lines: list[str], key: str) -> tuple[int, int] | None:
    """[start, end) of the top-level block ``key:`` — start is the key line
    itself, end is the next line that starts a new top-level key (or EOF).

    Map blocks (``merge:``, ``canonical_name:``) indent every content line
    by 2 spaces. Sequence blocks (``ignore:``, ``important:``) don't — their
    items and interspersed GM-ruling comments sit at column 0 (``- foo``,
    ``# why``), same as this repo's real entity_rules.yaml. A line only
    starts a *new* block when it's an unindented, non-comment, non-list
    ``key:`` line — nothing else ever looks like that.
    """

    start = None
    for i, line in enumerate(lines):
        if line == f"{key}:":
            start = i
            break
    if start is None:
        return None
    j = start + 1
    while j < len(lines):
        line = lines[j]
        if line.strip() == "" or line.startswith((" ", "-", "#")):
            j += 1
            continue
        break
    return start, j


def _last_data_line(lines: list[str], start: int, end: int) -> int:
    """Last non-blank, non-comment line in [start+1, end) — falls back to
    ``start`` (the key line) for an empty block. New entries are inserted
    right after this, so a trailing comment run (which reads as documenting
    whatever comes *next*) stays after the new entry, not before it."""

    last = start
    for k in range(start + 1, end):
        s = lines[k].strip()
        if s and not s.startswith("#"):
            last = k
    return last


def _parse_kv_line(line: str) -> tuple[str, Any] | None:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    try:
        obj = yaml.safe_load(s)
    except yaml.YAMLError:
        return None
    if isinstance(obj, dict) and len(obj) == 1:
        (k, v), = obj.items()
        return str(k), v
    return None


def _dump_line(key: str, value: str, indent: int = 2) -> str:
    text = yaml.safe_dump({key: value}, allow_unicode=True, default_flow_style=False, sort_keys=False)
    return " " * indent + text.rstrip("\n").splitlines()[0]


def _append_new_block(lines: list[str], key: str, header: str | None = None) -> list[str]:
    lines = list(lines)
    if lines and lines[-1].strip() != "":
        lines.append("")
    if header:
        lines.extend(header.splitlines())
    lines.append(f"{key}:")
    return lines


def set_in_block(lines: list[str], block_key: str, sub_key: str, value: str) -> list[str]:
    lines = list(lines)
    bounds = block_bounds(lines, block_key)
    if bounds is None:
        lines = _append_new_block(lines, block_key)
        bounds = block_bounds(lines, block_key)
    start, end = bounds
    for i in range(start + 1, end):
        parsed = _parse_kv_line(lines[i])
        if parsed and parsed[0] == sub_key:
            lines[i] = _dump_line(sub_key, value)
            return lines
    insert_at = _last_data_line(lines, start, end) + 1
    lines.insert(insert_at, _dump_line(sub_key, value))
    return lines


def del_from_block(lines: list[str], block_key: str, sub_key: str) -> list[str]:
    lines = list(lines)
    bounds = block_bounds(lines, block_key)
    if bounds is None:
        return lines
    start, end = bounds
    for i in range(start + 1, end):
        parsed = _parse_kv_line(lines[i])
        if parsed and parsed[0] == sub_key:
            del lines[i]
            return lines
    return lines


def add_to_list(lines: list[str], block_key: str, item: str) -> list[str]:
    """Add ``- item`` to a flat top-level list block (``important:``,
    ``unimportant:``), creating the block if needed. No-op if already
    present."""

    lines = list(lines)
    bounds = block_bounds(lines, block_key)
    if bounds is None:
        lines = _append_new_block(lines, block_key)
        bounds = block_bounds(lines, block_key)
    start, end = bounds
    for i in range(start + 1, end):
        s = lines[i].strip()
        if s.startswith("- ") and s[2:].strip() == item:
            return lines
    insert_at = _last_data_line(lines, start, end) + 1
    lines.insert(insert_at, f"- {item}")
    return lines


def remove_from_list(lines: list[str], block_key: str, item: str) -> list[str]:
    lines = list(lines)
    bounds = block_bounds(lines, block_key)
    if bounds is None:
        return lines
    start, end = bounds
    for i in range(start + 1, end):
        s = lines[i].strip()
        if s.startswith("- ") and s[2:].strip() == item:
            del lines[i]
            return lines
    return lines


def _set_alias_block(lines: list[str], cid: str, add: str | None = None, remove: str | None = None) -> list[str]:
    """Add/remove one display name from ``alias_block:[cid]``, re-serializing
    just that block. Tool-owned, so no hand comments to protect inside it."""

    lines = list(lines)
    bounds = block_bounds(lines, "alias_block")
    if bounds is None:
        lines = _append_new_block(lines, "alias_block", header=ALIAS_BLOCK_HEADER)
        bounds = block_bounds(lines, "alias_block")
    start, end = bounds
    raw = "\n".join(lines[start + 1 : end]).strip()
    data: dict[str, list[str]] = yaml.safe_load(raw) if raw else {}
    data = data or {}
    items = list(data.get(cid) or [])
    if add and not any(i.lower() == add.lower() for i in items):
        items.append(add)
    if remove:
        items = [i for i in items if i.lower() != remove.lower()]
    if items:
        data[cid] = items
    elif cid in data:
        del data[cid]

    if data:
        new_raw = yaml.safe_dump(data, allow_unicode=True, default_flow_style=False, sort_keys=True).rstrip("\n")
        new_block_lines = ["  " + line if line.strip() else line for line in new_raw.splitlines()]
    else:
        new_block_lines = []
    return lines[: start + 1] + new_block_lines + lines[end:]


def apply_edits(
    text: str,
    edits: list[dict[str, Any]],
    rules: dict[str, Any],
    sources: dict[str, list[tuple[str, str]]],
) -> tuple[str, list[str]]:
    """Apply staged glossary edits to the rules file text. Raises
    EditConflict for anything that needs a human decision or is malformed."""

    lines = text.split("\n")
    merge_map = {str(k).strip().lower(): str(v).strip() for k, v in (rules.get("merge") or {}).items()}
    warnings: list[str] = []

    for edit in edits:
        op = edit.get("op")
        cid = str(edit.get("concept_id", "")).strip()
        if not cid:
            raise EditConflict("concept_id fehlt.")

        if op == "rename":
            name = str(edit.get("name", "")).strip()
            if not name:
                raise EditConflict(f"{cid}: Name darf nicht leer sein.")
            lines = set_in_block(lines, "canonical_name", cid, name)

        elif op == "unpin":
            # Removing the pin is safe by construction: with no rule,
            # resolve.py falls back to whatever a transcript mention actually
            # says, it never gets stuck on the old pinned spelling.
            lines = del_from_block(lines, "canonical_name", cid)

        elif op == "set_important":
            important = bool(edit.get("important"))
            if important:
                lines = add_to_list(lines, "important", cid)
                lines = remove_from_list(lines, "unimportant", cid)
            else:
                lines = remove_from_list(lines, "important", cid)
                # important: true baked into a past registry run is a
                # ratchet (resolve.py::_load_important reads it straight
                # back) — unimportant: is the only thing that actually
                # overrides that, so always write it, not just when needed.
                lines = add_to_list(lines, "unimportant", cid)

        elif op == "add_alias":
            alias = str(edit.get("alias", "")).strip()
            if not alias:
                raise EditConflict(f"{cid}: Alias darf nicht leer sein.")
            key = alias.lower()
            existing = merge_map.get(key)
            if existing and existing != cid:
                raise EditConflict(f'"{alias}" ist bereits eine merge-Regel fuer {existing}.')
            lines = set_in_block(lines, "merge", key, cid)
            lines = _set_alias_block(lines, cid, remove=alias)
            merge_map[key] = cid

        elif op == "delete_alias":
            alias = str(edit.get("alias", "")).strip()
            if not alias:
                raise EditConflict(f"{cid}: Alias darf nicht leer sein.")
            known = {n.lower(): src for n, src in sources.get(cid, [])}
            source = known.get(alias.lower())
            if source is None:
                raise EditConflict(f'"{alias}" ist kein bekannter Alias von {cid}.')
            if source == "canonical":
                raise EditConflict(f'"{alias}" ist der Hauptname von {cid} — umbenennen statt loeschen.')
            if source == "merge" and edit.get("unfold_ack"):
                # Explicit confirmation: drop the merge rule itself, not just
                # its display. Mentions of this name form their own concept
                # on the next pipeline run.
                lines = del_from_block(lines, "merge", alias.lower())
                merge_map.pop(alias.lower(), None)
                warnings.append(
                    f'"{alias}" ist keine merge-Regel mehr fuer {cid} — bildet beim naechsten Lauf ein eigenes Konzept.'
                )
            # Default (no unfold_ack, or source == "registry"): hide only.
            # The merge:/identity rules are untouched; only the display name
            # disappears from the registry/bundle via alias_block.
            lines = _set_alias_block(lines, cid, add=alias)

        else:
            raise EditConflict(f"Unbekannte Operation: {op!r}")

    new_text = "\n".join(lines)
    if text.endswith("\n") and not new_text.endswith("\n"):
        new_text += "\n"
    return new_text, warnings


def validate(old_text: str, new_text: str) -> dict[str, Any]:
    """Re-parse the patched text before it's ever written. Raises
    yaml.YAMLError or EditConflict; the caller writes nothing on failure."""

    old_data = yaml.safe_load(old_text) or {}
    new_data = yaml.safe_load(new_text) or {}  # yaml.YAMLError propagates
    missing = set(old_data) - set(new_data)
    if missing:
        raise EditConflict(f"Validierung fehlgeschlagen: Bloecke verschwunden: {sorted(missing)}")

    new_lines = new_text.split("\n")
    bounds = block_bounds(new_lines, "merge")
    if bounds:
        start, end = bounds
        seen: set[str] = set()
        for i in range(start + 1, end):
            parsed = _parse_kv_line(new_lines[i])
            if parsed:
                if parsed[0] in seen:
                    raise EditConflict(f"Doppelter merge-Key nach dem Patch: {parsed[0]}")
                seen.add(parsed[0])
    return new_data


def sync(
    rules_path,
    registry_path,
    edits: list[dict[str, Any]],
    dry_run: bool,
    load_registry,
    entity_name_sources,
) -> dict[str, Any]:
    """Preview or write. ``load_registry``/``entity_name_sources`` are
    injected (glossary.load_registry / glossary.entity_name_sources) so this
    module has no import-time dependency on glossary.py's file layout."""

    raw = rules_path.read_text(encoding="utf-8")
    uses_crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    rules = yaml.safe_load(text) or {}
    registry = load_registry(registry_path)
    sources = entity_name_sources(registry, rules)

    new_text, warnings = apply_edits(text, edits, rules, sources)
    validate(text, new_text)

    diff = "".join(
        difflib.unified_diff(
            text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile="entity_rules.yaml",
            tofile="entity_rules.yaml",
        )
    )

    written = False
    if not dry_run and diff:
        out = new_text.replace("\n", "\r\n") if uses_crlf else new_text
        rules_path.write_text(out, encoding="utf-8", newline="")
        written = True

    return {"ok": True, "diff": diff, "warnings": warnings, "written": written}
