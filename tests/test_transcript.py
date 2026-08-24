"""Tests for the standalone transcript note and the callout it leaves behind.

The reference format is not invented here: it is what
``Recursos/segundo-cerebro/extraer-transcripciones.py`` wrote into the 482
notes already in the vault. A freshly synced note must be indistinguishable
from a migrated one, so these are golden-file comparisons.
"""

from datetime import UTC, datetime
from pathlib import Path

from granola_sync.api.models import GranolaDocument, TranscriptUtterance
from granola_sync.converters.people import SOURCE_ATTENDEE, from_emails
from granola_sync.converters.template import render_meeting_note
from granola_sync.converters.transcript import (
    render_callout,
    render_transcript_note,
    transcript_filename,
)

FIXTURES = Path(__file__).parent / "fixtures"

PARTICIPANT_EMAILS = ["ana@habitat.cl", "beto@lab-ai.org"]
# Addresses with no names attached: renders exactly like the migrated notes.
PARTICIPANTS = from_emails(PARTICIPANT_EMAILS, SOURCE_ATTENDEE)
NOTE_STEM = "2026-08-21-reunion-de-prueba"


def _make_doc(**overrides) -> GranolaDocument:
    defaults = {
        "id": "c4d33160-b0da-4708-938c-78eda410aea4",
        "title": "Reunión de prueba",
        "created_at": "2026-08-21T20:08:00Z",
        "updated_at": "2026-08-21T21:16:34Z",
        "people": {"attendees": [{"email": e} for e in PARTICIPANT_EMAILS]},
    }
    defaults.update(overrides)
    return GranolaDocument(**defaults)


def _make_utterances() -> list[TranscriptUtterance]:
    return [
        TranscriptUtterance(
            id="u1",
            document_id="c4d33160-b0da-4708-938c-78eda410aea4",
            start_timestamp=datetime(2026, 8, 21, 20, 8, 31, tzinfo=UTC),
            end_timestamp=datetime(2026, 8, 21, 20, 8, 35, tzinfo=UTC),
            text="Con todo el background que hemos ido levantando.",
            source="system",
        ),
        TranscriptUtterance(
            id="u2",
            document_id="c4d33160-b0da-4708-938c-78eda410aea4",
            start_timestamp=datetime(2026, 8, 21, 20, 8, 40, tzinfo=UTC),
            end_timestamp=datetime(2026, 8, 21, 20, 8, 44, tzinfo=UTC),
            text="Exacto, eso es lo que nosotros les vamos a diseñar.",
            source="microphone",
        ),
    ]


def test_transcript_note_matches_golden():
    """The transcript file is byte-identical to the migrated format."""
    result = render_transcript_note(
        _make_doc(), "2026-08-21", PARTICIPANTS, _make_utterances(), NOTE_STEM
    )
    expected = (FIXTURES / "expected_transcript.md").read_text(encoding="utf-8")
    assert result == expected


def test_callout_matches_golden():
    """The callout left in the note is byte-identical to the migrated one."""
    result = render_callout(_make_doc(), PARTICIPANTS, NOTE_STEM)
    expected = (FIXTURES / "expected_callout.md").read_text(encoding="utf-8")
    assert result == expected


def test_callout_names_the_people_it_can_name():
    from granola_sync.converters.people import Participant

    named = [
        Participant(email="ana@habitat.cl", name="Ana Pérez", company="AFP Hábitat", title="Jefa"),
        Participant(email="anon@x.cl"),
    ]
    result = render_callout(_make_doc(), named, NOTE_STEM)
    assert "> Meeting participants: ana@habitat.cl, anon@x.cl" in result
    # Only the person we can actually name; the rest are already listed above.
    assert "> Asistentes: Ana Pérez <ana@habitat.cl> — AFP Hábitat, Jefa\n" in result
    assert "anon@x.cl ·" not in result


