"""
Tests für den Perceptual-Hash-Teil (_dhash/scan_for_similar_images/
recompute_similarity), siehe duplicate_engine.py Abschnitt "Ähnliche
Bilder". Der wichtigste Test hier ist
test_recompute_similarity_reuses_cache_from_initial_scan() - der
Regressionstest für den Performance-Fix vom 07.09.2026 (Commit c369ecc):
recompute_similarity() darf nach einem Scan keine Bilder erneut
dekodieren, die bereits gehasht wurden.
"""

import random

import pytest

import duplicate_engine as engine

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def _make_test_image(path, seed: int, size: tuple[int, int] = (32, 32)) -> None:
    """Erzeugt ein deterministisches Testbild aus Zufalls-Pixeln - reicht
    für den dHash-Vergleich (unterschiedliche Seeds -> deutlich
    unterschiedlicher Hash, siehe Modul-Docstring), ohne echte Bilddateien
    im Repo zu brauchen."""
    rng = random.Random(seed)
    pixels = bytes(rng.randrange(256) for _ in range(size[0] * size[1] * 3))
    Image.frombytes("RGB", size, pixels).save(path)


class _CountingOpen:
    """Zählt Aufrufe von Image.open(), um zu verifizieren, dass ein
    gecachter dHash tatsächlich kein erneutes Dekodieren auslöst."""

    def __init__(self, original):
        self.original = original
        self.count = 0

    def __call__(self, path, *args, **kwargs):
        self.count += 1
        return self.original(path, *args, **kwargs)


def test_dhash_is_deterministic_for_same_file(tmp_path):
    img = tmp_path / "img.png"
    _make_test_image(img, seed=1)

    assert engine._dhash(img) == engine._dhash(img)


def test_dhash_caches_and_skips_redecoding_unchanged_file(tmp_path, monkeypatch):
    img = tmp_path / "img.png"
    _make_test_image(img, seed=1)
    counting_open = _CountingOpen(Image.open)
    monkeypatch.setattr(engine.Image, "open", counting_open)

    first = engine._dhash(img)
    second = engine._dhash(img)

    assert first == second
    assert counting_open.count == 1  # zweiter Aufruf kam aus dem Cache


def test_dhash_cache_is_invalidated_when_file_changes(tmp_path):
    img = tmp_path / "img.png"
    _make_test_image(img, seed=1)
    first = engine._dhash(img)

    # Andere mtime UND anderer Inhalt erzwingen - ein neuer Cache-Eintrag
    # statt des alten (falschen) Werts.
    import os
    import time

    time.sleep(0.01)
    _make_test_image(img, seed=2)
    os.utime(img, (time.time() + 1, time.time() + 1))

    second = engine._dhash(img)

    assert first != second


def test_scan_for_similar_images_groups_identical_images(tmp_path):
    paths = []
    for i in range(3):
        p = tmp_path / f"img{i}.png"
        _make_test_image(p, seed=1)  # identischer Inhalt -> garantiert "ähnlich"
        paths.append(p)

    groups = engine.scan_for_similar_images(paths)

    assert len(groups) == 1
    assert groups[0].kind == "similar"
    assert {entry.path for entry in groups[0].files} == set(paths)
    assert groups[0].similarity == pytest.approx(1.0)


def test_scan_for_similar_images_does_not_group_unrelated_images(tmp_path):
    a = tmp_path / "a.png"
    b = tmp_path / "b.png"
    _make_test_image(a, seed=1)
    _make_test_image(b, seed=2)  # deutlich anderer Hash, siehe Modul-Docstring

    groups = engine.scan_for_similar_images([a, b])

    assert groups == []


def test_recompute_similarity_matches_original_scan(tmp_path):
    paths = []
    for i in range(3):
        p = tmp_path / f"img{i}.png"
        _make_test_image(p, seed=1)
        paths.append(p)
    groups = engine.scan_for_similar_images(paths)
    original_similarity = groups[0].similarity

    # Gruppe "schrumpft" um eine Datei - Neuberechnung für die
    # verbleibenden zwei muss weiterhin ~1.0 ergeben (identische Bilder).
    recomputed = engine.recompute_similarity(paths[:2])

    assert recomputed == pytest.approx(original_similarity)
    assert recomputed == pytest.approx(1.0)


def test_recompute_similarity_reuses_cache_from_initial_scan(tmp_path, monkeypatch):
    """Regressionstest für den Performance-Fix vom 07.09.2026: nach einem
    Scan (der bereits alle Hashes berechnet hat) darf
    recompute_similarity() dieselben, unveränderten Dateien NICHT erneut
    dekodieren - vorher fror das die Oberfläche bei größeren Gruppen nach
    jeder einzelnen Verschieben/Löschen-Aktion spürbar ein."""
    paths = []
    for i in range(5):
        p = tmp_path / f"img{i}.png"
        _make_test_image(p, seed=1)
        paths.append(p)

    engine.scan_for_similar_images(paths)  # füllt den _dhash_cache

    counting_open = _CountingOpen(Image.open)
    monkeypatch.setattr(engine.Image, "open", counting_open)

    similarity = engine.recompute_similarity(paths[:3])

    assert similarity is not None
    assert counting_open.count == 0, (
        "recompute_similarity() hat mindestens ein Bild erneut dekodiert, "
        "obwohl es beim vorherigen Scan schon gehasht wurde"
    )


def test_recompute_similarity_returns_none_for_single_remaining_file(tmp_path):
    p = tmp_path / "img.png"
    _make_test_image(p, seed=1)

    assert engine.recompute_similarity([p]) is None
