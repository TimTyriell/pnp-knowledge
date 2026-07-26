"""Relative links must normalize and be validated, not silently pass through.

The synthesis prompt asks for document-relative hrefs ("../npcs/lenra.md")
while the emitted convention is bundle-absolute ("/npcs/lenra.md"). A pattern
anchored on a leading "/" let every relative link bypass both normalization
and validation, so the validator reported "0 broken" over a bundle holding
~1400 unchecked links.
"""

from pnp_okf.links import ConceptIndex, normalize_body


def _index():
    return ConceptIndex(
        ["npcs/lenra", "characters/lindo_laut", "deities/vharzul", "sessions/2025-04-09"]
    )


def test_relative_link_is_normalized_to_absolute():
    body, unresolved = normalize_body("Siehe [Lenra](../npcs/lenra.md) dort.", _index())
    assert body == "Siehe [Lenra](/npcs/lenra.md) dort."
    assert unresolved == []


def test_bare_and_dot_slash_links_resolve():
    body, _ = normalize_body("[L](lenra.md) und [X](./npcs/lenra.md)", _index())
    assert body.count("/npcs/lenra.md") == 2


def test_german_and_stale_directory_aliases_map_to_current_dirs():
    # 'goetter'/'gods' used to alias onto npcs/, which would mis-resolve a god.
    body, unresolved = normalize_body("[V](../goetter/vharzul.md)", _index())
    assert body == "[V](/deities/vharzul.md)"
    body, _ = normalize_body("[V](/gods/vharzul.md)", _index())
    assert body == "[V](/deities/vharzul.md)"
    body, _ = normalize_body("[L](../player-characters/lindo_laut.md)", _index())
    assert body == "[L](/characters/lindo_laut.md)"


def test_unresolvable_relative_link_is_reported_and_dropped():
    body, unresolved = normalize_body("[Ghost](../gods/nonexistent.md)", _index())
    assert body == "Ghost"                      # dead link removed
    assert unresolved == ["../gods/nonexistent.md"]  # and reported


def test_external_urls_are_left_alone():
    src = "[VOD](https://youtube.com/watch?v=x) and [doc](http://a/b.md)"
    body, unresolved = normalize_body(src, _index())
    assert body == src
    assert unresolved == []