def test_one_person_with_two_addresses_is_named_once():
    """Real case: Denise Marshall joined under both of her work addresses."""
    from granola_sync.converters.people import Participant

    twice = [
        Participant(email="dmarshall@tsplegal.cl", name="Denise Marshall", company="TSP Legal"),
        Participant(email="denise@dnxconsultora.cl", name="Denise Marshall", company="TSP Legal"),
    ]
    result = render_callout(_make_doc(), twice, NOTE_STEM)
    # Both addresses stay on the identity line...
    assert "dmarshall@tsplegal.cl, denise@dnxconsultora.cl" in result
    # ...but she is a single human.
    assert result.count("Denise Marshall") == 1


def test_callout_field_order_is_fixed():
    result = render_callout(_make_doc(), PARTICIPANTS, NOTE_STEM)
    assert result.index("> Ver:") < result.index("> Granola:")
    assert result.index("> Granola:") < result.index("> Meeting participants:")


def test_accent_free_wording_is_preserved():
    """'Transcripcion' stays unaccented — the 482 migrated notes spell it so.

    Fixing the accent here would split the vault into two formats and break
    the 'already processed' detection of the migration script.
    """
    callout = render_callout(_make_doc(), PARTICIPANTS, NOTE_STEM)
    transcript = render_transcript_note(
        _make_doc(), "2026-08-21", PARTICIPANTS, _make_utterances(), NOTE_STEM
    )
    assert "Transcripcion completa" in callout
    assert "Transcripcion literal" in transcript
    assert "Transcripción" not in callout
    assert "Transcripción" not in transcript


def test_transcript_filename_pairs_with_note():
    assert transcript_filename(NOTE_STEM) == f"{NOTE_STEM}-transcript.md"


def test_separate_mode_keeps_transcript_out_of_the_note():
    note = render_meeting_note(
        _make_doc(),
        "## Resumen\n\nUn acuerdo.",
        utterances=_make_utterances(),
        transcript_mode="separate",
        note_stem=NOTE_STEM,
    )
    assert "> [!quote]- Transcripcion completa" in note
    assert f"> Ver: [[{NOTE_STEM}-transcript]]" in note
    # the spoken text must not be in the note any more
    assert "Con todo el background" not in note
    assert "**[20:08:31]**" not in note
    # and the old inline preamble is gone: it moved to the transcript note
    assert "Meeting Title:" not in note
    assert "Transcript:" not in note


def test_inline_mode_is_unchanged():
    """The GUI exporter still needs everything in one file."""
    note = render_meeting_note(
        _make_doc(),
        "## Resumen",
        utterances=_make_utterances(),
        transcript_mode="inline",
    )
    assert "Con todo el background" in note
    assert "Transcript:" in note
    assert "> [!quote]" not in note


def test_separate_mode_without_transcript_keeps_the_metadata():
    """No utterances means no transcript note, so the metadata stays put.

    Otherwise the callout would link to a file that was never written and the
    participants would be lost.
    """
    note = render_meeting_note(
        _make_doc(),
        "## Resumen",
        utterances=None,
        transcript_mode="separate",
        note_stem=NOTE_STEM,
    )
    assert "> [!quote]" not in note
    assert "Meeting participants: ana@habitat.cl, beto@lab-ai.org" in note


def test_rendering_is_idempotent():
    """Re-syncing the same meeting produces exactly the same pair of files."""
    args = (_make_doc(), "2026-08-21", PARTICIPANTS, _make_utterances(), NOTE_STEM)
    assert render_transcript_note(*args) == render_transcript_note(*args)
    first = render_meeting_note(
        _make_doc(), "## Resumen", utterances=_make_utterances(),
        transcript_mode="separate", note_stem=NOTE_STEM,
    )
    second = render_meeting_note(
        _make_doc(), "## Resumen", utterances=_make_utterances(),
        transcript_mode="separate", note_stem=NOTE_STEM,
    )
    assert first == second


def test_utterances_are_ordered_chronologically():
    out_of_order = list(reversed(_make_utterances()))
    result = render_transcript_note(
        _make_doc(), "2026-08-21", PARTICIPANTS, out_of_order, NOTE_STEM
    )
    assert result.index("**[20:08:31]**") < result.index("**[20:08:40]**")
