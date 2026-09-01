"""
duplicate_engine.py
--------------------
Kernlogik der Duplikat-Suche, unabhängig von der Oberfläche (main.py).

Vergleich erfolgt gestuft, um bei vielen/großen Dateien nicht unnötig viel
lesen zu müssen:
  1. Dateigröße - Dateien mit einzigartiger Größe scheiden sofort aus.
  2. Teil-Hash (erste PARTIAL_HASH_BYTES Bytes) - filtert die meisten
     restlichen Nicht-Duplikate heraus, ohne die ganze Datei zu lesen.
  3. Voller Hash (SHA-256) - erst für die verbliebenen Kandidaten berechnet,
     das ist die verlässliche Bestätigung.
Zwei Dateien gelten als Duplikate, wenn Größe UND voller Hash übereinstimmen
- der Dateiname spielt bewusst keine Rolle (Duplikate haben oft
unterschiedliche Namen, z.B. "Foto.jpg" und "IMG_0231.jpg").

0-Byte-Dateien werden ignoriert (immer "identisch", aber kein sinnvoller
Fund). Ähnliche, aber nicht bit-identische Dateien (z.B. dasselbe Foto in
anderer Auflösung) werden hier NICHT erkannt - siehe ROADMAP.md.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

PARTIAL_HASH_BYTES = 64 * 1024  # 64 KB
CHUNK_SIZE = 1024 * 1024  # 1 MB - Lesepuffer für den vollen Hash
DUPLICATES_FOLDER_NAME = "Duplikate"

SETTINGS_FILE = Path(__file__).parent / "app_settings.json"
LOG_FILE = Path(__file__).parent / ".last_move_log.json"


@dataclass
class FileEntry:
    path: Path
    size: int
    mtime: float


@dataclass
class DuplicateGroup:
    """Eine Gruppe inhaltlich identischer Dateien. `files` ist nach
    Änderungsdatum aufsteigend sortiert (älteste zuerst) - die älteste Datei
    gilt als Vorschlag fürs "Original" (in main.py vorausgewählt, aber vom
    Nutzer per Häkchen änderbar)."""

    files: list[FileEntry]

    @property
    def size(self) -> int:
        return self.files[0].size

    @property
    def wasted_bytes(self) -> int:
        """Speicherplatz, der sich durch Entfernen aller bis auf eine Datei
        aus dieser Gruppe sparen ließe."""
        return self.size * (len(self.files) - 1)


# ---------------------------------------------------------------------------
# Ordner einlesen
# ---------------------------------------------------------------------------

def list_files(folder: Path, recursive: bool, include_hidden: bool = False) -> list[Path]:
    """Listet alle Dateien in `folder` - rekursiv über Unterordner, sofern
    gewünscht. Der App-eigene "Duplikate"-Ausgabeordner wird dabei immer
    übersprungen, damit bereits verschobene Duplikate nicht bei einem
    erneuten Scan wieder als Quelle mitgezählt werden."""
    pattern = "**/*" if recursive else "*"
    files = []
    for p in sorted(folder.glob(pattern)):
        if not p.is_file():
            continue
        if not include_hidden and p.name.startswith("."):
            continue
        if DUPLICATES_FOLDER_NAME in p.relative_to(folder).parts[:-1]:
            continue
        files.append(p)
    return files


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def _partial_hash(path: Path) -> str:
    with path.open("rb") as f:
        return hashlib.sha256(f.read(PARTIAL_HASH_BYTES)).hexdigest()


def _full_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Duplikat-Suche
# ---------------------------------------------------------------------------

def scan_for_duplicates(sources: list[Path], recursive: bool = True,
                         progress_callback=None) -> list[DuplicateGroup]:
    """Durchsucht die gegebenen Quellen (Ordner und/oder einzelne Dateien)
    und liefert alle gefundenen Duplikat-Gruppen (mind. 2 Dateien je
    Gruppe) - Gruppe mit dem meisten verschwendeten Speicherplatz zuerst.

    `progress_callback(done, total, phase)` wird optional nach jeder
    verarbeiteten Datei aufgerufen (phase: "partial"/"full") - für eine
    Fortschrittsanzeige in der Oberfläche. Nicht mehr lesbare Dateien
    (fehlende Berechtigung, währenddessen gelöscht, ...) werden übersprungen.
    """
    all_files: list[Path] = []
    seen: set[Path] = set()
    for src in sources:
        if src.is_dir():
            for f in list_files(src, recursive=recursive):
                if f not in seen:
                    seen.add(f)
                    all_files.append(f)
        elif src.is_file() and src not in seen:
            seen.add(src)
            all_files.append(src)

    # Stufe 1: nach Dateigröße gruppieren.
    by_size: dict[int, list[Path]] = {}
    for f in all_files:
        try:
            size = f.stat().st_size
        except OSError:
            continue
        if size == 0:
            continue
        by_size.setdefault(size, []).append(f)
    size_candidates = [group for group in by_size.values() if len(group) > 1]

    total = sum(len(g) for g in size_candidates)
    done = 0

    # Stufe 2: Teil-Hash innerhalb jeder Größen-Gruppe.
    by_partial: dict[tuple[int, str], list[Path]] = {}
    for size_group in size_candidates:
        for f in size_group:
            done += 1
            try:
                phash = _partial_hash(f)
                size = f.stat().st_size
            except OSError:
                if progress_callback:
                    progress_callback(done, total, "partial")
                continue
            by_partial.setdefault((size, phash), []).append(f)
            if progress_callback:
                progress_callback(done, total, "partial")
    partial_candidates = [group for group in by_partial.values() if len(group) > 1]

    total = sum(len(g) for g in partial_candidates)
    done = 0

    # Stufe 3: voller Hash innerhalb jeder Teil-Hash-Gruppe -> endgültige Gruppen.
    by_full: dict[tuple[int, str], list[tuple[Path, float]]] = {}
    for partial_group in partial_candidates:
        for f in partial_group:
            done += 1
            try:
                fhash = _full_hash(f)
                stat = f.stat()
            except OSError:
                if progress_callback:
                    progress_callback(done, total, "full")
                continue
            by_full.setdefault((stat.st_size, fhash), []).append((f, stat.st_mtime))
            if progress_callback:
                progress_callback(done, total, "full")

    groups = []
    for entries in by_full.values():
        if len(entries) < 2:
            continue
        entries.sort(key=lambda pair: pair[1])  # älteste zuerst -> Original-Vorschlag
        files = [FileEntry(path=p, size=p.stat().st_size, mtime=mtime) for p, mtime in entries]
        groups.append(DuplicateGroup(files=files))

    groups.sort(key=lambda g: g.wasted_bytes, reverse=True)
    return groups


# ---------------------------------------------------------------------------
# Duplikate verschieben (inkl. Rückgängig machen)
# ---------------------------------------------------------------------------

def _find_root(path: Path, roots: list[Path]) -> Path:
    """Liefert die (tiefste) Quelle aus `roots`, unter der `path` liegt -
    damit bleibt die Ordnerstruktur beim Verschieben erhalten. Liegt `path`
    unter keiner der Quellen (sollte nicht vorkommen), wird ersatzweise der
    direkte Elternordner der Datei verwendet."""
    best = None
    for root in roots:
        if root == path:
            continue
        try:
            path.relative_to(root)
        except ValueError:
            continue
        if best is None or len(root.parts) > len(best.parts):
            best = root
    return best if best is not None else path.parent


def _unique_path(path: Path) -> Path:
    """Hängt bei Namenskonflikt einen dreistelligen Zähler an (wie im
    Datei-Umbenenner), z.B. 'bild.jpg' -> 'bild_001.jpg'."""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{stem}_{counter:03d}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def move_to_duplicates_folder(files: list[Path], roots: list[Path]) -> list[tuple[str, str]]:
    """Verschiebt die gegebenen Dateien in einen 'Duplikate'-Unterordner der
    jeweils zugehörigen Quelle, die relative Ordnerstruktur darunter bleibt
    erhalten (z.B. landet 'Fotos/2020/bild.jpg' in
    'Fotos/Duplikate/2020/bild.jpg'). Bei Namenskonflikten im Zielordner
    wird automatisch ein Zähler angehängt.

    Schreibt zusätzlich ein Log (LOG_FILE) für undo_last_move() und gibt die
    Liste (alter Pfad, neuer Pfad) als Strings zurück.
    """
    performed: list[tuple[str, str]] = []
    for f in files:
        root = _find_root(f, roots)
        rel = f.relative_to(root)
        target = root / DUPLICATES_FOLDER_NAME / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target = _unique_path(target)
        shutil.move(str(f), str(target))
        performed.append((str(f), str(target)))

    if performed:
        LOG_FILE.write_text(json.dumps(performed, ensure_ascii=False, indent=2))
    return performed


def has_undo() -> bool:
    return LOG_FILE.exists()


def undo_last_move() -> tuple[int, list[str]]:
    """Macht die zuletzt per move_to_duplicates_folder() ausgeführte Aktion
    rückgängig - verschiebt jede Datei von ihrem neuen zurück an ihren alten
    Pfad. Gibt (Anzahl erfolgreich, Liste der Fehlermeldungen) zurück."""
    if not LOG_FILE.exists():
        return 0, []
    entries = json.loads(LOG_FILE.read_text())
    ok = 0
    errors: list[str] = []
    for old, new in reversed(entries):
        old_path, new_path = Path(old), Path(new)
        try:
            if not new_path.exists():
                raise FileNotFoundError(f"'{new_path}' existiert nicht mehr")
            old_path.parent.mkdir(parents=True, exist_ok=True)
            target = old_path if not old_path.exists() else _unique_path(old_path)
            shutil.move(str(new_path), str(target))
            ok += 1
        except OSError as exc:
            errors.append(f"{new_path.name}: {exc}")
    LOG_FILE.unlink(missing_ok=True)
    return ok, errors


# ---------------------------------------------------------------------------
# Kleinkram
# ---------------------------------------------------------------------------

def format_size(num_bytes: int) -> str:
    """Menschlich lesbare Größenangabe (z.B. '3,4 MB')."""
    value = float(num_bytes)
    for unit in ("Bytes", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            if unit == "Bytes":
                return f"{int(value)} {unit}"
            return f"{value:.1f}".replace(".", ",") + f" {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    try:
        data = json.loads(SETTINGS_FILE.read_text())
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2))
