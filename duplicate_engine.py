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
from datetime import datetime
from pathlib import Path

try:
    from PIL import ExifTags, Image
    from PIL.ExifTags import TAGS
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

try:
    import docx  # python-docx - fürs Anzeigen von .docx-Dateien im Datei-Viewer
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False

try:
    # Verschiebt Dateien plattformübergreifend in den System-Papierkorb
    # (macOS/Windows/Linux) statt sie endgültig zu löschen - für den
    # "🗑 Markierte Zeilen löschen"-Button in main.py (siehe move_to_trash()
    # weiter unten). Identisch zum Datei-Umbenenner übernommen.
    import send2trash
    HAS_SEND2TRASH = True
except ImportError:
    HAS_SEND2TRASH = False

PARTIAL_HASH_BYTES = 64 * 1024  # 64 KB
CHUNK_SIZE = 1024 * 1024  # 1 MB - Lesepuffer für den vollen Hash
DUPLICATES_FOLDER_NAME = "Duplikate"

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".tif", ".webp"}
PHASH_SIZE = 8  # 8x8 -> 64-Bit-Hash
SIMILARITY_THRESHOLD = 10  # von 64 Bits verschieden - toleriert leichte Unterschiede

# Für den Datei-Viewer (document_viewer.py) - identisch zum Datei-Umbenenner.
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".log", ".json", ".yaml", ".yml"}

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

def _is_within(path: Path, ancestor: Path) -> bool:
    try:
        path.relative_to(ancestor)
        return True
    except ValueError:
        return False


def list_files(folder: Path, recursive: bool, include_hidden: bool = False,
                exclude_dirs: set[Path] | None = None) -> list[Path]:
    """Listet alle Dateien in `folder` - rekursiv über Unterordner, sofern
    gewünscht. Der App-eigene "Duplikate"-Ausgabeordner wird dabei immer
    übersprungen, damit bereits verschobene Duplikate nicht bei einem
    erneuten Scan wieder als Quelle mitgezählt werden. `exclude_dirs`
    überspringt zusätzlich alle Dateien unterhalb der angegebenen Ordner -
    z.B. einen konfigurierten zentralen Zielordner mit abweichendem Namen
    (siehe collect_files/move_to_duplicates_folder)."""
    pattern = "**/*" if recursive else "*"
    exclude_dirs = exclude_dirs or set()
    files = []
    for p in sorted(folder.glob(pattern)):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(folder).parts
        # Prüft ALLE Pfadteile (Datei + jeden Unterordner darüber), nicht
        # nur den Dateinamen selbst - sonst würden z.B. Dateien in einem
        # ".git"-Unterordner trotz include_hidden=False durchsucht, weil
        # nur ihr eigener (unversteckter) Name geprüft wurde.
        if not include_hidden and any(part.startswith(".") for part in rel_parts):
            continue
        if DUPLICATES_FOLDER_NAME in rel_parts[:-1]:
            continue
        if any(_is_within(p, ex) for ex in exclude_dirs):
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

def collect_files(sources: list[Path], recursive: bool = True,
                   exclude_dirs: set[Path] | None = None) -> list[Path]:
    """Löst die gegebenen Quellen (Ordner und/oder einzelne Dateien) zu einer
    flachen, deduplizierten Liste von Dateipfaden auf. `exclude_dirs` siehe
    list_files()."""
    all_files: list[Path] = []
    seen: set[Path] = set()
    for src in sources:
        if src.is_dir():
            for f in list_files(src, recursive=recursive, exclude_dirs=exclude_dirs):
                if f not in seen:
                    seen.add(f)
                    all_files.append(f)
        elif src.is_file() and src not in seen:
            seen.add(src)
            all_files.append(src)
    return all_files


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
        files = []
        for p, mtime in entries:
            try:
                files.append(FileEntry(path=p, size=p.stat().st_size, mtime=mtime))
            except OSError:
                continue  # zwischenzeitlich gelöscht/unlesbar geworden - wie in Stufe 1-3 überspringen statt abzubrechen
        if len(files) >= 2:
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


