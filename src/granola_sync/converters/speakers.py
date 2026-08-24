"""Work out who the other voice in a transcript belongs to.

Granola ships no diarization, so every remote speaker arrives as one flat
"Speaker" label. This module handles the three honest ways out of that, in
descending order of certainty:

1. Granola itself attributes the turn (``detected_speaker_name``) — never seen
   in practice yet, since it is a paid feature, but handled for the day it is.
2. The meeting has exactly one other attendee and we can name them. Certain,
   because it comes from the invitation.
3. Nobody is on the invitation, but a name from the vault's Personas notes
   shows up in *both* the meeting title and the spoken text. That is a
   suggestion, never applied on its own — the user confirms it.

Anything weaker stays "Speaker". A wrong name on three hundred transcript
lines reads as fact and is worse than no name at all.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..api.models import TranscriptUtterance
    from .people import Participant, PersonasIndex

logger = logging.getLogger(__name__)

# How the non-owner turns got their label, recorded so a reader knows how much
# to trust it.
ATTRIBUTION_GRANOLA = "granola"
ATTRIBUTION_ONE_TO_ONE = "1a1"
ATTRIBUTION_SUGGESTED = "sugerido"
ATTRIBUTION_CONFIRMED = "confirmado"
ATTRIBUTION_NONE = "ninguna"

GENERIC_LABEL = "Speaker"

# A surname shorter than this matches too much to be worth following.
MIN_SURNAME = 5


def normalize(text: str) -> str:
    """Lowercase and strip accents, so 'Marín' and 'marin' are the same token."""
    folded = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def short_name(name: str) -> str:
    """Trim the disambiguating suffix vault notes carry in their filename.

    'Carmen Gloria Marín (Promind AI)' is a fine note title but a clumsy label
    to repeat on several hundred transcript lines. The full form stays on the
    roster, where it earns its keep.
    """
    head = name.split(" (")[0].strip()
    return head or name


@dataclass(frozen=True)
class Candidate:
    """A name we think might be the other speaker, and why."""

    name: str
    key: str          # the token that matched ("marshall")
    mentions: int     # times it appears in the spoken text
    ambiguous: bool   # the same token matches more than one person

    def evidence(self) -> str:
        base = f"'{self.key}' en el título y {self.mentions}× en la transcripción"
        return f"{base} (el apellido matchea más de una ficha)" if self.ambiguous else base


def resolve_speaker(
    participants: list[Participant],
    utterances: list[TranscriptUtterance],
    owner_emails: set[str] | None = None,
) -> tuple[str, str]:
    """Decide what to call the other side, from the invitation alone.

    Returns the label for non-owner turns and how it was arrived at.
    """
    if any(u.detected_speaker_name for u in utterances):
        logger.info("Granola supplied speaker attribution for this transcript")
        return GENERIC_LABEL, ATTRIBUTION_GRANOLA

    owners = {email.lower() for email in (owner_emails or ())}
    others = [p for p in participants if p.email.lower() not in owners]
    # Every remaining attendee must be named, and be the same person — someone
    # who joined under two addresses is still a one-to-one.
    if others and all(person.name for person in others):
        names = {person.name for person in others}
        if len(names) == 1:
            return short_name(names.pop()), ATTRIBUTION_ONE_TO_ONE

    return GENERIC_LABEL, ATTRIBUTION_NONE


def _keys_for(name: str) -> list[str]:
    """The ways a person actually gets referred to out loud.

    A meeting titled by surname is often spoken by first name, and the other
    way round: "JC Lanas y Gustavo" never says "Lanas" once, but says "Juan
    Carlos" eighteen times. Searching only the full name misses both.

    The given-name part is kept whole ("juan carlos") rather than split into
    bare tokens, because "juan" on its own matches half of Chile.
    """
    normalized = normalize(short_name(name))
    keys = [normalized]
    parts = normalized.split()
    if len(parts) > 1:
        if len(parts[-1]) >= MIN_SURNAME:
            keys.append(parts[-1])
        given = " ".join(parts[:-1])
        if len(given) >= MIN_SURNAME:
            keys.append(given)
    return keys


def _mentions(haystack: str, key: str) -> int:
    return len(re.findall(rf"\b{re.escape(key)}\b", haystack))


def suggest_speakers(
    title: str,
    utterances: list[TranscriptUtterance],
    personas: PersonasIndex,
    owner_names: set[str] | None = None,
    limit: int = 4,
) -> list[Candidate]:
    """Names from the vault that appear in both the title and the spoken text.

    Requiring both is what keeps this useful. Measured over a real fortnight,
    the transcript alone surfaces whoever was *talked about* — the owner's own
    name shows up in every single one — while title-and-transcript together
    picked out the right person every time it fired, and stayed quiet when
    there was nothing to say.
    """
    spoken = normalize(" ".join(u.text for u in utterances))
    heading = normalize(title).replace("-", " ")
    owners = {normalize(n) for n in (owner_names or ())}

    # A person qualifies when the title names them *and* the conversation
    # does — not necessarily by the same part of their name.
    hits: list[tuple[str, str, int]] = []
    for person, is_group in personas.names():
        if is_group or normalize(short_name(person)) in owners:
            continue
        keys = _keys_for(person)
        title_key = next((key for key in keys if _mentions(heading, key)), None)
        if not title_key:
            continue
        mentions = max(_mentions(spoken, key) for key in keys)
        if mentions:
            hits.append((person, title_key, mentions))

    # Only call it ambiguous when two people actually survived on the same
    # token; the spoken evidence often settles a shared surname by itself.
    shared = [key for _, key, _ in hits]
    found = [
        Candidate(
            name=short_name(person),
            key=key,
            mentions=mentions,
            ambiguous=shared.count(key) > 1,
        )
        for person, key, mentions in hits
    ]
    return sorted(found, key=lambda c: (-c.mentions, c.name))[:limit]
