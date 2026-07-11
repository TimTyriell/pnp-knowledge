"""Scene segmentation (docs/evolution/04, WP4).

v1 is deterministic: 1 scene = 1 chunk, seq = chunk index (1-based).
# ponytail: LLM scene-merging (v2, ~5-10 labeled scenes matching the report's
# S01-S07) only if reconcile-report needs 1:1 scene alignment.
"""


def scene_id(session_id: str, seq: int) -> str:
    return f"SCENE_{session_id}_S{seq:02d}"


def scene_entities(session_id: str, n_chunks: int) -> tuple[list[dict], list[dict]]:
    """Scene entity dicts + IN_SESSION edges for one session (resolve/store shape)."""
    session_node_id = f"SESS_{session_id}"
    entities = []
    edges = []
    for seq in range(1, n_chunks + 1):
        sid = scene_id(session_id, seq)
        entities.append({
            "id": sid, "type": "Scene",
            "props": {"name": sid, "seq": seq, "session_id": session_id, "confidence": "high"},
        })
        edges.append({
            "start_id": sid, "end_id": session_node_id, "type": "IN_SESSION",
            "props": {"session_id": session_id, "confidence": "high"},
        })
    return entities, edges
