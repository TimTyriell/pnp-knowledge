"""Pre-session recap + optional outlook, strictly grounded in the KB API.

Usage (KB API must be running: ``python -m pnp_okf.api`` in services/kb):

    python summary.py                          # recap from the last 3 sessions
    python summary.py --sessions 5
    python summary.py --as-of s26              # historic recap, stable forever
    python summary.py --outlook "GM plant: Hinterhalt der Hexe am Pass"

Grounding contract (ARCHITECTURE §2.3): the recap is composed ONLY from
session concepts fetched from the KB; every source is listed under
"Quellen". ``--outlook`` context is used ephemerally for this one output and
is never sent to or persisted in the KB (spoiler safety — ADR/open q #2).
"""

from __future__ import annotations

import argparse
import os
import sys

import httpx

try:  # optional convenience: load a .env if python-dotenv is present
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional at runtime
    pass

KB_URL_DEFAULT = os.environ.get("PNP_KB_URL", "http://127.0.0.1:8070")

SYSTEM_PROMPT = """\
Du schreibst für eine deutschsprachige Daggerheart-Pen-&-Paper-Runde die
Zusammenfassung "Was bisher geschah" vor der nächsten Session.

Regeln:
- Nutze AUSSCHLIESSLICH die bereitgestellten Session-Zusammenfassungen.
  Erfinde nichts, spekuliere nicht, extrapoliere nicht.
- Schreibe kompakt und stimmungsvoll: 2-4 Absätze.
- Die Liste "Offene Fäden" wird separat aus der Wissensbasis angehängt — schreibe
  KEINE eigene; beziehe dich höchstens im Fließtext darauf.
- Wenn dir Informationen fehlen, lass sie weg, statt zu raten.
"""

OUTLOOK_PROMPT = """\
Zusätzlich: schreibe danach einen kurzen Abschnitt "## Ausblick" (2-4 Sätze)
für die kommende Session. Er darf NUR auf dem folgenden GM-Kontext und den
Session-Zusammenfassungen basieren. Verrate keine Details, die die Spieler
überraschen sollen — formuliere als Andeutung.

GM-Kontext (vertraulich, nur für diesen Ausblick):
{context}
"""


KIND_LABELS = {
    "quest": "Auftrag",
    "mystery": "Rätsel",
    "promise": "Versprechen",
    "debt": "Schuld",
    "deadline": "Frist",
}


def _detail(client: httpx.Client, concept: str, as_of: str | None) -> dict:
    detail_params = {"as_of": as_of} if as_of else {}
    return client.get(f"/concepts/{concept}", params=detail_params).raise_for_status().json()


