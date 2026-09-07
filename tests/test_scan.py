"""
Tests für list_files()/collect_files() (Ordner einlesen) und
find_exact_duplicates() (exakter Duplikat-Vergleich), siehe
duplicate_engine.py Abschnitte "Ordner einlesen" / "Duplikat-Suche".
"""

import os
import time

import duplicate_engine as engine


def test_list_files_non_recursive_ignores_subfolder(tmp_path):
    (tmp_path / "top.txt").write_text("a")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.txt").write_text("b")

    files = engine.list_files(tmp_path, recursive=False)

    assert files == [tmp_path / "top.txt"]


def test_list_files_recursive_includes_subfolder(tmp_path):
    (tmp_path / "top.txt").write_text("a")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.txt").write_text("b")

    files = engine.list_files(tmp_path, recursive=True)

    assert set(files) == {tmp_path / "top.txt", sub / "nested.txt"}


def test_list_files_skips_hidden_file_by_default(tmp_path):
    (tmp_path / ".hidden.txt").write_text("a")
    (tmp_path / "visible.txt").write_text("b")

    files = engine.list_files(tmp_path, recursive=False)

    assert files == [tmp_path / "visible.txt"]


def test_list_files_skips_files_inside_hidden_subfolder_when_recursive(tmp_path):
    """Regressionstest für den 18770ae-Fix: nicht nur der Dateiname selbst,
    sondern auch versteckte Elternordner (z.B. '.git') zählen."""
    hidden_dir = tmp_path / ".git"
    hidden_dir.mkdir()
    (hidden_dir / "config").write_text("secret")
    (tmp_path / "visible.txt").write_text("b")

    files = engine.list_files(tmp_path, recursive=True)

    assert files == [tmp_path / "visible.txt"]


def test_list_files_include_hidden_true_returns_everything(tmp_path):
    (tmp_path / ".hidden.txt").write_text("a")
    (tmp_path / "visible.txt").write_text("b")

    files = engine.list_files(tmp_path, recursive=False, include_hidden=True)

    assert set(files) == {tmp_path / ".hidden.txt", tmp_path / "visible.txt"}


def test_list_files_always_skips_duplikate_output_folder(tmp_path):
    dup_dir = tmp_path / engine.DUPLICATES_FOLDER_NAME
    dup_dir.mkdir()
    (dup_dir / "already_moved.txt").write_text("a")
    (tmp_path / "source.txt").write_text("b")

    files = engine.list_files(tmp_path, recursive=True)

    assert files == [tmp_path / "source.txt"]


def test_list_files_exclude_dirs_skips_configured_target(tmp_path):
    central = tmp_path / "Zentral"
    central.mkdir()
    (central / "already_moved.txt").write_text("a")
    (tmp_path / "source.txt").write_text("b")

    files = engine.list_files(tmp_path, recursive=True, exclude_dirs={central})

    assert files == [tmp_path / "source.txt"]


def test_collect_files_deduplicates_across_sources(tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    f = folder / "a.txt"
    f.write_text("x")

    # Derselbe Pfad einmal über den Ordner, einmal direkt als Quelle.
    files = engine.collect_files([folder, f])

    assert files == [f]


def test_find_exact_duplicates_groups_identical_content(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("identical content")
    b.write_text("identical content")
    # Unterschiedliche mtimes erzwingen, damit die Sortierung eindeutig ist.
    os.utime(a, (time.time() - 100, time.time() - 100))
    os.utime(b, (time.time(), time.time()))

    groups = engine.find_exact_duplicates([a, b])

    assert len(groups) == 1
    group = groups[0]
    assert group.kind == "exact"
    assert [entry.path for entry in group.files] == [a, b]  # älteste (a) zuerst


def test_find_exact_duplicates_ignores_different_content(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("content one")
    b.write_text("content two, different length")

    groups = engine.find_exact_duplicates([a, b])

    assert groups == []


def test_find_exact_duplicates_ignores_empty_files(tmp_path):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("")
    b.write_text("")

    groups = engine.find_exact_duplicates([a, b])

    assert groups == []


def test_find_exact_duplicates_orders_groups_by_wasted_bytes(tmp_path):
    # Gruppe 1: 2x 20 Bytes -> 20 Bytes einsparbar.
    small_a, small_b = tmp_path / "s1.txt", tmp_path / "s2.txt"
    small_a.write_text("x" * 20)
    small_b.write_text("x" * 20)
    # Gruppe 2: 3x 50 Bytes -> 100 Bytes einsparbar (mehr, sollte zuerst kommen).
    big_a, big_b, big_c = tmp_path / "b1.txt", tmp_path / "b2.txt", tmp_path / "b3.txt"
    for f in (big_a, big_b, big_c):
        f.write_text("y" * 50)

    groups = engine.find_exact_duplicates([small_a, small_b, big_a, big_b, big_c])

    assert len(groups) == 2
    assert groups[0].wasted_bytes == 100
    assert groups[1].wasted_bytes == 20


def test_move_to_trash_moves_and_reports_count(tmp_path):
    if not engine.HAS_SEND2TRASH:
        import pytest
        pytest.skip("send2trash nicht installiert")
    f = tmp_path / "a.txt"
    f.write_text("x")

    count, errors = engine.move_to_trash([f])

    assert count == 1
    assert errors == []
    assert not f.exists()


def test_move_to_trash_missing_file_reports_error_without_crashing(tmp_path):
    if not engine.HAS_SEND2TRASH:
        import pytest
        pytest.skip("send2trash nicht installiert")
    missing = tmp_path / "does_not_exist.txt"

    count, errors = engine.move_to_trash([missing])

    assert count == 0
    assert len(errors) == 1
    assert "does_not_exist.txt" in errors[0]
