"""Tests for the shared HTML → Markdown / plain-text converters."""

from __future__ import annotations

from granola_sync.converters.html import html_to_markdown, html_to_plain_text


def test_headings_and_lists_to_markdown():
    html = "<h2>Acuerdos</h2><ul><li>Uno</li><li>Dos</li></ul>"
    md = html_to_markdown(html)
    assert "## Acuerdos" in md
    assert "- Uno" in md
    assert "- Dos" in md


def test_bold_italic_link_to_markdown():
    html = '<p><strong>Bold</strong> <em>it</em> <a href="https://x.test">link</a></p>'
    md = html_to_markdown(html)
    assert "**Bold**" in md
    assert "*it*" in md
    assert "[link](https://x.test)" in md


def test_entities_unescaped():
    assert "Ben & Jerry" in html_to_markdown("<p>Ben &amp; Jerry</p>")


def test_scripts_and_styles_dropped():
    html = "<style>.x{}</style><p>Hola</p><script>alert(1)</script>"
    md = html_to_markdown(html)
    assert "Hola" in md
    assert "alert" not in md
    assert ".x{" not in md


def test_plain_text_strips_markdown_markers():
    html = "<h2>Título</h2><p><strong>Fuerte</strong> y <a href='u'>enlace</a></p>"
    plain = html_to_plain_text(html)
    assert "**" not in plain
    assert "#" not in plain
    assert "](" not in plain
    assert "Título" in plain
    assert "Fuerte" in plain
    assert "enlace" in plain
