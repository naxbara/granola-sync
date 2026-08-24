"""Tests for suggesting a speaker name and confirming it.

The whole point is that a suggestion is never applied on its own. These pin
down both halves: what gets suggested (and, more importantly, what does not),
and that confirming it rewrites only what it should.
"""

from datetime import UTC, datetime

from granola_sync.api.models import GranolaDocument, TranscriptUtterance
from granola_sync.converters.people import PersonasIndex
from granola_sync.converters.speakers import suggest_speakers
from granola_sync.converters.transcript import render_transcript_note
from granola_sync.sync.speaker_confirm import (
    apply_confirmation,
    confirmed_speaker,
    read_frontmatter,
)

NOTE_STEM = "2026-08-19-marshall"


def _utterances(*texts) -> list[TranscriptUtterance]:
    return [
        TranscriptUtterance(
            id=f"u{i}",
            document_id="doc-1",
            start_timestamp=datetime(2026, 8, 19, 16, 51, i, tzinfo=UTC),
            end_timestamp=datetime(2026, 8, 19, 16, 51, i + 1, tzinfo=UTC),
            text=text,
            source="system" if i else "microphone",
        )
        for i, text in enumerate(texts)
    ]


def _vault(tmp_path, fichas: dict[str, str]):
    personas = tmp_path / "Personas"
    personas.mkdir(exist_ok=True)
    for name, body in fichas.items():
        (personas / f"{name}.md").write_text(body, encoding="utf-8")
    return PersonasIndex.from_vault(tmp_path)


def test_a_name_in_both_title_and_transcript_is_suggested(tmp_path):
    index = _vault(tmp_path, {"Francisco Marshall": "---\nemail: f@nexart.cl\n---\n"})
    found = suggest_speakers(
        "Marshall", _utterances("Hola", "Marshall me dijo que sí"), index
    )
    assert [c.name for c in found] == ["Francisco Marshall"]
    assert found[0].mentions == 1


def test_a_shared_surname_offers_both_and_says_so(tmp_path):
    """Real case: 'marshall' matches two people in the vault."""
    index = _vault(
        tmp_path,
        {
            "Francisco Marshall": "---\nemail: f@nexart.cl\n---\n",
            "Denise Marshall": "---\nemail: d@tsplegal.cl\n---\n",
        },
    )
    found = suggest_speakers("Marshall", _utterances("Hola", "Marshall dijo"), index)
    assert {c.name for c in found} == {"Francisco Marshall", "Denise Marshall"}
    assert all(c.ambiguous for c in found)
    assert "más de una ficha" in found[0].evidence()


def test_a_name_only_in_the_transcript_is_not_suggested(tmp_path):
    """Whoever is talked about is not necessarily whoever is talking."""
    index = _vault(tmp_path, {"Cristian Muñoz": "---\nemail: c@x.cl\n---\n"})
    found = suggest_speakers(
        "Situación KYON", _utterances("Hola", "Cristian me contó que Cristian viene"), index
    )
    assert found == []


def test_a_name_only_in_the_title_is_not_suggested(tmp_path):
    index = _vault(tmp_path, {"Gustavo Sáez": "---\nemail: g@x.cl\n---\n"})
    found = suggest_speakers("Conversación Gustavo", _utterances("Hola", "Nada"), index)
    assert found == []


def test_the_owner_is_never_a_candidate(tmp_path):
    """'Sebastián' appears in every single transcript."""
    index = _vault(tmp_path, {"Sebastian Suarez": "---\nemail: s@x.cl\n---\n"})
    found = suggest_speakers(
        "Sebastian y el equipo",
        _utterances("Hola", "Sebastian, cuéntanos"),
        index,
        owner_names={"Sebastian Suarez"},
    )
    assert found == []


def test_group_notes_are_not_speakers(tmp_path):
    index = _vault(
        tmp_path, {"Grupo Molymet": "---\ntype: group\nemail: g@molymet.cl\n---\n"}
    )
    found = suggest_speakers("Molymet sesión", _utterances("Hola", "Molymet pidió"), index)
    assert found == []


def test_accents_do_not_break_the_match(tmp_path):
    index = _vault(tmp_path, {"Carmen Gloria Marín": "---\nemail: c@x.cl\n---\n"})
    found = suggest_speakers("Reunión Marin", _utterances("Hola", "Marín comentó"), index)
    assert [c.name for c in found] == ["Carmen Gloria Marín"]


# --- the confirmation half ------------------------------------------------


def _doc() -> GranolaDocument:
    return GranolaDocument(
        id="doc-1",
        title="Marshall",
        created_at="2026-08-19T16:51:00Z",
        updated_at="2026-08-19T17:30:00Z",
    )


def _write_suggested(tmp_path, index):
    candidates = suggest_speakers("Marshall", _utterances("Hola", "Marshall dijo"), index)
    note = render_transcript_note(
        _doc(),
        "2026-08-19",
        [],
        _utterances("Hola", "Marshall dijo"),
        NOTE_STEM,
        candidates=candidates,
    )
    path = tmp_path / f"{NOTE_STEM}-transcript.md"
    path.write_text(note, encoding="utf-8")
    return path


