"""
conftest.py
-----------
Gemeinsame Fixtures für alle Tests. Isoliert jeden Test von globalem
Zustand in duplicate_engine.py:

- LOG_FILE zeigt normalerweise auf eine feste Datei neben dem Modul
  (`.last_move_log.json`) - Tests bekommen stattdessen eine frische Datei
  in einem eigenen Temp-Ordner, damit sie sich weder gegenseitig noch die
  echte Undo-Historie einer laufenden App beeinflussen.
- _dhash_cache (Perceptual-Hash-Cache, siehe [[recompute_similarity]])
  wird vor jedem Test geleert, damit ein Test nicht vom Hash-Ergebnis
  eines vorherigen profitiert/gestört wird.
- send2trash.send2trash() wird durch ein einfaches Löschen der (ohnehin
  nur in tmp_path liegenden) Testdatei ersetzt - sonst würde
  test_move_to_trash_moves_and_reports_count bei installiertem send2trash
  echt den System-Papierkorb des Rechners anfassen, auf dem die Tests
  laufen. Die Assertions in den Tests (Datei existiert danach nicht mehr)
  bleiben davon unberührt.
"""

from pathlib import Path

import pytest

import duplicate_engine as engine


@pytest.fixture(autouse=True)
def isolated_engine_state(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "LOG_FILE", tmp_path / ".last_move_log.json")
    if engine.HAS_SEND2TRASH:
        monkeypatch.setattr(engine.send2trash, "send2trash", lambda path: Path(path).unlink())
    engine._dhash_cache.clear()
    yield
    engine._dhash_cache.clear()
