# Datei-Duplikatfinder

Eine kleine Desktop-App, die Ordner nach doppelten Dateien durchsucht und
sie hervorhebt. Die Oberfläche nutzt
[PySide6](https://doc.qt.io/qtforpython/) (die Python-Anbindung von Qt) für
ein modernes, natives Aussehen inklusive Dark-Mode-Unterstützung und
eingebautem Drag & Drop - aufgebaut nach demselben Muster wie der
[Datei-Umbenenner](../file_renamer).

## Starten

```bash
cd Datei-Duplikatfinder
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Alternativ per Doppelklick auf **„App öffnen.command“** (macOS - nutzt das
fest hinterlegte Python unter `/opt/homebrew/opt/python@3.14/bin/python3.14`,
dort muss `PySide6` installiert sein). Öffnet dabei ein Terminal-Fenster mit
der laufenden Ausgabe.

Ein Versuch, stattdessen ein echtes `.app`-Bundle (ohne Terminal-Fenster) zu
bauen, zeigte einen hartnäckigen grauen Rand um das Icon und wurde
zurückgestellt - siehe [ROADMAP.md](ROADMAP.md).

Beide sind an den festen Pfad dieses Projektordners gebunden (nicht
verschiebbar, ohne den Pfad im jeweiligen Skript anzupassen).

## Funktionsweise

1. **Quellordner auswählen** – *Drop-Zone*: Ordner (oder einzelne Dateien)
   hineinziehen, auch mehrere auf einmal, oder klicken für den klassischen
   Ordner-Auswahldialog. Rechts daneben, übereinander gestapelt: **„↺“**
   setzt die Auswahl zurück, **„📌“** merkt sich den aktuell geladenen
   Ordner dauerhaft als *Fester Standardordner* (gespeichert in
   `app_settings.json` – wird dann bei jedem App-Start automatisch
   geladen), **„✕“** hebt das wieder auf.
2. **Optionen** – „Unterordner einbeziehen (rekursiv)“ ist standardmäßig
   angehakt und bezieht beim Scannen alle Unterordner der Quelle(n) mit
   ein; abschaltbar für einen Vergleich nur der obersten Ebene. Die
   Einstellung wird gemerkt. Über das ℹ️-Symbol steht, wonach genau
   verglichen wird (siehe auch nächster Abschnitt).
   „🖼️ Ähnliche Bilder zusätzlich erkennen (experimentell)“ – standardmäßig
   **aus** – findet zusätzlich Bilder, die sich zwar leicht unterscheiden
   (andere Auflösung, erneut komprimiert), aber ganz ähnlich aussehen
   (Perceptual Hashing statt exaktem Vergleich, siehe nächster Abschnitt).
   Braucht das Paket `Pillow` – fehlt es, bleibt die Option wirkungslos
   (Hinweis daneben).
   **Zielordner** – standardmäßig landet jede verschobene Datei im
   `Duplikate`-Unterordner ihrer jeweiligen Quelle; über „Ändern…“ lässt
   sich stattdessen ein einziger, zentraler Zielordner für alle
   verschobenen Duplikate festlegen (gespeichert in `app_settings.json`,
   bleibt über einen Neustart hinweg erhalten), „↺ Standard“ setzt das
   wieder zurück. Liegt der zentrale Zielordner innerhalb einer der
   Quellen, wird er beim Scannen automatisch übersprungen.
3. **„🔍 Auf Duplikate prüfen“** – durchsucht die Quelle(n) in einem
   Hintergrund-Thread (die Oberfläche bleibt währenddessen bedienbar) und
   zeigt den Fortschritt an.
4. **Ergebnis** – je gefundene Gruppe eine Zeile mit Anzahl Dateien und
   einsparbarem Speicherplatz, darunter aufgeklappt die einzelnen Dateien
   mit Pfad, Größe und Änderungsdatum. Bei exakten Duplikaten ist die
   **älteste Datei** je Gruppe mit „🟢 Original“ markiert, bei ähnlichen
   Bildern („🖼️ Ähnliche Bilder N“, mit ungefährem Ähnlichkeitswert in der
   Gruppenzeile) die **größte Datei** mit „🖼️ Beste Qualität“ – deren
   Häkchen ist jeweils standardmäßig **nicht** gesetzt, alle anderen
   Dateien der Gruppe sind angehakt. Über **„☑ Alle auswählen“**/
   „☐ Alle abwählen“ lässt sich das für alle Zeilen auf einmal umschalten,
   **„↺ Auswahl zurücksetzen“** stellt die ursprüngliche Vorauswahl wieder
   her.
5. **„🗂 Ausgewählte in 'Duplikate'-Ordner verschieben“** – verschiebt alle
   angehakten Dateien in den `Duplikate`-Unterordner ihrer jeweiligen
   Quelle, oder - falls unter „Optionen“ festgelegt - gemeinsam in den
   konfigurierten zentralen Zielordner (die Ordnerstruktur innerhalb der
   Quelle bleibt jeweils erhalten). Nichts wird gelöscht. **„↺ Verschieben
   rückgängig machen“** macht die zuletzt durchgeführte Aktion wieder
   vollständig rückgängig.

## Vergleichskriterium

Zwei Dateien gelten als Duplikat, wenn sie **exakt denselben Inhalt**
haben - unabhängig vom Dateinamen. Geprüft wird gestuft, um bei vielen/
großen Dateien nicht unnötig viel lesen zu müssen:

1. **Dateigröße** – schnellster erster Filter.
2. **Teil-Prüfsumme** (erste 64 KB) – filtert die meisten restlichen
   Nicht-Duplikate heraus, ohne die ganze Datei zu lesen.
3. **Volle Prüfsumme** (SHA-256) – nur noch für die verbliebenen
   Kandidaten berechnet, das ist die verlässliche Bestätigung.

0-Byte-Dateien werden ignoriert.

**Ähnliche Bilder** (optionale Zusatzoption, siehe oben) werden dagegen
über einen **Bildvergleich** erkannt, nicht über exakte Prüfsummen: Jedes
Bild wird auf 8×8 Graustufen-Pixel verkleinert und daraus ein 64-Bit
„Differenz-Hash“ (dHash) gebildet - zwei Bilder gelten als ähnlich, wenn
sich ihre Hashes in höchstens 10 der 64 Bits unterscheiden. Das ist robust
gegen erneutes Speichern/Skalieren/leichte Bearbeitung, kann aber auch mal
tatsächlich unterschiedliche Bilder als „ähnlich“ einstufen – deshalb vor
dem Verschieben prüfen. Nur Bilder, die nicht schon als exaktes Duplikat
erkannt wurden, werden hierfür verglichen (keine doppelten Gruppen).

## Projektstruktur

- `main.py` – Oberfläche (PySide6)
- `duplicate_engine.py` – Scan-/Hash-/Verschiebe-Logik, unabhängig von der Oberfläche
- `qt_widgets.py` – wiederverwendbare UI-Bausteine (identisch zum Datei-Umbenenner)
