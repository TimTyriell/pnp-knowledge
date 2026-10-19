from pnp_okf.models import CanonicalEntity, EntityType, MentionRef
from pnp_okf.synthesize import link_targets, render_brief_body


def _e(cid, name, etype=EntityType.CHARACTER, note="n"):
    return CanonicalEntity(concept_id=cid, type=etype, canonical_name=name,
                           mentions=[MentionRef(session_id="s", date="d", url="u", citation_ts="00:00:01", note=note)])


def test_blocked_name_is_not_a_link_target():
    targets = link_targets([_e("characters/krieg", "Krieg")], blocked={"krieg"})
    assert "Krieg" not in targets


def test_blocked_name_stays_plain_text_in_a_brief_body():
    war = _e("domains/splitterwelt", "Splitterwelt", EntityType.DOMAIN, note="Der Krieg zerriss die Welt.")
    body = render_brief_body(war, link_targets([war, _e("characters/krieg", "Krieg")], blocked={"krieg"}))
    assert "[Krieg]" not in body


def test_unblocked_names_still_link():
    war = _e("domains/splitterwelt", "Splitterwelt", EntityType.DOMAIN, note="Lindo Laut kommt.")
    body = render_brief_body(war, link_targets([war, _e("characters/lindo_laut", "Lindo Laut")]))
    assert "[Lindo Laut](characters/lindo_laut.md)" in body