# Sicherheitsnetz gegen exponentielle Laufzeit der Cliquen-Suche (Bron-
# Kerbosch, siehe _find_cliques) bei sehr großen, dicht vernetzten
# Nachbarschaften - in der Praxis bei Foto-Duplikaten unüblich (meist
# einstellige bis niedrige zweistellige Gruppengrößen).
MAX_CLIQUE_NEIGHBORHOOD_SIZE = 60


def _avg_pair_similarity(members, hashes: dict[Path, int]) -> float:
    members = list(members)
    if len(members) < 2:
        return 0.0
    sims = [
        1 - _hamming(hashes[members[i]], hashes[members[j]]) / (PHASH_SIZE * PHASH_SIZE)
        for i in range(len(members)) for j in range(i + 1, len(members))
    ]
    return sum(sims) / len(sims)


def recompute_similarity(paths: list[Path]) -> float | None:
    """Berechnet die durchschnittliche paarweise Ähnlichkeit (0..1) der
    gegebenen Bilder neu - z.B. nachdem eine "Ähnliche Bilder"-Gruppe durch
    Verschieben/Löschen einzelner Dateien geschrumpft ist und der zuvor für
    die GESAMTE Gruppe berechnete Wert nicht mehr zu den verbleibenden
    Dateien passt. None, wenn Pillow fehlt oder weniger als 2 Bilder lesbar
    übrig sind (main.py zeigt dann keinen Ähnlichkeitswert an)."""
    if not PILLOW_AVAILABLE:
        return None
    hashes = {}
    for p in paths:
        h = _dhash(p)
        if h is not None:
            hashes[p] = h
    if len(hashes) < 2:
        return None
    return _avg_pair_similarity(list(hashes.keys()), hashes)


def _find_cliques(members: list[Path], adjacency: dict[Path, set[Path]]) -> list[set[Path]]:
    """Findet alle maximalen Cliquen (Bron-Kerbosch, ohne Pivot) innerhalb
    `members` - Teilmengen, in denen WIRKLICH jedes Bild zu jedem anderen
    ähnlich genug ist (nicht nur transitiv über eine Kette verbunden, siehe
    scan_for_similar_images). Bei zu großen Nachbarschaften (siehe
    MAX_CLIQUE_NEIGHBORHOOD_SIZE) wird ersatzweise die gesamte Nachbarschaft
    als eine einzige (lockerere) Gruppe zurückgegeben, um keine exponentielle
    Laufzeit zu riskieren."""
    if len(members) > MAX_CLIQUE_NEIGHBORHOOD_SIZE:
        return [set(members)]

    cliques: list[set[Path]] = []

    def bron_kerbosch(r: set[Path], p: set[Path], x: set[Path]) -> None:
        if not p and not x:
            if len(r) >= 2:
                cliques.append(set(r))
            return
        for v in list(p):
            bron_kerbosch(r | {v}, p & adjacency[v], x & adjacency[v])
            p = p - {v}
            x = x | {v}

    bron_kerbosch(set(), set(members), set())
    return cliques


