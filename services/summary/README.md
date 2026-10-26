# pnp-summary

Pre-session recap ("Was bisher geschah") + optional outlook for the table,
strictly grounded in the Knowledge-Base API — never invents beyond what the
KB holds, and lists its sources.

```bash
# 1. Start the KB API (separate shell):
cd ../kb && python -m pnp_okf.api

# 2. Generate (needs DEEPSEEK_API_KEY):
python summary.py                          # recap from the last 3 sessions
python summary.py --sessions 5
python summary.py --as-of s26              # historic recap, stable forever
python summary.py --outlook "GM plant: Hinterhalt der Hexe am Pass"
python summary.py --team A                 # only Team A's sessions and threads
```

`--outlook` context shapes only this one output — it is **never sent to or
persisted in the KB** (GM plans are spoilers; see ARCHITECTURE open question
#2). Output is markdown on stdout, paste it into the table chat.

Open threads come from the KB (`GET /concepts?type=Thread&thread_status=open`,
then each concept's frontmatter). The model gets them as ground truth, and
"Offene Fäden" is rendered deterministically after the recap, so the model
never writes that list itself. `--team A` keeps only sessions with
`team_letter: A` and threads whose `teams` include `A`, so a Team-B recap
can't spoil Team-A events. A KB with no threads yields an empty list and no
"Offene Fäden" section.

Tests (offline, no HTTP/LLM): `python -m pytest`.
