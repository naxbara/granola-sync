"""Claude AI enrichment for meeting notes.

Extracts structured metadata: projects, action items, tags,
meeting type, and follow-ups.

Uses forced tool use so Claude returns a validated structured object
(``tool_use.input`` is already a parsed dict) instead of free-form text
we would have to strip code fences from and ``json.loads``.
"""

from __future__ import annotations

import logging

import anthropic

logger = logging.getLogger(__name__)

MEETING_TYPES = [
    "sales", "technical", "planning", "standup", "review", "training", "other",
]

ENRICHMENT_TOOL = {
    "name": "record_enrichment",
    "description": "Record the structured metadata extracted from a meeting note.",
    "input_schema": {
        "type": "object",
        "properties": {
            "projects": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Nombres de proyectos mencionados o relacionados (máx 5).",
            },
            "action_items": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tareas o acciones concretas mencionadas, en español (máx 10).",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tags de categorización en español, minúscula, sin '#' (máx 8).",
            },
            "meeting_type": {
                "type": "string",
                "enum": MEETING_TYPES,
                "description": "Tipo de reunión.",
            },
            "follow_ups": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Seguimientos o próximos pasos pendientes, en español (máx 5).",
            },
        },
        "required": ["projects", "action_items", "tags", "meeting_type", "follow_ups"],
    },
}

ENRICHMENT_PROMPT = """\
Analiza esta nota de reunión y extrae información estructurada llamando a la
herramienta record_enrichment. Responde con proyectos, tareas, tags y
seguimientos en español; usa el enum indicado para meeting_type.

Título: {title}

Contenido:
{content}"""


class ClaudeEnricher:
    """Enriches meeting notes using the Claude API."""

    def __init__(self, api_key: str, model: str = "claude-opus-4-8") -> None:
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def enrich(self, title: str, content: str) -> dict:
        """Extract structured metadata from a meeting note.

        Args:
            title: Meeting title.
            content: Markdown content of the meeting notes.

        Returns:
            Dict with keys: projects, action_items, tags, meeting_type, follow_ups.
            Returns empty dict on failure (logged at WARNING).
        """
        if not content.strip():
            return {}

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                tools=[ENRICHMENT_TOOL],
                tool_choice={"type": "tool", "name": "record_enrichment"},
                messages=[
                    {
                        "role": "user",
                        "content": ENRICHMENT_PROMPT.format(
                            title=title,
                            content=content[:4000],  # Limit to avoid token overflow
                        ),
                    }
                ],
            )
        except anthropic.APIError as e:
            logger.warning("Claude API error enriching '%s': %s", title, e)
            return {}
        except Exception as e:  # network / SDK errors not wrapped as APIError
            logger.warning("Unexpected error enriching '%s': %s", title, e)
            return {}

        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                result = dict(block.input)
                logger.info(
                    "Enriched '%s': type=%s, %d action items, %d tags",
                    title,
                    result.get("meeting_type", "?"),
                    len(result.get("action_items", [])),
                    len(result.get("tags", [])),
                )
                return result

        logger.warning("Claude returned no tool_use block enriching '%s'", title)
        return {}
