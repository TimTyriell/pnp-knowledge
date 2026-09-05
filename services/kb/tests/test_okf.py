from __future__ import annotations

import yaml
from pnp_okf.okf import render_document, slugify, write_index


def test_slugify_transliterates_german():
    assert slugify("Lindo Laut") == "lindo_laut"
    assert slugify("Höhle des Zwergs") == "hoehle_des_zwergs"
    assert slugify("Straße 7!") == "strasse_7"
    assert slugify("   ") == "unnamed"


def test_render_document_requires_type():
    try:
        render_document({"title": "x"}, "body")
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected ValueError for missing type")


def test_render_document_roundtrip_frontmatter_order():
    doc = render_document(
        {"title": "T", "type": "Character", "tags": ["a"]}, "# Body\n\ntext"
    )
    assert doc.startswith("---\n")
    fm_block = doc.split("---\n")[1]
    parsed = yaml.safe_load(fm_block)
    # type must be present and first key.
    assert list(parsed.keys())[0] == "type"
    assert parsed["type"] == "Character"


def test_write_index_no_frontmatter(tmp_path):
    path = write_index(
        tmp_path,
        [("Sessions", [("Session 1", "2025-03-26.md", "Auftakt")])],
    )
    content = path.read_text(encoding="utf-8")
    assert not content.startswith("---")
    assert "# Sessions" in content
    assert "* [Session 1](2025-03-26.md) - Auftakt" in content
