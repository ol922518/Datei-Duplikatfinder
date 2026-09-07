"""
Tests für move_to_duplicates_folder() / undo_last_move() / has_undo() -
die Datei-verschiebende Kernlogik, siehe duplicate_engine.py Abschnitt
"Verschieben in einen 'Duplikate'-Unterordner" bzw. "Rückgängig machen".

Deckt insbesondere ab:
- Commit 2901b9a: das Undo-Log wird bei einer neuen Verschiebe-Aktion
  ergänzt statt überschrieben, und ein Teil-Fehlschlag beim
  Rückgängigmachen verliert die betroffenen Einträge nicht.
- Review vom 07.09.2026 (Fehlerbehandlung bei Verschieben/Löschen):
  move_to_duplicates_folder()/undo_last_move() geben jetzt ein 3-Tupel
  zurück (..., log_warning) - Protokoll-Probleme sind von echten
  Datei-Fehlern getrennt; undo_last_move() liest ein beschädigtes Log
  jetzt kontrolliert statt ungefangen zu werfen; ein einzelner
  beschädigter Log-Eintrag bricht nicht mehr den gesamten Undo-Batch ab.
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

    performed, errors, log_warning = engine.move_to_duplicates_folder([f], [src])

    assert errors == []
    assert log_warning is None
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

    performed, errors, log_warning = engine.move_to_duplicates_folder([f], [src])

    assert errors == []
    assert log_warning is None
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

    performed, errors, log_warning = engine.move_to_duplicates_folder([ok_file, missing_file], [src])

    assert len(performed) == 1
    assert performed[0][0] == str(ok_file)
    assert len(errors) == 1
    assert "does_not_exist.txt" in errors[0]
    assert log_warning is None
    assert not ok_file.exists()


def test_move_preserves_relative_subfolder_structure(tmp_path):
    src = tmp_path / "src"
    (src / "Fotos" / "2020").mkdir(parents=True)
    f = src / "Fotos" / "2020" / "bild.jpg"
    _make_file(f)

    performed, _errors, _log_warning = engine.move_to_duplicates_folder([f], [src])

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

    performed, errors, log_warning = engine.move_to_duplicates_folder(
        [f_a, f_b], [src_a, src_b], target_folder=target
    )

    assert errors == []
    assert log_warning is None
    assert (target / "x.txt").exists()
    assert (target / "y.txt").exists()


def test_move_log_write_failure_reported_separately_from_move_errors(tmp_path, monkeypatch):
    """Review-Fix 07.09.2026: schlägt nur das Log-Schreiben fehl (alle
    Dateien aber erfolgreich verschoben), landet das in log_warning, NICHT
    in errors - sonst würde die aufrufende Oberfläche "N von N verschoben,
    1 Fehler" anzeigen, was nach einer fehlgeschlagenen Datei klingt,
    obwohl tatsächlich alle verschoben wurden."""
    src = tmp_path / "src"
    src.mkdir()
    f = src / "a.txt"
    _make_file(f)

    def _broken_write_text(self, *args, **kwargs):
        raise OSError("Festplatte voll (simuliert)")

    monkeypatch.setattr(engine.Path, "write_text", _broken_write_text)

    performed, errors, log_warning = engine.move_to_duplicates_folder([f], [src])

    assert len(performed) == 1  # die Datei wurde trotzdem verschoben
    assert not f.exists()
    assert errors == []  # kein Datei-Fehler
    assert log_warning is not None
    assert "Protokoll" in log_warning


def test_move_with_corrupted_existing_log_warns_instead_of_silently_dropping_it(tmp_path):
    """Review-Fix 07.09.2026: ein nicht lesbares vorheriges Protokoll wird
    zwar weiterhin verworfen (der aktuelle Verschiebe-Vorgang darf dadurch
    nicht blockiert werden), aber nicht mehr stillschweigend - der Nutzer
    muss erfahren, dass darin evtl. noch offene Rückgängig-Einträge
    verloren gegangen sind."""
    src = tmp_path / "src"
    src.mkdir()
    f = src / "a.txt"
    _make_file(f)
    engine.LOG_FILE.write_text("{das ist kein gültiges JSON")

    performed, errors, log_warning = engine.move_to_duplicates_folder([f], [src])

    assert len(performed) == 1  # aktueller Vorgang trotzdem erfolgreich
    assert errors == []
    assert log_warning is not None
    assert "verworfen" in log_warning
    # Das neue Log enthält nur den aktuellen Batch - das alte, kaputte ist
    # weg (kann nicht anders sein, war ja nicht lesbar), aber jetzt zumindest
    # gültig und für den aktuellen Batch nutzbar.
    new_entries = json.loads(engine.LOG_FILE.read_text())
    assert new_entries == [list(pair) for pair in performed]  # JSON kennt keine Tupel


def test_undo_restores_file_and_clears_log_on_full_success(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "a.txt"
    _make_file(f, "hello")
    engine.move_to_duplicates_folder([f], [src])
    assert not f.exists()

    ok, errors, log_warning = engine.undo_last_move()

    assert ok == 1
    assert errors == []
    assert log_warning is None
    assert f.exists()
    assert f.read_text() == "hello"
    assert not engine.has_undo()


def test_undo_multi_file_round_trip(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    files = [src / f"{i}.txt" for i in range(4)]
    for f in files:
        _make_file(f)

    performed, errors, _log_warning = engine.move_to_duplicates_folder(files, [src])
    assert not errors and len(performed) == 4

    ok, errors, log_warning = engine.undo_last_move()

    assert ok == 4
    assert errors == []
    assert log_warning is None
    assert all(f.exists() for f in files)
    assert not engine.has_undo()


def test_undo_with_no_log_is_a_noop(tmp_path):
    ok, errors, log_warning = engine.undo_last_move()
    assert (ok, errors, log_warning) == (0, [], None)


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

    ok, errors, log_warning = engine.undo_last_move()

    assert ok == 0
    assert len(errors) == 1
    assert log_warning is None
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

    performed, errors, log_warning = engine.move_to_duplicates_folder([f2], [src])

    assert errors == []
    assert log_warning is None
    log_after = json.loads(engine.LOG_FILE.read_text())
    assert bogus_entry in log_after
    assert len(log_after) == 2

    # Der offene Eintrag lässt sich weiterhin gezielt nachholen.
    ok, undo_errors, undo_log_warning = engine.undo_last_move()
    assert ok == 1  # nur b.txt lässt sich wiederherstellen
    assert len(undo_errors) == 1  # a.txt (bogus_entry) schlägt weiterhin fehl
    assert undo_log_warning is None
    remaining = json.loads(engine.LOG_FILE.read_text())
    assert remaining == [bogus_entry]


def test_undo_corrupted_log_reports_error_instead_of_raising(tmp_path):
    """Review-Fix 07.09.2026: ein beschädigtes/kein gültiges JSON in
    LOG_FILE (z.B. nach einem Absturz mitten im Schreiben) darf
    undo_last_move() nicht mit einer ungefangenen Exception abbrechen
    lassen - das hätte main.py's undo_last() ungeschützt getroffen."""
    engine.LOG_FILE.write_text("{das ist kein gültiges JSON")

    ok, errors, log_warning = engine.undo_last_move()

    assert ok == 0
    assert len(errors) == 1
    assert "Protokoll" in errors[0]
    assert log_warning is None


