"""Rewrite entity_rules.yaml's concept-id references to uids (B1, ADR-007).

One-time migration. Line-level and comment-preserving -- never a YAML
round-trip, which would strip every comment and with it the reason for every
rule. The readable concept id stays on the line as a trailing comment:

    important:
    - c_k3m9q2xa  # characters/esterossa

Only the families that *point at* an existing concept are rewritten
(resolve._ID_LIST_FAMILIES, resolve._ID_KEY_FAMILIES, never_merge,
status_rules.drop). merge: and split: values stay concept ids: they define a
target, they don't reference one. A concept id the registry has no uid for is
left as it is and listed on stderr.

    python migrate_rules_to_uids.py            # dry run: print a diff
    python migrate_rules_to_uids.py --write    # apply
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

from pnp_okf.resolve import _ID_KEY_FAMILIES, _ID_LIST_FAMILIES, UID_RE, load_uid_index

ROOT = Path(__file__).resolve().parent  # services/kb
KNOWLEDGE = ROOT.parent.parent / "knowledge"

_LIST_BLOCKS = {*_ID_LIST_FAMILIES, "never_merge", "status_rules"}
_TOP = re.compile(r"^([A-Za-z_]\w*):")
# "- cid", "- - cid", "  - cid" (never_merge groups), with an optional comment.
_ITEM = re.compile(r"^(?P<lead>\s*(?:-\s+)+)(?P<cid>[a-z_]+/[\w-]+)(?P<at>@\S+)?(?P<rest>\s*(?:#.*)?)$")
# "  cid: value" in a key family.
_KEY = re.compile(r"^(?P<lead>\s+)(?P<cid>[a-z_]+/[\w-]+):(?P<rest>.*)$")


def migrate(text: str, cid_to_uid: dict[str, str]) -> tuple[str, list[str]]:
    """(new text, concept ids that had no uid). Pure."""

    out: list[str] = []
    missing: list[str] = []
    block = None
    for line in text.split("\n"):
        top = _TOP.match(line)
        if top:
            block = top.group(1)
            out.append(line)
            continue
        new = line
        m = _ITEM.match(line) if block in _LIST_BLOCKS else None
        k = _KEY.match(line) if block in _ID_KEY_FAMILIES else None
        if m and (block != "status_rules" or m.group("at")):
            cid = m.group("cid")
            uid = cid_to_uid.get(cid)
            if uid:
                new = f"{m.group('lead')}{uid}{m.group('at') or ''}{_with_cid(m.group('rest'), cid)}"
            else:
                missing.append(cid)
        elif k:
            cid = k.group("cid")
            uid = cid_to_uid.get(cid)
            if uid:
                new = f"{k.group('lead')}{uid}:{_with_cid(k.group('rest'), cid)}"
            else:
                missing.append(cid)
        out.append(new)
    return "\n".join(out), missing


def _with_cid(rest: str, cid: str) -> str:
    """Append ``# cid`` as the line's comment, keeping any comment already there."""

    body, hash_, comment = rest.partition("#")
    if hash_:
        return f"{body.rstrip()}  # {cid} --{comment}" if body.strip() else f"  # {cid} --{comment}"
    return f"{rest.rstrip()}  # {cid}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--knowledge", type=Path, default=KNOWLEDGE)
    ap.add_argument("--write", action="store_true", help="apply (default: print a diff)")
    args = ap.parse_args(argv)

    rules_path = args.knowledge / "entity_rules.yaml"
    index = load_uid_index(args.knowledge / "entity_registry.yaml")
    if not index:
        print("The registry has no uids yet: run a warm `pnp run` with B1 first.", file=sys.stderr)
        return 1
    cid_to_uid = {cid: uid for uid, cid in index.items() if UID_RE.match(uid)}

    raw = rules_path.read_text(encoding="utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    new, missing = migrate(text, cid_to_uid)
    for cid in sorted(set(missing)):
        print(f"no uid (left as concept id): {cid}", file=sys.stderr)
    if not args.write:
        sys.stdout.writelines(difflib.unified_diff(
            text.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile="entity_rules.yaml", tofile="entity_rules.yaml (uids)",
        ))
        return 0
    rules_path.write_text(new.replace("\n", "\r\n") if crlf else new, encoding="utf-8", newline="")
    print(f"rewrote {rules_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