def scan_for_similar_images(files: list[Path], threshold: int = SIMILARITY_THRESHOLD,
                             progress_callback=None) -> list[DuplicateGroup]:
    """Gruppiert Bilddateien unter den gegebenen `files` nach visueller
    Ähnlichkeit (Perceptual Hashing, nicht exakter Bytevergleich) - findet
    z.B. dasselbe Foto in anderer Auflösung/Kompression. `files` sollte
    bereits um exakte Duplikate bereinigt sein (siehe main.py), sonst
    entstünden doppelte Gruppen für dieselben Dateien.

    Zwei Bilder gelten als ähnlich, wenn sich ihre 64-Bit-Hashes in höchstens
    `threshold` Bits unterscheiden. Innerhalb einer Gruppe muss das für
    JEDES Paar gelten (echte Cliquen, siehe _find_cliques) - nicht nur
    transitiv über eine Kette verbunden sein. Sonst könnten z.B. bei A~B und
    B~C auch A und C in derselben Gruppe landen, obwohl A und C direkt
    verglichen gar nicht mehr ähnlich genug sind ("Chaining"-Problem bei
    Single-Linkage-Clustering) - das war vorher der Fall und führte zu
    sichtbar unpassenden Gruppen. Jedes Bild landet höchstens in einer
    Gruppe (größte/ähnlichste Cliquen zuerst vergeben).

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
    adjacency: dict[Path, set[Path]] = {p: set() for p in paths}

    def find(x: Path) -> Path:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: Path, b: Path) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Erster Durchlauf: grobe Nachbarschaften per Union-Find ermitteln (wie
    # zuvor) - dient hier nur noch dazu, die anschließende (teurere)
    # Cliquen-Suche auf kleine, bereits eingegrenzte Nachbarschaften zu
    # beschränken, statt über alle Bilder auf einmal zu laufen. Gleichzeitig
    # wird die Kantenliste (adjacency) für die Cliquen-Suche mitgesammelt.
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            if _hamming(hashes[paths[i]], hashes[paths[j]]) <= threshold:
                union(paths[i], paths[j])
                adjacency[paths[i]].add(paths[j])
                adjacency[paths[j]].add(paths[i])

    neighborhoods: dict[Path, list[Path]] = {}
    for p in paths:
        neighborhoods.setdefault(find(p), []).append(p)

    groups = []
    for members in neighborhoods.values():
        if len(members) < 2:
            continue

        cliques = _find_cliques(members, adjacency)
        # Größte Cliquen zuerst, bei Gleichstand die mit der höheren
        # durchschnittlichen Ähnlichkeit - so werden die "saubersten"
        # Gruppen zuerst vergeben.
        cliques.sort(key=lambda c: (len(c), _avg_pair_similarity(c, hashes)), reverse=True)

        already_used: set[Path] = set()
        for clique in cliques:
            if clique & already_used:
                continue  # Bild schon einer besseren Clique zugeordnet
            already_used |= clique

            entries = []
            for p in clique:
                try:
                    stat = p.stat()
                except OSError:
                    continue
                entries.append(FileEntry(path=p, size=stat.st_size, mtime=stat.st_mtime))
            if len(entries) < 2:
                continue
            entries.sort(key=lambda e: e.size, reverse=True)  # größte zuerst -> Original-Vorschlag (beste Qualität)

            groups.append(DuplicateGroup(files=entries, kind="similar", similarity=_avg_pair_similarity(clique, hashes)))

    groups.sort(key=lambda g: g.wasted_bytes, reverse=True)
    return groups


# ---------------------------------------------------------------------------
# Datei-Viewer: Foto-Metadaten + Geocoding (identisch zum Datei-Umbenenner) -
# wird von document_viewer.py genutzt, um bei echten Kamerafotos eine kleine
# Metadaten-Zeile (Datum/Kamera/Ort) samt "🌐 Ort ermitteln"-Button anzuzeigen.
# reverse_geocode() ist die EINZIGE Stelle in der ganzen App, die eine
# Internetverbindung braucht (Abfrage bei OpenStreetMap/Nominatim) - wird nie
# automatisch aufgerufen, sondern nur auf diesen Klick hin.
# ---------------------------------------------------------------------------

def _dms_to_decimal(dms, ref) -> float | None:
    """Wandelt eine EXIF-GPS-Koordinate (Grad/Minuten/Sekunden) in eine
    Dezimalzahl um - negativ bei Süd/West."""
    try:
        deg, minutes, seconds = (float(v) for v in dms)
    except (TypeError, ValueError):
        return None
    value = deg + minutes / 60 + seconds / 3600
    return -value if str(ref) in ("S", "W") else value


def extract_photo_metadata(path: Path) -> dict:
    """Liest gängige EXIF-Metadaten eines Fotos aus (Aufnahmedatum, GPS-
    Koordinaten, Kamerahersteller/-modell) - nur bei echten Kamerabildern
    vorhanden, komplett offline (keine Internetverbindung nötig). Fehlende
    Felder fehlen im Ergebnis-dict.

    Mögliche Schlüssel: "date" (Text "JJJJ-MM-TT"), "date_obj" (datetime),
    "camera" (Text), "latitude"/"longitude" (float, Dezimalgrad)."""
    result: dict = {}
    if not PILLOW_AVAILABLE:
        return result
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return result
            tag_map = {TAGS.get(tag_id, tag_id): value for tag_id, value in exif.items()}
            # DateTimeOriginal steht nicht im Haupt-IFD (das liefert
            # exif.items() allein), sondern im Exif-SubIFD - ohne diesen
            # Zusatzschritt bleibt das Aufnahmedatum bei den meisten echten
            # Kamerafotos leer, obwohl es vorhanden ist (analog zum
            # GPS-SubIFD-Zugriff weiter unten).
            try:
                exif_sub_ifd = exif.get_ifd(ExifTags.IFD.Exif)
                tag_map.update({TAGS.get(tag_id, tag_id): value for tag_id, value in exif_sub_ifd.items()})
            except Exception:
                pass

            date_str = tag_map.get("DateTimeOriginal") or tag_map.get("DateTime")
            if date_str:
                try:
                    dt = datetime.strptime(str(date_str), "%Y:%m:%d %H:%M:%S")
                    result["date_obj"] = dt
                    result["date"] = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass

            make = str(tag_map.get("Make", "")).strip()
            model = str(tag_map.get("Model", "")).strip()
            camera = model if model.startswith(make) else " ".join(p for p in (make, model) if p)
            if camera:
                result["camera"] = camera

            try:
                gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
            except Exception:
                gps_ifd = None
            if gps_ifd and 2 in gps_ifd and 4 in gps_ifd:
                lat = _dms_to_decimal(gps_ifd[2], gps_ifd.get(1, "N"))
                lon = _dms_to_decimal(gps_ifd[4], gps_ifd.get(3, "E"))
                if lat is not None and lon is not None:
                    result["latitude"] = lat
                    result["longitude"] = lon
    except Exception:
        pass
    return result


LOCATION_CACHE: dict[tuple[float, float], dict] = {}


def location_cache_key(lat: float, lon: float) -> tuple[float, float]:
    return (round(lat, 4), round(lon, 4))


def reverse_geocode(lat: float, lon: float, timeout: float = 6.0) -> dict | None:
    """Fragt bei OpenStreetMap/Nominatim Ort und Land zu GPS-Koordinaten ab.
    Gibt bei Erfolg {'ort': ..., 'land': ...} zurück - einzelne Werte können
    leer bleiben, falls Nominatim für diese Koordinate keine Adressdaten
    liefert (das ist dann trotzdem ein erfolgreiches Ergebnis und wird auch
    so zwischengespeichert). Gibt None zurück, wenn die Abfrage selbst
    fehlschlägt (z.B. kein Internet)."""
    key = location_cache_key(lat, lon)
    if key in LOCATION_CACHE:
        return LOCATION_CACHE[key]
    try:
        import urllib.parse
        import urllib.request

        url = "https://nominatim.openstreetmap.org/reverse?" + urllib.parse.urlencode(
            {"lat": lat, "lon": lon, "format": "jsonv2", "zoom": "10", "accept-language": "de"}
        )
        request = urllib.request.Request(
            url, headers={"User-Agent": "Datei-Duplikatfinder/1.0 (privates Hobby-Projekt)"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
        address = data.get("address", {})
        ort = (
            address.get("city") or address.get("town") or address.get("village")
            or address.get("municipality") or address.get("county") or ""
        )
        if not ort:
            ort = (data.get("display_name") or "").split(",")[0]
        land = address.get("country", "")
    except Exception:
        return None
    result = {"ort": ort, "land": land}
    LOCATION_CACHE[key] = result
    return result


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


def move_to_duplicates_folder(files: list[Path], roots: list[Path],
                               target_folder: Path | None = None) -> tuple[list[tuple[str, str]], list[str]]:
    """Verschiebt die gegebenen Dateien - die relative Ordnerstruktur
    innerhalb ihrer jeweiligen Quelle bleibt dabei erhalten (z.B. landet
    'Fotos/2020/bild.jpg' als 'Fotos/Duplikate/2020/bild.jpg' bzw. bei
    gesetztem `target_folder` als '<target_folder>/2020/bild.jpg'). Bei
    Namenskonflikten im Zielordner wird automatisch ein Zähler angehängt.

    - `target_folder=None` (Standard): jede Datei landet im
      'Duplikate'-Unterordner ihrer jeweiligen Quelle (siehe `roots`).
    - `target_folder=<Pfad>`: alle Dateien landen gemeinsam dort, unabhängig
      davon, aus welcher Quelle sie stammen.

    Jede Datei wird einzeln versucht - schlägt eine fehl (z.B. Berechtigung,
    Speicherplatz), werden die zuvor bereits erfolgreich verschobenen Dateien
    trotzdem behalten/protokolliert, statt komplett verworfen zu werden.
    Schreibt ein Log (LOG_FILE) für undo_last_move() und gibt
    (erfolgreiche (alter Pfad, neuer Pfad)-Paare, Fehlermeldungen) zurück.
    """
    performed: list[tuple[str, str]] = []
    errors: list[str] = []
    for f in files:
        try:
            root = _find_root(f, roots)
            rel = f.relative_to(root)
            base = target_folder if target_folder is not None else (root / DUPLICATES_FOLDER_NAME)
            target = base / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target = _unique_path(target)
            shutil.move(str(f), str(target))
            performed.append((str(f), str(target)))
        except OSError as exc:
            errors.append(f"{f.name}: {exc}")

    if performed:
        LOG_FILE.write_text(json.dumps(performed, ensure_ascii=False, indent=2))
    return performed, errors


def has_undo() -> bool:
    return LOG_FILE.exists()


def undo_last_move() -> tuple[int, list[str]]:
    """Macht die zuletzt per move_to_duplicates_folder() ausgeführte Aktion
    rückgängig - verschiebt jede Datei von ihrem neuen zurück an ihren alten
    Pfad. Gibt (Anzahl erfolgreich, Liste der Fehlermeldungen) zurück.

    Schlägt einzelne Dateien fehl (z.B. Ursprungsordner inzwischen
    schreibgeschützt), wird das Log NICHT komplett gelöscht, sondern nur um
    die erfolgreich wiederhergestellten Einträge bereinigt - die
    fehlgeschlagenen bleiben für einen erneuten Versuch erhalten, statt
    ihre alter-Pfad/neuer-Pfad-Zuordnung unwiderruflich zu verlieren."""
    if not LOG_FILE.exists():
        return 0, []
    entries = json.loads(LOG_FILE.read_text())
    ok = 0
    errors: list[str] = []
    failed_indices: set[int] = set()
    for i in range(len(entries) - 1, -1, -1):
        old, new = entries[i]
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
            failed_indices.add(i)

    if failed_indices:
        LOG_FILE.write_text(json.dumps([entries[i] for i in sorted(failed_indices)], ensure_ascii=False, indent=2))
    else:
        LOG_FILE.unlink(missing_ok=True)
    return ok, errors


def move_to_trash(paths: list[Path]) -> tuple[int, list[str]]:
    """Verschiebt die angegebenen Dateien in den System-Papierkorb (nicht
    endgültig, im Unterschied zu move_to_duplicates_folder()/undo_last_move()
    aber auch nicht über eigene Rückgängig-Funktion rückholbar - dafür ist
    der Papierkorb selbst zuständig). Gibt (Anzahl, Fehler) zurück. Ohne
    installiertes send2trash (siehe HAS_SEND2TRASH) wird nichts gelöscht -
    main.py deaktiviert den zugehörigen Button in dem Fall bereits vorher.
    Identisch zum Datei-Umbenenner übernommen."""
    if not HAS_SEND2TRASH:
        return 0, ["Paket 'send2trash' nicht installiert - siehe requirements.txt."]

    count = 0
    errors: list[str] = []
    for path in paths:
        try:
            send2trash.send2trash(str(path))
            count += 1
        except OSError as e:
            errors.append(f"{path.name}: {e}")
    return count, errors


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