def test_undo_malformed_entry_fails_only_that_entry_not_whole_batch(tmp_path):
    """Review-Fix 07.09.2026: ein einzelner beschädigter Log-Eintrag
    (falsche Anzahl Elemente) darf run_per_item() nicht mit einem
    ValueError/TypeError verlassen - das würde den kompletten
    Undo-Vorgang abbrechen, auch für noch gar nicht versuchte, an sich
    gültige Einträge (verletzt run_per_item()'s eigene
    Isolations-Garantie)."""
    src = tmp_path / "src"
    src.mkdir()
    ok_file = src / "a.txt"
    _make_file(ok_file, "hello")
    engine.move_to_duplicates_folder([ok_file], [src])
    good_entry = json.loads(engine.LOG_FILE.read_text())[0]

    malformed_entry = ["only_one_element"]
    # Der beschädigte Eintrag zuerst (wird bei reversed() zuletzt versucht) -
    # Reihenfolge spielt für den Test keine Rolle, Hauptsache beide Formen
    # kommen im selben Batch vor.
    engine.LOG_FILE.write_text(json.dumps([malformed_entry, good_entry], ensure_ascii=False, indent=2))

    ok, errors, log_warning = engine.undo_last_move()

    assert ok == 1  # der gültige Eintrag wurde trotzdem wiederhergestellt
    assert ok_file.exists()
    assert ok_file.read_text() == "hello"
    assert len(errors) == 1
    assert "beschädigt" in errors[0] or "Eintrag" in errors[0]
    assert log_warning is None
    # Nur der beschädigte Eintrag bleibt für einen erneuten Versuch übrig.
    remaining = json.loads(engine.LOG_FILE.read_text())
    assert remaining == [malformed_entry]
