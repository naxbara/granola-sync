"""Tests for ProseMirror JSON to Markdown conversion."""

from granola_sync.converters.prosemirror import ProseMirrorToMarkdown


converter = ProseMirrorToMarkdown()


def test_empty_doc():
    doc = {"type": "doc", "content": []}
    assert converter.convert(doc) == ""


def test_heading_levels():
    for level in [1, 2, 3]:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": level},
                    "content": [{"type": "text", "text": "Title"}],
                }
            ],
        }
        result = converter.convert(doc)
        assert result == f"{'#' * level} Title"


def test_paragraph():
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Hello world"}],
            }
        ],
    }
    assert converter.convert(doc) == "Hello world"


def test_bold_mark():
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "This is "},
                    {"type": "text", "text": "bold", "marks": [{"type": "bold"}]},
                    {"type": "text", "text": " text"},
                ],
            }
        ],
    }
    assert converter.convert(doc) == "This is **bold** text"


def test_italic_mark():
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "emphasis", "marks": [{"type": "italic"}]},
                ],
            }
        ],
    }
    assert converter.convert(doc) == "*emphasis*"


def test_link_mark():
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "click here",
                        "marks": [
                            {"type": "link", "attrs": {"href": "https://example.com"}}
                        ],
                    },
                ],
            }
        ],
    }
    assert converter.convert(doc) == "[click here](https://example.com)"


def test_bold_italic_combined():
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": "both",
                        "marks": [{"type": "bold"}, {"type": "italic"}],
                    },
                ],
            }
        ],
    }
    assert converter.convert(doc) == "***both***"


def test_bullet_list():
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "bulletList",
                "attrs": {"tight": True},
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "Item A"}]}
                        ],
                    },
                    {
                        "type": "listItem",
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "Item B"}]}
                        ],
                    },
                ],
            }
        ],
    }
    result = converter.convert(doc)
    assert "- Item A" in result
    assert "- Item B" in result


def test_ordered_list():
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "orderedList",
                "attrs": {"tight": True, "start": 1},
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "First"}]}
                        ],
                    },
                    {
                        "type": "listItem",
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "Second"}]}
                        ],
                    },
                ],
            }
        ],
    }
    result = converter.convert(doc)
    assert "1. First" in result
    assert "2. Second" in result


def test_nested_list():
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {"type": "paragraph", "content": [{"type": "text", "text": "Parent"}]},
                            {
                                "type": "bulletList",
                                "content": [
                                    {
                                        "type": "listItem",
                                        "content": [
                                            {"type": "paragraph", "content": [{"type": "text", "text": "Child"}]}
                                        ],
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }
    result = converter.convert(doc)
    assert "- Parent" in result
    assert "  - Child" in result


def test_full_sample_document(sample_prosemirror):
    result = converter.convert(sample_prosemirror)

    # Check headings
    assert "# Reuni" in result and "con Cliente BUPA" in result
    assert "## Contexto del Proyecto" in result
    assert "## Pr" in result and "ximos Pasos" in result

    # Check bold
    assert "**KYON XR**" in result

    # Check italic
    assert "*equipo de finanzas*" in result

    # Check link
    assert "[el portal](https://portal.bupa.cl)" in result

    # Check ordered list
    assert "1. Enviar propuesta" in result
    assert "2. Agendar reuni" in result

    # Check combined marks
    assert "***negrita e" in result


def test_empty_paragraph():
    doc = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": []},
        ],
    }
    result = converter.convert(doc)
    assert result == ""


def test_unicode_characters():
    doc = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Presentación técnica — año 2026"}
                ],
            }
        ],
    }
    result = converter.convert(doc)
    assert "Presentación técnica — año 2026" in result
