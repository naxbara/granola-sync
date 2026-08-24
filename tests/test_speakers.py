"""Tests for naming the other side of the conversation.

Granola gives no diarization: every remote voice arrives as one "Speaker".
There is exactly one case that can be resolved without guessing — a meeting
with a single other attendee whom we can name — and these tests pin down that
line so nothing wider creeps past it.
"""

from datetime import UTC, datetime

from granola_sync.api.models import GranolaDocument, TranscriptUtterance
from granola_sync.converters.people import Participant
from granola_sync.converters.speakers import (
    ATTRIBUTION_GRANOLA,
    ATTRIBUTION_NONE,
    ATTRIBUTION_ONE_TO_ONE,
    resolve_speaker,
)
from granola_sync.converters.transcript import render_transcript_note, render_utterances

OWNER = {"ssuarez@gmail.com", "sebastian.suarez@kauel.com"}
NOTE_STEM = "2026-08-21-reunion"


def _doc() -> GranolaDocument:
    return GranolaDocument(
        id="doc-1",
        title="Reunión",
        created_at="2026-08-21T20:08:00Z",
        updated_at="2026-08-21T21:16:00Z",
    )


def _utterances(**overrides) -> list[TranscriptUtterance]:
    base = {
        "document_id": "doc-1",
        "end_timestamp": datetime(2026, 8, 21, 20, 8, 35, tzinfo=UTC),
    }
    return [
        TranscriptUtterance(
            id="u1",
            start_timestamp=datetime(2026, 8, 21, 20, 8, 31, tzinfo=UTC),
            text="Hola, cuéntame.",
            source="microphone",
            **base,
        ),
        TranscriptUtterance(
            id="u2",
            start_timestamp=datetime(2026, 8, 21, 20, 8, 40, tzinfo=UTC),
            text="Te explico el estado.",
            source="system",
            **{**base, **overrides},
        ),
    ]


def test_a_one_to_one_names_the_other_person():
    people = [
        Participant(email="ssuarez@gmail.com", name="Sebastián"),
        Participant(email="ana@habitat.cl", name="Ana Pérez"),
    ]
    label, mode = resolve_speaker(people, _utterances(), OWNER)
    assert (label, mode) == ("Ana Pérez", ATTRIBUTION_ONE_TO_ONE)


def test_the_label_drops_the_notes_disambiguating_suffix():
    """Real case: the vault names her ficha 'Carmen Gloria Marín (Promind AI)'."""
    people = [
        Participant(email="ssuarez@gmail.com", name="Sebastián"),
        Participant(email="yoyamarin@gmail.com", name="Carmen Gloria Marín (Promind AI)"),
    ]
    label, mode = resolve_speaker(people, _utterances(), OWNER)
    assert (label, mode) == ("Carmen Gloria Marín", ATTRIBUTION_ONE_TO_ONE)


def test_a_group_call_keeps_the_generic_label():
    """In a room of five the turns are genuinely indistinguishable."""
    people = [
        Participant(email="ssuarez@gmail.com", name="Sebastián"),
        Participant(email="ana@habitat.cl", name="Ana Pérez"),
        Participant(email="beto@lab-ai.org", name="Beto Soto"),
    ]
    label, mode = resolve_speaker(people, _utterances(), OWNER)
    assert (label, mode) == ("Speaker", ATTRIBUTION_NONE)


def test_an_unnamed_counterpart_is_not_labelled_with_an_address():
    people = [
        Participant(email="ssuarez@gmail.com", name="Sebastián"),
        Participant(email="quien@x.cl"),
    ]
    label, mode = resolve_speaker(people, _utterances(), OWNER)
    assert (label, mode) == ("Speaker", ATTRIBUTION_NONE)


def test_one_person_under_two_addresses_is_still_a_one_to_one():
    people = [
        Participant(email="ssuarez@gmail.com", name="Sebastián"),
        Participant(email="dmarshall@tsplegal.cl", name="Denise Marshall"),
        Participant(email="denise@dnxconsultora.cl", name="Denise Marshall"),
    ]
    label, mode = resolve_speaker(people, _utterances(), OWNER)
    assert (label, mode) == ("Denise Marshall", ATTRIBUTION_ONE_TO_ONE)


def test_without_owner_addresses_nothing_is_named():
    """Unconfigured owner_emails must fail closed, not label the owner's own words."""
    people = [
        Participant(email="ssuarez@gmail.com", name="Sebastián"),
        Participant(email="ana@habitat.cl", name="Ana Pérez"),
    ]
    label, mode = resolve_speaker(people, _utterances(), owner_emails=None)
    assert (label, mode) == ("Speaker", ATTRIBUTION_NONE)


def test_a_meeting_with_only_the_owner_names_nobody():
    people = [Participant(email="ssuarez@gmail.com", name="Sebastián")]
    label, mode = resolve_speaker(people, _utterances(), OWNER)
    assert (label, mode) == ("Speaker", ATTRIBUTION_NONE)


def test_granola_attribution_wins_when_it_ever_arrives():
    people = [
        Participant(email="ssuarez@gmail.com", name="Sebastián"),
        Participant(email="ana@habitat.cl", name="Ana Pérez"),
    ]
    utterances = _utterances(detected_speaker_name="Carlos Díaz")
    label, mode = resolve_speaker(people, utterances, OWNER)
    assert mode == ATTRIBUTION_GRANOLA
    # And the per-utterance name is what actually gets rendered.
    lines = render_utterances(utterances, label)
    assert "_Carlos Díaz_: Te explico el estado." in "\n".join(lines)


def test_the_mic_owner_is_always_You():
    """The 482 migrated transcripts use _You_; that label does not move."""
    lines = "\n".join(render_utterances(_utterances(), "Ana Pérez"))
    assert "_You_: Hola, cuéntame." in lines
    assert "_Ana Pérez_: Te explico el estado." in lines


def test_attribution_is_recorded_in_the_transcript_frontmatter():
    people = [
        Participant(email="ssuarez@gmail.com", name="Sebastián"),
        Participant(email="ana@habitat.cl", name="Ana Pérez"),
    ]
    note = render_transcript_note(
        _doc(), "2026-08-21", people, _utterances(), NOTE_STEM, owner_emails=OWNER
    )
    assert "speaker_attribution: 1a1" in note
    assert "_Ana Pérez_:" in note


def test_no_attribution_leaves_the_frontmatter_as_the_migrated_files_have_it():
    """Absence of the key means the generic label, same as the 482 migrated."""
    people = [
        Participant(email="ssuarez@gmail.com", name="Sebastián"),
        Participant(email="ana@habitat.cl", name="Ana Pérez"),
        Participant(email="beto@lab-ai.org", name="Beto Soto"),
    ]
    note = render_transcript_note(
        _doc(), "2026-08-21", people, _utterances(), NOTE_STEM, owner_emails=OWNER
    )
    assert "speaker_attribution:" not in note
    assert "_Speaker_:" in note
