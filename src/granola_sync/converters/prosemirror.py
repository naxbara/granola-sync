"""Custom ProseMirror JSON to Markdown converter for Granola documents.

Handles exactly the node and mark types found in real Granola documents:
  Nodes: doc, heading, paragraph, bulletList, orderedList, listItem, text
  Marks: bold, italic, link
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


_MARKDOWN_STRIP_PATTERNS = [
    (re.compile(r"\[([^\]]+)\]\([^)]+\)"), r"\1"),  # [text](url) -> text
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),        # **bold** -> bold
    (re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)"), r"\1"),  # *italic* -> italic
    (re.compile(r"^(#{1,6})\s+", re.MULTILINE), ""),   # heading prefixes
]


def to_plain_text(doc: dict) -> str:
    """Convert a ProseMirror doc to readable plain text (no markdown markers).

    Bullet/ordered lists become "- " / "N. " prefixed lines so the structure
    survives in a .txt file readable from Notepad.
    """
    md = ProseMirrorToMarkdown().convert(doc)
    plain = md
    for pattern, repl in _MARKDOWN_STRIP_PATTERNS:
        plain = pattern.sub(repl, plain)
    return plain


class ProseMirrorToMarkdown:
    """Convert a ProseMirror JSON document to a Markdown string."""

    def convert(self, doc: dict) -> str:
        """Convert a ProseMirror doc node to Markdown.

        Args:
            doc: The root ProseMirror node (type must be "doc").

        Returns:
            Markdown string.
        """
        if doc.get("type") != "doc":
            logger.warning("Expected 'doc' root node, got '%s'", doc.get("type"))
        return self._convert_blocks(doc.get("content", []))

    def _convert_blocks(self, nodes: list[dict]) -> str:
        """Convert a list of block-level nodes, separated by blank lines."""
        parts = []
        for node in nodes:
            result = self._convert_block(node)
            if result is not None:
                parts.append(result)
        return "\n\n".join(parts)

    def _convert_block(self, node: dict) -> str | None:
        """Convert a single block-level node to Markdown."""
        node_type = node.get("type", "")
        attrs = node.get("attrs") or {}
        content = node.get("content", [])

        match node_type:
            case "heading":
                level = attrs.get("level", 1)
                text = self._inline_content(content)
                if text:
                    return f"{'#' * level} {text}"
                return None

            case "paragraph":
                return self._inline_content(content)

            case "bulletList":
                return self._convert_list(content, "bullet", depth=0)

            case "orderedList":
                start = attrs.get("start", 1)
                return self._convert_list(content, "ordered", depth=0, start=start)

            case _:
                # Unknown block node — try to extract text content
                if content:
                    text = self._inline_content(content)
                    if text:
                        logger.debug("Unknown block node type: %s", node_type)
                        return text
                return None

    def _convert_list(
        self,
        items: list[dict],
        list_type: str,
        depth: int,
        start: int = 1,
    ) -> str:
        """Convert a list (bullet or ordered) to Markdown."""
        indent = "  " * depth
        lines: list[str] = []

        for i, item in enumerate(items):
            if item.get("type") != "listItem":
                continue

            children = item.get("content", [])
            text_parts: list[str] = []
            nested_lists: list[str] = []

            for child in children:
                child_type = child.get("type", "")
                if child_type in ("bulletList", "orderedList"):
                    child_start = (child.get("attrs") or {}).get("start", 1)
                    nested_type = "bullet" if child_type == "bulletList" else "ordered"
                    nested_lists.append(
                        self._convert_list(
                            child.get("content", []),
                            nested_type,
                            depth + 1,
                            child_start,
                        )
                    )
                else:
                    text = self._inline_content(child.get("content", []))
                    if text:
                        text_parts.append(text)

            item_text = " ".join(text_parts)
            if list_type == "bullet":
                prefix = f"{indent}- "
            else:
                prefix = f"{indent}{start + i}. "

            lines.append(f"{prefix}{item_text}")
            for nested in nested_lists:
                lines.append(nested)

        return "\n".join(lines)

    def _inline_content(self, nodes: list[dict]) -> str:
        """Convert inline content (text nodes with marks) to Markdown."""
        parts: list[str] = []
        for node in nodes:
            if node.get("type") == "text":
                parts.append(self._apply_marks(node))
            else:
                # Recurse for non-text inline nodes
                inner = node.get("content", [])
                if inner:
                    parts.append(self._inline_content(inner))
        return "".join(parts)

    def _apply_marks(self, node: dict) -> str:
        """Apply Markdown formatting for marks (bold, italic, link)."""
        text = node.get("text", "")
        if not text:
            return ""

        marks = node.get("marks", [])
        if not marks:
            return text

        # Sort marks so link is outermost, then bold, then italic
        has_bold = False
        has_italic = False
        link_href = None

        for mark in marks:
            mark_type = mark.get("type", "")
            if mark_type == "bold":
                has_bold = True
            elif mark_type == "italic":
                has_italic = True
            elif mark_type == "link":
                link_href = (mark.get("attrs") or {}).get("href", "")

        # Apply formatting inside-out: italic → bold → link
        if has_italic:
            text = f"*{text}*"
        if has_bold:
            text = f"**{text}**"
        if link_href:
            # Strip any bold/italic we just added for the link text display
            display = text
            text = f"[{display}]({link_href})"

        return text
