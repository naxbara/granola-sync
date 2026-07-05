"""HTML → Markdown / plain-text conversion for legacy Granola panel content.

Granola's older panels store their AI summary as shallow HTML (h1-6, ul/ol/li,
p, br, strong/b, em/i, a). These are best-effort regex converters — not a full
HTML parser — matched to that consistently-shallow structure. Both the Obsidian
(.md) and exporter (.txt) pipelines share them so the two never diverge.
"""

from __future__ import annotations

import html as _html
import re

from .prosemirror import strip_markdown


def html_to_markdown(content: str) -> str:
    """Convert shallow HTML to Markdown (headings, lists, bold/italic, links)."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    for level in range(1, 7):
        text = re.sub(
            rf"<h{level}[^>]*>(.*?)</h{level}>",
            lambda m, level=level: f"\n{'#' * level} {m.group(1)}\n",
            text,
            flags=re.DOTALL | re.IGNORECASE,
        )

    text = re.sub(r"<li[^>]*>", "- ", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?[ou]l[^>]*>", "\n", text, flags=re.IGNORECASE)

    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<p[^>]*>", "", text, flags=re.IGNORECASE)

    text = re.sub(r"<(strong|b)[^>]*>(.*?)</\1>", r"**\2**", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<(em|i)[^>]*>(.*?)</\1>", r"*\2*", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(
        r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>',
        r"[\2](\1)",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    text = re.sub(r"<[^>]+>", "", text)
    text = _html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def html_to_plain_text(content: str) -> str:
    """Convert shallow HTML to plain text (Markdown markers stripped)."""
    return strip_markdown(html_to_markdown(content))
