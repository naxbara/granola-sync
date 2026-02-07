"""Claude AI enrichment for meeting notes.

Extracts structured metadata: projects, action items, tags,
meeting type, and follow-ups.
"""

from __future__ import annotations

import json
import logging

import anthropic

logger = logging.getLogger(__name__)

ENRICHMENT_PROMPT = """\
Analyze this meeting note and extract structured information.

Meeting Title: {title}

Meeting Content:
{content}

Respond in JSON format with exactly these fields:
- "projects": list of project names mentioned or related (max 5)
- "action_items": list of specific action items or tasks mentioned (max 10)
- "tags": list of relevant tags for categorization, lowercase, no # prefix (max 8)
- "meeting_type": one of "sales", "technical", "planning", "standup", "review", "training", "other"
- "follow_ups": list of pending follow-ups or next steps mentioned (max 5)

Return ONLY valid JSON, no other text."""


class ClaudeEnricher:
    """Enriches meeting notes using the Claude API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def enrich(self, title: str, content: str) -> dict:
        """Extract structured metadata from a meeting note.

        Args:
            title: Meeting title.
            content: Markdown content of the meeting notes.

        Returns:
            Dict with keys: projects, action_items, tags, meeting_type, follow_ups.
            Returns empty dict on failure.
        """
        if not content.strip():
            return {}

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
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
            text = response.content[0].text.strip()

            # Handle potential markdown code fences in response
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            result = json.loads(text)
            logger.info("Enriched '%s': type=%s, %d action items, %d tags",
                        title, result.get("meeting_type", "?"),
                        len(result.get("action_items", [])),
                        len(result.get("tags", [])))
            return result

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse Claude response for '%s': %s", title, e)
            return {}
        except anthropic.APIError as e:
            logger.warning("Claude API error for '%s': %s", title, e)
            return {}
