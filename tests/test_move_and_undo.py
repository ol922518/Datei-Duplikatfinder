"""
Tests für move_to_duplicates_folder() / undo_last_move() / has_undo() -
die Datei-verschiebende Kernlogik, siehe duplicate_engine.py Abschnitt
"Verschieben in einen 'Duplikate'-Unterordner" bzw. "Rückgängig machen".

Deckt insbesondere die beiden Review-Fixes vom 07.09.2026 ab (Commit
2901b9a): das Undo-Log wird bei einer neuen Verschiebe-Aktion ergänzt
statt überschrieben, und ein Teil-Fehlschlag beim Rückgängigmachen
verliert die betroffenen Einträge nicht.
"""

import json

import duplicate_engine as engine


def _make_file(path, content: str = "x") -> None:
    path.write_text(content)


def test_move_single_file_succeeds(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "a.txt"
    _make_file(f)

    performed, errors = engine.move_to_duplicates_folder([f], [src])

    assert errors == []
    assert len(performed) == 1
    old, new = performed[0]
    assert old == str(f)
    assert not f.exists()
    assert (src / "Duplikate" / "a.txt").exists()
    assert engine.has_undo()


def test_move_writes_log_for_undo(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "a.txt"
    _make_file(f)

    engine.move_to_duplicates_folder([f], [src])

    entries = json.loads(engine.LOG_FILE.read_text())
    assert entries == [[str(f), str(src / "Duplikate" / "a.txt")]]


def test_move_name_conflict_gets_unique_suffix(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    dup_dir = src / "Duplikate"
    dup_dir.mkdir()
    _make_file(dup_dir / "a.txt", "already there")
    f = src / "a.txt"
    _make_file(f, "new content")

    performed, errors = engine.move_to_duplicates_folder([f], [src])

    assert errors == []
    _old, new = performed[0]
    assert new == str(dup_dir / "a_001.txt")
    assert (dup_dir / "a.txt").read_text() == "already there"
    assert (dup_dir / "a_001.txt").read_text() == "new content"


def test_move_one_missing_file_does_not_discard_other_successes(tmp_path):
    """Eine fehlgeschlagene Datei darf die zuvor erfolgreich verschobenen
    nicht verwerfen (Review-Fix 18770ae) - hier simuliert über eine Datei,
    die zwischen dem Sammeln der Auswahl und dem eigentlichen Verschieben
    verschwunden ist."""
    src = tmp_path / "src"
    src.mkdir()
    ok_file = src / "a.txt"
    _make_file(ok_file)
    missing_file = src / "does_not_exist.txt"

    performed, errors = engine.move_to_duplicates_folder([ok_file, missing_file], [src])

    assert len(performed) == 1
    assert performed[0][0] == str(ok_file)
    assert len(errors) == 1
    assert "does_not_exist.txt" in errors[0]
    assert not ok_file.exists()


def test_move_preserves_relative_subfolder_structure(tmp_path):
    src = tmp_path / "src"
    (src / "Fotos" / "2020").mkdir(parents=True)
    f = src / "Fotos" / "2020" / "bild.jpg"
    _make_file(f)

    performed, _errors = engine.move_to_duplicates_folder([f], [src])

    _old, new = performed[0]
    assert new == str(src / "Duplikate" / "Fotos" / "2020" / "bild.jpg")


def test_move_with_shared_target_folder_ignores_source_structure(tmp_path):
    src_a = tmp_path / "a"
    src_b = tmp_path / "b"
    src_a.mkdir()
    src_b.mkdir()
    f_a = src_a / "x.txt"
    f_b = src_b / "y.txt"
    _make_file(f_a)
    _make_file(f_b)
    target = tmp_path / "central"

    performed, errors = engine.move_to_duplicates_folder(
        [f_a, f_b], [src_a, src_b], target_folder=target
    )

    assert errors == []
    assert (target / "x.txt").exists()
    assert (target / "y.txt").exists()


def test_undo_restores_file_and_clears_log_on_full_success(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "a.txt"
    _make_file(f, "hello")
    engine.move_to_duplicates_folder([f], [src])
    assert not f.exists()

    ok, errors = engine.undo_last_move()

    assert ok == 1
    assert errors == []
    assert f.exists()
    assert f.read_text() == "hello"
    assert not engine.has_undo()


def test_undo_multi_file_round_trip(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    files = [src / f"{i}.txt" for i in range(4)]
    for f in files:
        _make_file(f)

    performed, errors = engine.move_to_duplicates_folder(files, [src])
    assert not errors and len(performed) == 4

    ok, errors = engine.undo_last_move()

    assert ok == 4
    assert errors == []
    assert all(f.exists() for f in files)
    assert not engine.has_undo()


def test_undo_with_no_log_is_a_noop(tmp_path):
    ok, errors = engine.undo_last_move()
    assert (ok, errors) == (0, [])


def test_undo_partial_failure_keeps_only_failed_entries_for_retry(tmp_path):
    """Review-Fix aus dem 18770ae-Round: ein Teil-Fehlschlag beim
    Rückgängigmachen darf die alter-Pfad/neuer-Pfad-Zuordnung der noch
    nicht wiederhergestellten Dateien nicht verlieren."""
    src = tmp_path / "src"
    src.mkdir()
    f = src / "a.txt"
    _make_file(f)
    engine.move_to_duplicates_folder([f], [src])

    # Simuliert einen bereits fehlgeschlagenen vorherigen Undo-Versuch:
    # der alte Pfad existiert nicht mehr (Ursprungsordner z.B. gelöscht).
    bogus_entry = ["/nonexistent/old/a.txt", str(src / "Duplikate" / "a.txt")]
    engine.LOG_FILE.write_text(json.dumps([bogus_entry], ensure_ascii=False, indent=2))

    ok, errors = engine.undo_last_move()

    assert ok == 0
    assert len(errors) == 1
    assert engine.has_undo()
    remaining = json.loads(engine.LOG_FILE.read_text())
    assert remaining == [bogus_entry]


def test_move_after_partial_undo_failure_preserves_pending_retry_entry(tmp_path):
    """Der Kern-Fix aus Commit 2901b9a: eine neue Verschiebe-Aktion darf
    einen noch offenen Undo-Retry-Eintrag nicht stillschweigend
    überschreiben."""
    src = tmp_path / "src"
    src.mkdir()
    f1 = src / "a.txt"
    f2 = src / "b.txt"
    _make_file(f1)
    _make_file(f2)

    engine.move_to_duplicates_folder([f1], [src])
    bogus_entry = ["/nonexistent/old/a.txt", str(src / "Duplikate" / "a.txt")]
    engine.LOG_FILE.write_text(json.dumps([bogus_entry], ensure_ascii=False, indent=2))

    performed, errors = engine.move_to_duplicates_folder([f2], [src])

    assert errors == []
    log_after = json.loads(engine.LOG_FILE.read_text())
    assert bogus_entry in log_after
    assert len(log_after) == 2

    # Der offene Eintrag lässt sich weiterhin gezielt nachholen.
    ok, undo_errors = engine.undo_last_move()
    assert ok == 1  # nur b.txt lässt sich wiederherstellen
    assert len(undo_errors) == 1  # a.txt (bogus_entry) schlägt weiterhin fehl
    remaining = json.loads(engine.LOG_FILE.read_text())
    assert remaining == [bogus_entry]
