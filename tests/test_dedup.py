"""Tests for duplicate detection."""

from pathlib import Path

from granola_sync.sync.dedup import (
    extract_granola_id,
    fuzzy_match_title,
    scan_vault_for_granola_ids,
)


def test_extract_granola_id(tmp_path: Path):
    md_file = tmp_path / "test.md"
    md_file.write_text(
        "---\ntype: meeting\ngranola_id: abc-123-xyz\n---\n\n# Meeting",
        encoding="utf-8",
    )
    assert extract_granola_id(md_file) == "abc-123-xyz"


def test_extract_granola_id_no_frontmatter(tmp_path: Path):
    md_file = tmp_path / "test.md"
    md_file.write_text("# Just a heading\n\nSome text", encoding="utf-8")
    assert extract_granola_id(md_file) is None


def test_extract_granola_id_no_id(tmp_path: Path):
    md_file = tmp_path / "test.md"
    md_file.write_text("---\ntype: meeting\n---\n\n# Meeting", encoding="utf-8")
    assert extract_granola_id(md_file) is None


def test_scan_vault(tmp_path: Path):
    # Create files in Notas Granola subfolder
    notes_dir = tmp_path / "Notas Granola"
    notes_dir.mkdir()
    (notes_dir / "meeting1.md").write_text(
        "---\ngranola_id: id-001\n---\n\n# M1", encoding="utf-8"
    )
    (notes_dir / "meeting2.md").write_text(
        "---\ngranola_id: id-002\n---\n\n# M2", encoding="utf-8"
    )
    (notes_dir / "regular-note.md").write_text("# No frontmatter", encoding="utf-8")

    id_map = scan_vault_for_granola_ids(tmp_path)
    assert len(id_map) == 2
    assert "id-001" in id_map
    assert "id-002" in id_map


def test_scan_empty_vault(tmp_path: Path):
    id_map = scan_vault_for_granola_ids(tmp_path)
    assert id_map == {}


def test_fuzzy_match_exact(tmp_path: Path):
    files = [
        tmp_path / "2026-02-06-reunion-cliente-bupa.md",
        tmp_path / "2026-02-06-daily-standup.md",
    ]
    for f in files:
        f.write_text("content", encoding="utf-8")

    result = fuzzy_match_title("reunion cliente bupa", "2026-02-06", files, threshold=85)
    assert result is not None
    assert "bupa" in result.name


def test_fuzzy_match_similar(tmp_path: Path):
    files = [tmp_path / "2026-02-06-reunion-con-cliente-bupa-q1.md"]
    for f in files:
        f.write_text("content", encoding="utf-8")

    result = fuzzy_match_title(
        "reunion con cliente bupa q1 planning", "2026-02-06", files, threshold=70
    )
    assert result is not None


def test_fuzzy_match_no_match(tmp_path: Path):
    files = [tmp_path / "2026-02-06-daily-standup.md"]
    for f in files:
        f.write_text("content", encoding="utf-8")

    result = fuzzy_match_title("reunion cliente bupa", "2026-02-06", files, threshold=85)
    assert result is None


def test_fuzzy_match_wrong_date(tmp_path: Path):
    files = [tmp_path / "2026-02-05-reunion-cliente-bupa.md"]
    for f in files:
        f.write_text("content", encoding="utf-8")

    # Different date should not match
    result = fuzzy_match_title("reunion cliente bupa", "2026-02-06", files, threshold=85)
    assert result is None
