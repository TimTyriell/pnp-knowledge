"""SRD grounding (docs/evolution/05, WP5).

Loads the static, campaign-independent rule reference `data/daggerheart_srd.json`
and provides:
- `preload(driver)` — MERGE every entry as a shared :Entity{type:'RuleEntity'}
  node before any session ingest (idempotent, session-independent).
- `SrdIndex.lookup(surface)` — surface form -> SRD id via name/alias map, so
  resolution links rules references to the ONE shared node instead of minting
  per-session copies.
"""

import json
import logging

from .config import SRD_PATH
from .resolve import normalize

log = logging.getLogger("pnp_graph.srd")


class SrdIndex:
    def __init__(self, path=SRD_PATH):
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"entries": []}
        self.entries: list[dict] = data["entries"]
        self._by_norm: dict[str, str] = {}
        for e in self.entries:
            for surface in (e["name"], *e.get("aliases", [])):
                self._by_norm[normalize(surface)] = e["id"]

    def lookup(self, surface: str) -> str | None:
        return self._by_norm.get(normalize(surface))

    def gazetteer(self) -> list[str]:
        """Canonical rule names, fed into the extraction prompt as a controlled vocab."""
        return [e["name"] for e in self.entries]


def preload(driver, index: SrdIndex) -> None:
    """MERGE all SRD entries as shared RuleEntity nodes (run once per ingest)."""
    with driver.session() as db:
        for e in index.entries:
            db.run(
                "MERGE (n:Entity {id: $id}) "
                "SET n.type = 'RuleEntity', n.name = $name, n.subtype = $subtype, "
                "    n.source = $source, n.srd_ref = $srd_ref, n.domains = $domains, "
                "    n.session_id = 'SRD', n.confidence = 'high'",
                id=e["id"], name=e["name"], subtype=e["subtype"],
                source=e.get("source", "daggerheart-srd"), srd_ref=e.get("srd_ref", ""),
                domains=e.get("domains", []),
            )
    log.info("SRD preloaded: %d RuleEntity nodes", len(index.entries))
