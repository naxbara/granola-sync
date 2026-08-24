"""Tests for participant resolution.

The point of this module is to stop losing people: Granola's payload carries
names, employers and job titles that the old code threw away, and most recent
documents carry no attendees at all.
"""

from granola_sync.api.models import GranolaDocument
from granola_sync.converters.people import (
    SOURCE_CREATOR,
    SOURCE_GOOGLE_CALENDAR,
    Participant,
    PersonasIndex,
    dedupe,
    emails,
    from_document,
    resolve,
    roster,
)


def _make_doc(**overrides) -> GranolaDocument:
    defaults = {
        "id": "doc-1",
        "title": "Reunión",
        "created_at": "2026-08-21T20:08:00Z",
        "updated_at": "2026-08-21T21:16:00Z",
    }
    defaults.update(overrides)
    return GranolaDocument(**defaults)


def test_reads_name_company_and_title_from_details():
    doc = _make_doc(
        people={
            "attendees": [
                {
                    "email": "Ana@Habitat.cl",
                    "details": {
                        "person": {
                            "name": {"fullName": "Ana Pérez"},
                            "employment": {"name": "AFP Hábitat", "title": "Jefa de Arquitectura"},
                        },
                        "company": {"name": "AFP Hábitat"},
                    },
                }
            ]
        }
    )
    (person,) = from_document(doc)
    assert person.email == "ana@habitat.cl"  # normalized
    assert person.name == "Ana Pérez"
    assert person.company == "AFP Hábitat"
    assert person.title == "Jefa de Arquitectura"


def test_creator_is_included():
    """The creator rides on every document; it used to be discarded."""
    doc = _make_doc(people={"creator": {"email": "beto@lab-ai.org", "name": "Beto Soto"}})
    (person,) = from_document(doc)
    assert person.email == "beto@lab-ai.org"
    assert person.name == "Beto Soto"
    assert person.source == SOURCE_CREATOR


def test_calendar_event_attendees_are_used_too():
    doc = _make_doc(
        google_calendar_event={"attendees": [{"email": "c@x.cl"}, {"email": "d@x.cl"}]}
    )
    assert emails(from_document(doc)) == ["c@x.cl", "d@x.cl"]


def test_entries_without_an_email_are_dropped():
    doc = _make_doc(people={"attendees": [{"name": "Sin correo"}, {"email": "  "}]})
    assert from_document(doc) == []


def test_dedupe_keeps_first_sighting_and_fills_its_gaps():
    people_list = [
        Participant(email="a@x.cl", name="Ana"),
        Participant(email="A@X.CL", company="Equis"),
        Participant(email="b@x.cl"),
    ]
    result = dedupe(people_list)
    assert emails(result) == ["a@x.cl", "b@x.cl"]
    assert result[0].name == "Ana"
    assert result[0].company == "Equis"


def test_dedupe_never_overwrites_a_known_name():
    result = dedupe(
        [Participant(email="a@x.cl", name="Ana Pérez"), Participant(email="a@x.cl", name="A. P.")]
    )
    assert result[0].name == "Ana Pérez"


def _write_ficha(folder, filename, body):
    (folder / filename).write_text(body, encoding="utf-8")


def test_personas_index_resolves_names_from_the_vault(tmp_path):
    personas = tmp_path / "Personas"
    personas.mkdir()
    _write_ficha(
        personas,
        "Andrés Erlandsen.md",
        "---\nemail: andres@catchai.ai\ncompany: CatchAI\nrole: Fundador\n---\n\nFicha.\n",
    )
    index = PersonasIndex.from_vault(tmp_path)

    (person,) = index.enrich([Participant(email="andres@catchai.ai")])
    assert person.name == "Andrés Erlandsen"
    assert person.company == "CatchAI"
    assert person.title == "Fundador"


def test_personas_index_honours_alternate_addresses(tmp_path):
    """emails_alt is the vault's way of saying 'same person'."""
    personas = tmp_path / "Personas"
    personas.mkdir()
    _write_ficha(
        personas,
        "Ana Pérez.md",
        "---\nemail: ana@habitat.cl\nemails_alt: [ana.perez@gmail.com]\n---\n",
    )
    index = PersonasIndex.from_vault(tmp_path)
    (person,) = index.enrich([Participant(email="ana.perez@gmail.com")])
    assert person.name == "Ana Pérez"


def test_personas_index_survives_a_broken_ficha(tmp_path):
    personas = tmp_path / "Personas"
    personas.mkdir()
    _write_ficha(personas, "Rota.md", "---\nemail: [unclosed\n---\n")
    _write_ficha(personas, "Sana.md", "---\nemail: ok@x.cl\n---\n")
    index = PersonasIndex.from_vault(tmp_path)
    assert len(index) == 1


def test_personas_index_without_the_folder_is_empty(tmp_path):
    assert len(PersonasIndex.from_vault(tmp_path)) == 0


def test_the_vault_never_overwrites_granola(tmp_path):
    """Granola said 'Ana Pérez'; a stale ficha must not rename her."""
    personas = tmp_path / "Personas"
    personas.mkdir()
    _write_ficha(personas, "Nombre Viejo.md", "---\nemail: ana@habitat.cl\n---\n")
    doc = _make_doc(people={"attendees": [{"email": "ana@habitat.cl", "name": "Ana Pérez"}]})

    (person,) = resolve(doc, personas=PersonasIndex.from_vault(tmp_path))
    assert person.name == "Ana Pérez"


def test_resolve_merges_calendar_addresses(tmp_path):
    doc = _make_doc(people={"attendees": [{"email": "ana@habitat.cl"}]})
    result = resolve(doc, calendar_emails=["beto@lab-ai.org", "ANA@habitat.cl"])
    assert emails(result) == ["ana@habitat.cl", "beto@lab-ai.org"]
    assert result[1].source == SOURCE_GOOGLE_CALENDAR


def test_roster_reads_as_a_sentence():
    people_list = [
        Participant(email="ana@habitat.cl", name="Ana Pérez", company="AFP Hábitat", title="Jefa"),
        Participant(email="beto@lab-ai.org", name="Beto Soto"),
        Participant(email="anon@x.cl"),
    ]
    assert roster(people_list) == (
        "Ana Pérez <ana@habitat.cl> — AFP Hábitat, Jefa · "
        "Beto Soto <beto@lab-ai.org> · "
        "anon@x.cl"
    )
