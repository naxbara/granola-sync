"""Resolve who attended a meeting, with their name, company and role.

Granola's own attendee data collapsed: of 100 recent documents only 8 carry
``people.attendees`` and 9 carry ``google_calendar_event``. So participants are
assembled from several sources, hardest data first, and every one of them
remembers where it came from — a name filled in from the vault is not the same
kind of fact as an address on a calendar invite.

Nothing here invents people: a source either yields an address or it does not.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, replace
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Where a participant came from, most to least authoritative.
SOURCE_ATTENDEE = "granola-attendee"
SOURCE_CREATOR = "granola-creator"
SOURCE_GRANOLA_CALENDAR = "granola-calendar"
SOURCE_GOOGLE_CALENDAR = "google-calendar"

FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)


@dataclass(frozen=True)
class Participant:
    """One meeting attendee. ``email`` is the identity key."""

    email: str
    name: str | None = None
    company: str | None = None
    title: str | None = None
    source: str = SOURCE_ATTENDEE

    def merged_with(self, other: Participant) -> Participant:
        """Fill this participant's gaps from another sighting of the same person.

        The first sighting wins on every field it already has, so a name that
        came from the invite is never overwritten by a weaker guess later.
        """
        return replace(
            self,
            name=self.name or other.name,
            company=self.company or other.company,
            title=self.title or other.title,
        )

    def describe(self) -> str:
        """Readable form for the note: 'Ana Perez <a@x.cl> - Habitat, Jefa'."""
        head = f"{self.name} <{self.email}>" if self.name else self.email
        tail = ", ".join(part for part in (self.company, self.title) if part)
        return f"{head} — {tail}" if tail else head


def _clean(value: object) -> str | None:
    """Return a trimmed non-empty string, or None."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _from_granola_person(entry: dict, source: str) -> Participant | None:
    """Build a participant from a Granola attendee/creator entry.

    The payload hides the good parts under ``details``: the person's full name,
    their employer and their job title. The previous code read only ``email``.
    """
    email = _clean(entry.get("email"))
    if not email:
        return None

    name = _clean(entry.get("name"))
    company = title = None

    details = entry.get("details")
    if isinstance(details, dict):
        person = details.get("person")
        if isinstance(person, dict):
            full = person.get("name")
            if isinstance(full, dict):
                name = name or _clean(full.get("fullName"))
            employment = person.get("employment")
            if isinstance(employment, dict):
                company = _clean(employment.get("name"))
                title = _clean(employment.get("title"))
        company_block = details.get("company")
        if isinstance(company_block, dict):
            company = company or _clean(company_block.get("name"))

    return Participant(
        email=email.lower(), name=name, company=company, title=title, source=source
    )


def from_document(doc) -> list[Participant]:
    """Every participant Granola itself knows about, in order of authority."""
    found: list[Participant] = []

    people = doc.people if isinstance(doc.people, dict) else {}
    for entry in people.get("attendees") or []:
        if isinstance(entry, dict):
            person = _from_granola_person(entry, SOURCE_ATTENDEE)
            if person:
                found.append(person)

    # The creator rides on every document and was being thrown away entirely.
    creator = people.get("creator")
    if isinstance(creator, dict):
        person = _from_granola_person(creator, SOURCE_CREATOR)
        if person:
            found.append(person)

    cal = doc.google_calendar_event if isinstance(doc.google_calendar_event, dict) else {}
    for entry in cal.get("attendees") or []:
        if isinstance(entry, dict):
            email = _clean(entry.get("email"))
            if email:
                found.append(
                    Participant(email=email.lower(), source=SOURCE_GRANOLA_CALENDAR)
                )

    return found


def from_emails(addresses: list[str], source: str) -> list[Participant]:
    """Wrap bare addresses (e.g. from the Calendar API) as participants."""
    found = []
    for raw in addresses:
        email = _clean(raw)
        if email:
            found.append(Participant(email=email.lower(), source=source))
    return found


def dedupe(participants: list[Participant]) -> list[Participant]:
    """Collapse repeated addresses, keeping the first sighting and its extras."""
    by_email: dict[str, Participant] = {}
    order: list[str] = []
    for person in participants:
        key = person.email.lower()
        if key in by_email:
            by_email[key] = by_email[key].merged_with(person)
        else:
            by_email[key] = person
            order.append(key)
    return [by_email[key] for key in order]


class PersonasIndex:
    """Lookup of email -> name/company/role from the vault's Personas/ notes.

    Offline and free: the vault already knows who most of these people are.
    Uses the same identity key as the personas-vault skill (``email`` plus
    ``emails_alt``) so both agree on who is who.
    """

    def __init__(self, entries: dict[str, Participant] | None = None) -> None:
        self._by_email = entries or {}

    def __len__(self) -> int:
        return len(self._by_email)

    @classmethod
    def from_vault(cls, vault_path: Path, folder: str = "Personas") -> PersonasIndex:
        entries: dict[str, Participant] = {}
        base = vault_path / folder
        if not base.is_dir():
            return cls(entries)

        for note in base.glob("*.md"):
            try:
                text = note.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            match = FRONTMATTER.match(text)
            if not match:
                continue
            try:
                data = yaml.safe_load(match.group(1)) or {}
            except yaml.YAMLError:
                logger.debug("Skipping %s: unreadable frontmatter", note.name)
                continue
            if not isinstance(data, dict):
                continue

            addresses = [data.get("email")]
            alt = data.get("emails_alt")
            if isinstance(alt, list):
                addresses.extend(alt)
            elif isinstance(alt, str):
                addresses.extend(alt.split(","))

            # The filename is the person's name in this vault's convention.
            person = Participant(
                email="",
                name=_clean(data.get("name")) or note.stem,
                company=_clean(data.get("company")),
                title=_clean(data.get("role")),
            )
            for raw in addresses:
                email = _clean(raw)
                if email:
                    entries.setdefault(email.lower(), person)

        return cls(entries)

    def enrich(self, participants: list[Participant]) -> list[Participant]:
        """Fill missing names/companies from the vault, never overwriting."""
        return [
            person.merged_with(known)
            if (known := self._by_email.get(person.email.lower()))
            else person
            for person in participants
        ]


def resolve(
    doc,
    calendar_emails: list[str] | None = None,
    personas: PersonasIndex | None = None,
) -> list[Participant]:
    """Full cascade: Granola's own data, then Calendar, then the vault."""
    found = from_document(doc)
    if calendar_emails:
        found.extend(from_emails(calendar_emails, SOURCE_GOOGLE_CALENDAR))
    found = dedupe(found)
    if personas:
        found = personas.enrich(found)
    return found


def emails(participants: list[Participant]) -> list[str]:
    """Just the addresses — the shape the frontmatter has always had."""
    return [person.email for person in participants]


def roster(participants: list[Participant]) -> str:
    """One-line roster with names, for the callout and the transcript header."""
    return " · ".join(person.describe() for person in participants)
