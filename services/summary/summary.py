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

KB_URL_DEFAULT = os.environ.get("PNP_KB_URL", "http://127.0.0.1:8070")

SYSTEM_PROMPT = """\
Du schreibst für eine deutschsprachige Daggerheart-Pen-&-Paper-Runde die
Zusammenfassung "Was bisher geschah" vor der nächsten Session.

Regeln:
- Nutze AUSSCHLIESSLICH die bereitgestellten Session-Zusammenfassungen.
  Erfinde nichts, spekuliere nicht, extrapoliere nicht.
- Schreibe kompakt und stimmungsvoll: 2-4 Absätze, dann eine kurze
  Stichpunktliste "Offene Fäden" mit dem, was zuletzt ungelöst blieb.
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


def fetch_sessions(kb_url: str, count: int, as_of: str | None) -> list[dict]:
    """Latest ``count`` session concepts (sorted by date) with full bodies."""

    params = {"type": "Session"}
    if as_of:
        params["as_of"] = as_of
    with httpx.Client(base_url=kb_url, timeout=30) as client:
        listing = client.get("/concepts", params=params).raise_for_status().json()
        # Session concept paths are sessions/<date> — lexical sort = date sort.
        latest = sorted(listing, key=lambda c: c["concept"])[-count:]
        out = []
        for item in latest:
            detail_params = {"as_of": as_of} if as_of else {}
            detail = (
                client.get(f"/concepts/{item['concept']}", params=detail_params)
                .raise_for_status()
                .json()
            )
            out.append(detail)
        return out


def build_messages(
    sessions: list[dict], outlook_context: str | None
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
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def sources_footer(sessions: list[dict], as_of: str | None) -> str:
    lines = ["", "---", "Quellen (Knowledge-Base):"]
    for s in sessions:
        ref = f" @ {as_of}" if as_of else ""
        resource = s["frontmatter"].get("resource", "")
        lines.append(f"- {s['concept']}{ref} ({resource})")
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
        model=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
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
    args = parser.parse_args(argv)

    try:
        sessions = fetch_sessions(args.kb_url, args.sessions, args.as_of)
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

    messages = build_messages(sessions, args.outlook)
    print(call_llm(messages))
    print(sources_footer(sessions, args.as_of))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