def fetch_sessions(
    kb_url: str,
    count: int,
    as_of: str | None,
    team: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> list[dict]:
    """Latest ``count`` session concepts (sorted by date) with full bodies.

    With *team*, only that table's sessions (``team_letter``) are kept. The
    filter needs every session's frontmatter, so it runs before ``count``
    (T9: a Team-B recap must not show Team-A sessions).
    """

    params = {"type": "Session"}
    if as_of:
        params["as_of"] = as_of
    with httpx.Client(base_url=kb_url, timeout=30, transport=transport) as client:
        listing = client.get("/concepts", params=params).raise_for_status().json()
        # Session concept paths are sessions/<date> — lexical sort = date sort.
        ordered = sorted(listing, key=lambda c: c["concept"])
        if team:
            details = [_detail(client, item["concept"], as_of) for item in ordered]
            return [d for d in details if d["frontmatter"].get("team_letter") == team][-count:]
        return [_detail(client, item["concept"], as_of) for item in ordered[-count:]]


def fetch_open_threads(
    kb_url: str,
    as_of: str | None,
    team: str | None,
    transport: httpx.BaseTransport | None = None,
) -> list[dict]:
    """Open Thread concepts (T6), oldest first; filtered to one table when *team* is set.

    Returns [] against a KB that predates threads, so the recap still works.
    """

    params = {"type": "Thread", "thread_status": "open"}
    if as_of:
        params["as_of"] = as_of
    with httpx.Client(base_url=kb_url, timeout=30, transport=transport) as client:
        listing = client.get("/concepts", params=params).raise_for_status().json()
        threads = []
        for item in listing:
            fm = _detail(client, item["concept"], as_of)["frontmatter"]
            if team and team not in (fm.get("teams") or []):
                continue
            threads.append({**fm, "concept": item["concept"]})
    threads.sort(key=lambda t: (t.get("opened") or "", t.get("title") or ""))
    return threads


def render_threads(threads: list[dict]) -> str:
    """Deterministic "Offene Fäden" list; the model never writes this one."""
    if not threads:
        return ""
    lines = ["## Offene Fäden"]
    for t in threads:
        label = KIND_LABELS.get(t.get("kind"), t.get("kind") or "Faden")
        seit = f" (seit {t['opened']})" if t.get("opened") else ""
        lines.append(f"- {label}: {t.get('title', t['concept'])}{seit} — {t['concept']}")
    return "\n".join(lines)


def build_messages(
    sessions: list[dict], outlook_context: str | None, threads: list[dict] | None = None
) -> list[dict]:
    system = SYSTEM_PROMPT
    if outlook_context:
        system += "\n" + OUTLOOK_PROMPT.format(context=outlook_context.strip())
    blocks = []
    for s in sessions:
        fm = s["frontmatter"]
        blocks.append(
            f"### Session {fm.get('title', s['concept'])} "
            f"({s['concept']}, Qualität: {fm.get('quality', 'unbekannt')})\n"
            f"{s['body_md']}"
        )
    user = "Session-Zusammenfassungen (chronologisch):\n\n" + "\n\n".join(blocks)
    if threads:
        lines = []
        for t in threads:
            seit = f" (seit {t['opened']})" if t.get("opened") else ""
            lines.append(f"- [{t.get('kind')}] {t.get('title')}{seit}")
        user += (
            "\n\nOffene Fäden laut Wissensbasis (gesichert, nicht verändern):\n"
            + "\n".join(lines)
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def sources_footer(
    sessions: list[dict], as_of: str | None, threads: list[dict] | None = None
) -> str:
    lines = ["", "---", "Quellen (Knowledge-Base):"]
    for s in sessions:
        ref = f" @ {as_of}" if as_of else ""
        resource = s["frontmatter"].get("resource", "")
        lines.append(f"- {s['concept']}{ref} ({resource})")
    for t in threads or []:
        lines.append(f"- {t['concept']}")
    return "\n".join(lines)


def call_llm(messages: list[dict]) -> str:
    from openai import OpenAI  # deferred so offline tests never import it

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY missing (same key as services/kb)")
    client = OpenAI(
        api_key=api_key,
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )
    completion = client.chat.completions.create(
        model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"),
        messages=messages,
        temperature=0.4,
    )
    return (completion.choices[0].message.content or "").strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--kb-url", default=KB_URL_DEFAULT)
    parser.add_argument("--sessions", type=int, default=3)
    parser.add_argument("--as-of", default=None, help="Session tag, e.g. s26")
    parser.add_argument(
        "--outlook",
        default=None,
        help="GM context for a look-ahead section (ephemeral, never persisted)",
    )
    parser.add_argument(
        "--team",
        default=None,
        help="Only this table's sessions and threads, e.g. A (letter, uppercased)",
    )
    args = parser.parse_args(argv)
    team = args.team.upper() if args.team else None

    try:
        sessions = fetch_sessions(args.kb_url, args.sessions, args.as_of, team=team)
        threads = fetch_open_threads(args.kb_url, args.as_of, team)
    except httpx.HTTPError as exc:
        print(
            f"KB API not reachable at {args.kb_url} ({exc}).\n"
            "Start it first: cd services/kb && python -m pnp_okf.api",
            file=sys.stderr,
        )
        return 2
    if not sessions:
        print("No session concepts in the KB.", file=sys.stderr)
        return 1

    messages = build_messages(sessions, args.outlook, threads=threads)
    print(call_llm(messages))
    block = render_threads(threads)
    if block:
        print("\n" + block)
    print(sources_footer(sessions, args.as_of, threads))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