def test_a_suggestion_records_itself_without_touching_the_body(tmp_path):
    index = _vault(tmp_path, {"Francisco Marshall": "---\nemail: f@nexart.cl\n---\n"})
    path = _write_suggested(tmp_path, index)
    text = path.read_text(encoding="utf-8")

    assert "speaker_attribution: sugerido" in text
    assert 'speaker_candidates: ["Francisco Marshall"]' in text
    # The body still says Speaker: nothing was applied.
    assert "_Speaker_: Marshall dijo" in text
    # And the frontmatter is still valid YAML despite the quotes in the
    # evidence string — this is what broke the first time round.
    assert read_frontmatter(path)["speaker_candidates"] == ["Francisco Marshall"]


def test_confirming_relabels_the_body_and_records_the_answer(tmp_path):
    index = _vault(tmp_path, {"Francisco Marshall": "---\nemail: f@nexart.cl\n---\n"})
    path = _write_suggested(tmp_path, index)

    changed = apply_confirmation(path, "Francisco Marshall")
    text = path.read_text(encoding="utf-8")

    assert changed == 1
    assert "_Francisco Marshall_: Marshall dijo" in text
    assert "speaker_attribution: confirmado" in text
    assert "speaker_confirmed: Francisco Marshall" in text
    # The suggestion is spent.
    assert "speaker_candidates" not in text
    assert "speaker_evidence" not in text


def test_confirming_does_not_reformat_the_rest_of_the_note(tmp_path):
    """The blank line under the frontmatter is part of the canonical format."""
    index = _vault(tmp_path, {"Francisco Marshall": "---\nemail: f@nexart.cl\n---\n"})
    path = _write_suggested(tmp_path, index)
    before = path.read_text(encoding="utf-8")
    apply_confirmation(path, "Francisco Marshall")
    after = path.read_text(encoding="utf-8")

    tail = "\n> Transcripcion literal"
    assert before.split("---\n")[-1].startswith("\n> Transcripcion literal")
    assert tail in after
    assert "---\n> Transcripcion" not in after


def test_confirming_leaves_the_mic_owner_alone(tmp_path):
    index = _vault(tmp_path, {"Francisco Marshall": "---\nemail: f@nexart.cl\n---\n"})
    path = _write_suggested(tmp_path, index)
    apply_confirmation(path, "Francisco Marshall")
    assert "_You_: Hola" in path.read_text(encoding="utf-8")


def test_confirming_twice_changes_nothing_more(tmp_path):
    index = _vault(tmp_path, {"Francisco Marshall": "---\nemail: f@nexart.cl\n---\n"})
    path = _write_suggested(tmp_path, index)
    apply_confirmation(path, "Francisco Marshall")
    first = path.read_text(encoding="utf-8")

    assert apply_confirmation(path, "Francisco Marshall") == 0
    assert path.read_text(encoding="utf-8") == first


def test_a_confirmed_name_survives_a_resync(tmp_path):
    """Regenerating the transcript must not undo the answer."""
    index = _vault(tmp_path, {"Francisco Marshall": "---\nemail: f@nexart.cl\n---\n"})
    path = _write_suggested(tmp_path, index)
    apply_confirmation(path, "Francisco Marshall")

    settled = confirmed_speaker(path)
    assert settled == "Francisco Marshall"

    regenerated = render_transcript_note(
        _doc(),
        "2026-08-19",
        [],
        _utterances("Hola", "Marshall dijo"),
        NOTE_STEM,
        confirmed_speaker=settled,
    )
    assert "_Francisco Marshall_: Marshall dijo" in regenerated
    assert "speaker_attribution: confirmado" in regenerated


def test_a_name_typed_by_hand_in_obsidian_is_picked_up(tmp_path):
    index = _vault(tmp_path, {"Francisco Marshall": "---\nemail: f@nexart.cl\n---\n"})
    path = _write_suggested(tmp_path, index)
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text.replace(
            "speaker_attribution: sugerido",
            "speaker_attribution: sugerido\nspeaker_confirmed: Otra Persona",
        ),
        encoding="utf-8",
    )
    assert confirmed_speaker(path) == "Otra Persona"

    apply_confirmation(path, confirmed_speaker(path))
    assert "_Otra Persona_: Marshall dijo" in path.read_text(encoding="utf-8")


def test_frontmatter_of_an_untouched_transcript_has_no_speaker_keys(tmp_path):
    note = render_transcript_note(
        _doc(), "2026-08-19", [], _utterances("Hola", "Nada"), NOTE_STEM
    )
    path = tmp_path / "plain-transcript.md"
    path.write_text(note, encoding="utf-8")
    meta = read_frontmatter(path)
    assert "speaker_attribution" not in meta
    assert confirmed_speaker(path) is None
