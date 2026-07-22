from __future__ import annotations

import json

from pnp_okf.ingest import load_transcript


def test_load_transcript(tmp_path):
    payload = {
        "video_date": "2025-03-26",
        "video_url": "https://youtu.be/abc",
        "video_title": "Session 1",
        "language": "de",
        "segments": [
            {"start": 4.2, "end": 8.0, "speaker": "Deniz (GM)", "text": "Hallo"},
            {"start": 65.0, "end": 70.0, "speaker": "Tim", "text": "Servus"},
        ],
    }
    path = tmp_path / "2025-03-26_RF_abc.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    transcript = load_transcript(path)
    assert transcript.session_id == "2025-03-26_RF_abc"
    assert transcript.date == "2025-03-26"
    assert transcript.word_count == 2
    dialogue = transcript.render_dialogue()
    assert "[00:00:04] Deniz (GM): Hallo" in dialogue
    assert "[00:01:05] Tim: Servus" in dialogue
