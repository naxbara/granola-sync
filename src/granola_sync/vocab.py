"""Words the sync writes into the vault, per vault language.

The Spanish set is copied verbatim from what the vault already holds — including
"Transcripcion" without its accent — so a freshly synced note stays
indistinguishable from the ones migrated in August. Other tools match on some of
these strings (the "Ver:" line, the callout title), so they only change together
with a vault's language, never on their own.

`ACTIVE` is module-level on purpose, like `utils.LOCAL_TZ`: the engine sets it
once per run from the vault profile, and tests monkeypatch it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Vocab:
    transcript_type: str
    meeting_key: str            # frontmatter key linking a transcript to its note
    transcript_intro: str       # "{note}" is the meeting note stem
    callout_title: str
    callout_body: tuple[str, ...]
    see: str                    # label of the link to the transcript
    attendees: str
    evidence: str               # "{key}", "{mentions}"
    evidence_ambiguous: str


VOCABS: dict[str, Vocab] = {
    "es": Vocab(
        transcript_type="transcripcion",
        meeting_key="reunion",
        transcript_intro="> Transcripcion literal de [[{note}]]. Fuera del camino de lectura por defecto.",
        callout_title="> [!quote]- Transcripcion completa",
        callout_body=(
            "> La transcripcion literal de esta reunion vive fuera del camino de lectura",
            "> por defecto para no pesar en las consultas al vault.",
        ),
        see="Ver",
        attendees="Asistentes",
        evidence="'{key}' en el título y {mentions}× en la transcripción",
        evidence_ambiguous=" (el apellido matchea más de una ficha)",
    ),
    "en": Vocab(
        transcript_type="transcript",
        meeting_key="meeting",
        transcript_intro="> Literal transcript of [[{note}]]. Kept out of the default reading path.",
        callout_title="> [!quote]- Full transcript",
        callout_body=(
            "> The literal transcript of this meeting lives outside the default reading path",
            "> so it does not weigh on queries over the vault.",
        ),
        see="See",
        attendees="Attendees",
        evidence="'{key}' in the title and {mentions}× in the transcript",
        evidence_ambiguous=" (the surname matches more than one person)",
    ),
}

ACTIVE: Vocab = VOCABS["es"]


def use(language: str) -> Vocab:
    """Make `language` the active vocabulary. Unknown languages fall back to Spanish."""
    global ACTIVE
    ACTIVE = VOCABS.get(language, VOCABS["es"])
    return ACTIVE
