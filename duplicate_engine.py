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

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

PARTIAL_HASH_BYTES = 64 * 1024  # 64 KB
CHUNK_SIZE = 1024 * 1024  # 1 MB - Lesepuffer für den vollen Hash
DUPLICATES_FOLDER_NAME = "Duplikate"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".tif", ".webp"}
PHASH_SIZE = 8  # 8x8 -> 64-Bit-Hash
SIMILARITY_THRESHOLD = 10  # von 64 Bits verschieden - toleriert leichte Unterschiede

SETTINGS_FILE = Path(__file__).parent / "app_settings.json"
LOG_FILE = Path(__file__).parent / ".last_move_log.json"


@dataclass
class FileEntry:
    path: Path
    size: int
    mtime: float


@dataclass
class DuplicateGroup:
    """Eine Gruppe inhaltlich identischer ("exact") oder visuell ähnlicher
    ("similar", nur bei Bildern) Dateien.

    Bei `kind == "exact"` ist `files` nach Änderungsdatum aufsteigend
    sortiert (älteste zuerst) - die älteste Datei gilt als Vorschlag fürs
    "Original". Bei `kind == "similar"` nach Dateigröße absteigend (größte
    zuerst) - die größte Datei gilt als Vorschlag (vermutlich beste
    Qualität). In main.py ist jeweils Index 0 vorausgewählt zum Behalten,
    vom Nutzer per Häkchen änderbar. `similarity` (nur bei "similar") ist
    die durchschnittliche Ähnlichkeit aller Datei-Paare der Gruppe (0..1)."""

    files: list[FileEntry]
    kind: str = "exact"
    similarity: float | None = None

    @property
    def size(self) -> int:
        return self.files[0].size

    @property
    def wasted_bytes(self) -> int:
        """Speicherplatz, der sich durch Entfernen aller bis auf eine Datei
        aus dieser Gruppe sparen ließe."""
        if self.kind == "exact":
            return self.size * (len(self.files) - 1)
        # Bei "similar" haben die Dateien unterschiedliche Größen - alle bis
        # auf die größte (die vorausgewählt bleibt) zählen als einsparbar.
        sizes = sorted((f.size for f in self.files), reverse=True)
        return sum(sizes[1:])


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

def collect_files(sources: list[Path], recursive: bool = True) -> list[Path]:
    """Löst die gegebenen Quellen (Ordner und/oder einzelne Dateien) zu einer
    flachen, deduplizierten Liste von Dateipfaden auf."""
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
    return all_files


def scan_for_duplicates(sources: list[Path], recursive: bool = True,
                         progress_callback=None) -> list[DuplicateGroup]:
    """Durchsucht die gegebenen Quellen und liefert alle gefundenen exakten
    Duplikat-Gruppen - Komfort-Wrapper um collect_files() + find_exact_duplicates()
    (siehe dort für Details zu progress_callback)."""
    return find_exact_duplicates(collect_files(sources, recursive=recursive), progress_callback=progress_callback)


def find_exact_duplicates(all_files: list[Path], progress_callback=None) -> list[DuplicateGroup]:
    """Gruppiert die gegebenen Dateien nach exakt identischem Inhalt (mind. 2
    Dateien je Gruppe) - Gruppe mit dem meisten verschwendeten Speicherplatz
    zuerst.

    `progress_callback(done, total, phase)` wird optional nach jeder
    verarbeiteten Datei aufgerufen (phase: "partial"/"full") - für eine
    Fortschrittsanzeige in der Oberfläche. Nicht mehr lesbare Dateien
    (fehlende Berechtigung, währenddessen gelöscht, ...) werden übersprungen.
    """
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
        groups.append(DuplicateGroup(files=files, kind="exact"))

    groups.sort(key=lambda g: g.wasted_bytes, reverse=True)
    return groups


# ---------------------------------------------------------------------------
# Ähnliche Bilder (Perceptual Hashing, "near-duplicates")
# ---------------------------------------------------------------------------

def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTENSIONS


def _dhash(path: Path, hash_size: int = PHASH_SIZE) -> int | None:
    """Differenz-Hash (dHash): verkleinert das Bild auf (hash_size+1)x
    hash_size Graustufen-Pixel und kodiert je Zeile, ob ein Pixel heller als
    sein rechter Nachbar ist, als ein Bit. Robust gegen leichte Änderungen
    durch erneutes Speichern/Skalieren/Komprimieren - anders als der exakte
    SHA-256-Vergleich oben. Liefert None, wenn Pillow fehlt oder die Datei
    sich nicht als Bild öffnen lässt."""
    if not PILLOW_AVAILABLE:
        return None
    try:
        with Image.open(path) as img:
            img = img.convert("L").resize((hash_size + 1, hash_size), Image.LANCZOS)
            pixels = list(img.getdata())
    except Exception:
        return None
    bits = 0
    for row in range(hash_size):
        offset = row * (hash_size + 1)
        for col in range(hash_size):
            bits = (bits << 1) | (1 if pixels[offset + col] < pixels[offset + col + 1] else 0)
    return bits


def _hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def scan_for_similar_images(files: list[Path], threshold: int = SIMILARITY_THRESHOLD,
                             progress_callback=None) -> list[DuplicateGroup]:
    """Gruppiert Bilddateien unter den gegebenen `files` nach visueller
    Ähnlichkeit (Perceptual Hashing, nicht exakter Bytevergleich) - findet
    z.B. dasselbe Foto in anderer Auflösung/Kompression. `files` sollte
    bereits um exakte Duplikate bereinigt sein (siehe main.py), sonst
    entstünden doppelte Gruppen für dieselben Dateien.

    Zwei Bilder gelten als ähnlich, wenn sich ihre 64-Bit-Hashes in höchstens
    `threshold` Bits unterscheiden. Mehrere paarweise ähnliche Bilder werden
    transitiv zu einer gemeinsamen Gruppe zusammengefasst (Union-Find).
    Braucht Pillow (PILLOW_AVAILABLE) - ohne das Paket liefert diese Funktion
    eine leere Liste.
    """
    if not PILLOW_AVAILABLE:
        return []

    images = [f for f in files if is_image(f)]
    hashes: dict[Path, int] = {}
    for i, f in enumerate(images):
        h = _dhash(f)
        if h is not None:
            hashes[f] = h
        if progress_callback:
            progress_callback(i + 1, len(images), "phash")

    paths = list(hashes.keys())
    parent = {p: p for p in paths}

    def find(x: Path) -> Path:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: Path, b: Path) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            if _hamming(hashes[paths[i]], hashes[paths[j]]) <= threshold:
                union(paths[i], paths[j])

    clusters: dict[Path, list[Path]] = {}
    for p in paths:
        clusters.setdefault(find(p), []).append(p)

    groups = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        entries = []
        for p in members:
            try:
                stat = p.stat()
            except OSError:
                continue
            entries.append(FileEntry(path=p, size=stat.st_size, mtime=stat.st_mtime))
        if len(entries) < 2:
            continue
        entries.sort(key=lambda e: e.size, reverse=True)  # größte zuerst -> Original-Vorschlag (beste Qualität)

        pair_similarities = [
            1 - _hamming(hashes[members[i]], hashes[members[j]]) / (PHASH_SIZE * PHASH_SIZE)
            for i in range(len(members)) for j in range(i + 1, len(members))
        ]
        similarity = sum(pair_similarities) / len(pair_similarities) if pair_similarities else None
        groups.append(DuplicateGroup(files=entries, kind="similar", similarity=similarity))

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
