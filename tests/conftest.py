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
"""

import pytest

import duplicate_engine as engine


@pytest.fixture(autouse=True)
def isolated_engine_state(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "LOG_FILE", tmp_path / ".last_move_log.json")
    engine._dhash_cache.clear()
    yield
    engine._dhash_cache.clear()
