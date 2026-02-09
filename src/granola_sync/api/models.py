"""Pydantic models for Granola API responses."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProseMirrorMark(BaseModel):
    type: str  # "bold", "italic", "link"
    attrs: dict | None = None


class ProseMirrorNode(BaseModel):
    type: str  # "doc", "heading", "paragraph", "bulletList", "orderedList", "listItem", "text"
    content: list[ProseMirrorNode] = Field(default_factory=list)
    text: str | None = None
    attrs: dict | None = None
    marks: list[ProseMirrorMark] = Field(default_factory=list)


class CalendarEventTime(BaseModel):
    dateTime: str | None = None
    timeZone: str | None = None


class CalendarEvent(BaseModel):
    start: CalendarEventTime | None = None
    end: CalendarEventTime | None = None
    summary: str | None = None
    attendees: list[dict] = Field(default_factory=list)
    description: str | None = None


class PersonDetails(BaseModel):
    name: str | None = None
    email: str | None = None
    details: dict | None = None


class DocumentPeople(BaseModel):
    title: str | None = None
    creator: dict | None = None
    attendees: list[dict] = Field(default_factory=list)
    conferencing: dict | None = None


class DocumentPanel(BaseModel):
    document_id: str = ""
    id: str = ""
    title: str | None = None
    content: dict | None = None  # ProseMirror doc
    template_slug: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    content_updated_at: str | None = None


class GranolaDocument(BaseModel):
    """A Granola meeting document."""

    id: str
    title: str = ""
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    type: str | None = "meeting"
    notes: dict | None = None  # ProseMirror JSON
    notes_plain: str | None = ""
    notes_markdown: str | None = ""
    people: dict | None = None
    google_calendar_event: dict | None = None
    summary: str | None = None
    overview: str | None = None
    chapters: list | None = None
    workspace_id: str | None = None
    creation_source: str | None = None
    subscription_plan_id: str | None = None
    status: str | None = None
    panels: list[DocumentPanel] = Field(default_factory=list, alias="documentPanels")
    last_viewed_panel: DocumentPanel | None = None

    model_config = {"populate_by_name": True, "extra": "ignore"}

    @property
    def meeting_date(self) -> datetime:
        """Get the meeting date from calendar event or created_at."""
        cal = self.google_calendar_event
        if cal and isinstance(cal, dict):
            start = cal.get("start", {})
            dt_str = start.get("dateTime") if isinstance(start, dict) else None
            if dt_str:
                return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return self.created_at

    @property
    def duration_minutes(self) -> int | None:
        """Calculate duration from calendar event start/end."""
        cal = self.google_calendar_event
        if not cal or not isinstance(cal, dict):
            return None
        start = cal.get("start", {})
        end = cal.get("end", {})
        start_dt = start.get("dateTime") if isinstance(start, dict) else None
        end_dt = end.get("dateTime") if isinstance(end, dict) else None
        if not start_dt or not end_dt:
            return None
        s = datetime.fromisoformat(start_dt.replace("Z", "+00:00"))
        e = datetime.fromisoformat(end_dt.replace("Z", "+00:00"))
        return int((e - s).total_seconds() / 60)

    @property
    def participant_emails(self) -> list[str]:
        """Extract participant emails from people or calendar event."""
        emails = []
        if self.people and isinstance(self.people, dict):
            for att in self.people.get("attendees", []):
                email = att.get("email", "")
                if email:
                    emails.append(email)
        if not emails and self.google_calendar_event:
            cal = self.google_calendar_event
            if isinstance(cal, dict):
                for att in cal.get("attendees", []):
                    email = att.get("email", "")
                    if email:
                        emails.append(email)
        return emails


class TranscriptUtterance(BaseModel):
    """A single utterance from a meeting transcript."""

    id: str
    document_id: str
    start_timestamp: datetime
    end_timestamp: datetime
    text: str
    source: str = "system"  # "system" | "microphone"
    is_final: bool = True
