# Datei-Duplikatfinder

Eine kleine Desktop-App, die Ordner nach doppelten Dateien durchsucht und
sie hervorhebt. Die Oberfläche nutzt
[PySide6](https://doc.qt.io/qtforpython/) (die Python-Anbindung von Qt) für
ein modernes, natives Aussehen inklusive Dark-Mode-Unterstützung und
eingebautem Drag & Drop - aufgebaut nach demselben Muster wie der
[Datei-Umbenenner](../file_renamer).

## Starten

Setzt voraus, dass [`qt-app-kit`](../qt-app-kit) (geteilte UI-Bausteine) als
Geschwister-Ordner neben diesem Projekt liegt.

```bash
cd Datei-Duplikatfinder
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Für den Alltag gibt es zwei Doppelklick-Varianten (macOS), beide fest an
den Pfad dieses Projektordners gebunden (nicht verschiebbar, ohne den Pfad
im jeweiligen Skript/Bundle anzupassen):

- **„Datei-Duplikatfinder.app“** – echtes App-Bundle, kein Terminal-Fenster.
  Fehler landen in `.app_launch.log` im Projektordner statt in der Konsole.
  Ein zweiter Doppelklick bei bereits laufender App holt das bestehende
  Fenster nach vorne, statt einen zweiten Prozess zu starten. Dafür sorgt
  ein eigener Einzelinstanz-Mechanismus in `qt_app_kit/single_instance.py`
  (geteilt mit file_renamer; lokaler Qt-Socket, `QLocalServer`/`QLocalSocket`,
  plus `NSApplication.activateIgnoringOtherApps_()`
  via PyObjC, da Qts `raise_()`/`activateWindow()` allein die App nicht vor
  andere, gerade aktive Apps holt) - `LSMultipleInstancesProhibited` im
  Info.plist allein reicht nicht, da der Launcher `main.py` als
  eigenständigen Python-Prozess startet und macOS diesen Prozess nicht
  zuverlässig dem App-Bundle zuordnet. Frühere, von Hand gebaute Bundles
  zeigten einen kosmetischen grauen Rand ums Icon - behoben, indem das Icon
  zusätzlich per Finder-eigenem "Benutzerdefiniertes Symbol"-Mechanismus
  gesetzt wird (`NSWorkspace.setIcon_forFile_options_()`, nicht nur über
  `CFBundleIconFile`) - vom Nutzer am 07.09.2026 bestätigt: sauberes Icon,
  kein Rand mehr.
- **„App öffnen.command“** – Terminal-Fenster mit laufender Ausgabe bleibt
  sichtbar, dafür ohne jedes Icon-Risiko. Nutzt das fest hinterlegte Python
  unter `/opt/homebrew/opt/python@3.14/bin/python3.14`, dort muss
  `PySide6` installiert sein.

## Funktionsweise

Oben rechts, außerhalb des scrollbaren Bereichs: **„🌐 DE/EN“** wechselt die
Sprache der gesamten Oberfläche - wirkt erst nach einem Neustart der App
(Wahl wird in `app_settings.json` gespeichert, wie der Standardordner).

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
3. **Ergebnis** – oben der Button **„🔍 Auf Duplikate prüfen“**, der die
   Quelle(n) in einem Hintergrund-Thread durchsucht (die Oberfläche bleibt
   währenddessen bedienbar) und den Fortschritt anzeigt. Darunter je
   gefundene Gruppe eine fette Trennzeile mit Anzahl Dateien und
   einsparbarem Speicherplatz, gefolgt von den einzelnen Dateien mit
   Häkchen, Name, Ordner, Größe und Änderungsdatum. Bei exakten Duplikaten
   ist die **älteste Datei** je Gruppe mit vorangestelltem „🟢 Original“
   markiert, bei ähnlichen Bildern („🖼️ Ähnliche Bilder N“, mit ungefährem
   Ähnlichkeitswert in der Gruppenzeile) die **größte Datei** mit „🖼️ Beste
   Qualität“ – deren Häkchen (per anklickbarer Checkbox links vom Namen)
   ist jeweils standardmäßig **nicht** gesetzt, alle anderen Dateien der
   Gruppe sind angehakt. Über **„☑ Alle auswählen“**/„☐ Alle abwählen“
   lässt sich das für alle Zeilen auf einmal umschalten, **„↺ Auswahl
   zurücksetzen“** stellt die ursprüngliche Vorauswahl wieder her. Die
   Spalten „Datei“ und „Ordner“ lassen sich per Maus am Rand in der
   Kopfzeile in der Breite anpassen (z.B. um lange Ablagepfade zu prüfen).
4. **„🗂 Ausgewählte in 'Duplikate'-Ordner verschieben“** – verschiebt alle
   angehakten Dateien in den `Duplikate`-Unterordner ihrer jeweiligen
   Quelle, oder - falls unter „Optionen“ festgelegt - gemeinsam in den
   konfigurierten zentralen Zielordner (die Ordnerstruktur innerhalb der
   Quelle bleibt jeweils erhalten). Nichts wird gelöscht. **„↺ Verschieben
   rückgängig machen“** macht die zuletzt durchgeführte Aktion wieder
   vollständig rückgängig. Daneben **„🗑 Angehakte löschen“** – dieselbe
   Häkchen-Auswahl wie beim Verschieben, nur landen die Dateien direkt im
   System-Papierkorb statt im `Duplikate`-Ordner (siehe Punkt 5 für die
   Einschränkungen: kein Rückgängig über die App, braucht `send2trash`).
5. **„🗑 Markierte Zeilen löschen“** (identisch zum Datei-Umbenenner) –
   verschiebt die per Maus im Baum **markierten** Dateien (anklicken, mit
   Shift für zusammenhängende bzw. Cmd für einzelne Mehrfachauswahl) in den
   System-Papierkorb - eine von den Häkchen komplett unabhängige Auswahl
   (siehe „🗑 Angehakte löschen“ oben für die Häkchen-basierte Variante
   derselben Papierkorb-Aktion). Landet im Papierkorb, nicht endgültig
   gelöscht, aber auch nicht über die eingebaute Rückgängig-Funktion
   wiederherstellbar (dafür ist der Papierkorb selbst zuständig). Braucht
   das Paket `send2trash` - fehlt es, sind beide Löschen-Buttons deaktiviert
   (Hinweis im Tooltip). Daneben **„📂 Ablageort öffnen“** öffnet den Finder
   am Ort der aktuell in der Vorschau gezeigten Datei und markiert sie dort.

Sowohl „Verschieben" als auch „Löschen" aktualisieren die Ergebnisliste
danach **gezielt**: nur die betroffenen Dateien verschwinden aus ihren
Gruppen (eine Gruppe mit nur noch einer verbleibenden Datei fällt ganz
weg) - der Rest der zuvor gefundenen Duplikate bleibt sichtbar, ein neuer
Scan ist dafür nicht nötig. Die rechts angezeigte Vorschau bleibt dabei
ebenfalls erhalten, solange nicht ausgerechnet die dort gezeigte Datei
selbst betroffen war.

Rechts neben der Ergebnis-Tabelle zeigt ein **eingebauter Datei-Viewer**
(Grundgerüst identisch zum Datei-Umbenenner) die zur ausgewählten Zeile
gehörende Datei an - PDF, Bilder (inkl. Zoom), Text/Markdown/CSV/JSON/YAML,
Word (`.docx`, sofern `python-docx` installiert ist), PowerPoint (`.pptx`,
sofern `python-pptx` installiert ist - **nur Text je Folie**, keine
Bilder/Layout/Formatierung) sowie **Videos**
(`.mp4`/`.mov`/`.m4v`/`.avi`/`.mkv`/`.webm` - mit Play/Pause-Button und
Fortschrittsleiste; läuft über Qts eingebautes FFmpeg-Backend, tatsächlich
abspielbare Codecs hängen davon ab, nicht unterstützte Dateien zeigen eine
Fehlermeldung statt eines leeren Players). Bei Bildern und
PDF lässt sich mit dem **Trackpad navigieren**: Zwei-Finger-Wischen
scrollt, Zusammen-/Auseinanderziehen (Pinch) zoomt. **Zoom und Bildausschnitt
bleiben dabei beim Wechsel zur nächsten Datei erhalten** (als relativer
Bruchteil, nicht als Pixelwert - funktioniert daher auch bei unterschiedlich
großen Dateien): war z.B. die rechte untere Ecke einer Datei zu sehen, zeigt
die nächste Datei ebenfalls ihre rechte untere Ecke - praktisch, um beim
manuellen Vergleichen mehrerer Duplikate dieselbe Stelle im Blick zu
behalten. Der allererste Start ist echte 100 % oben links; „↺ Einpassen“
setzt jederzeit bewusst darauf zurück. Bei echten Kamerafotos
mit GPS-Daten erscheint zusätzlich eine Metadaten-Zeile mit einem Button
„🌐 Ort ermitteln“ - das ist die einzige Stelle in der App, die (nur auf
diesen Klick hin) eine Internetverbindung braucht.

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
dem Verschieben prüfen. Innerhalb einer Gruppe muss das für **jedes Paar**
gelten (nicht nur transitiv über eine Kette verbunden sein) - sonst könnten
z.B. bei „A ähnlich B“ und „B ähnlich C“ auch A und C in derselben Gruppe
landen, obwohl sie direkt verglichen gar nicht mehr ähnlich genug sind. Nur
Bilder, die nicht schon als exaktes Duplikat erkannt wurden, werden hierfür
verglichen (keine doppelten Gruppen).

## Projektstruktur

- `main.py` – Oberfläche (PySide6)
- `duplicate_engine.py` – Scan-/Hash-/Verschiebe-Logik, unabhängig von der Oberfläche
- `document_viewer.py` – Datei-Viewer (identisch zum Datei-Umbenenner)
- `translations.py` – Deutsch/Englisch-Texte der Oberfläche (`TEXTS`-Wörterbuch, vollständig migriert 07.09.2026); der Mechanismus selbst (`t()`/`set_language()`) liegt geteilt mit dem [file_renamer](../file_renamer) in `qt_app_kit.i18n`
- UI-Bausteine (`TitledFrame`, `InfoIcon`, …) sowie `file_ops.py`/`result_dialogs.py`/`i18n.py` kommen aus dem geteilten [`qt-app-kit`](../qt-app-kit)-Paket (Geschwister-Ordner, siehe „Starten“)
- `tests/` – automatisierte Tests für `duplicate_engine.py` (siehe unten)

## Tests ausführen

```bash
pip install -r requirements-dev.txt
pytest
```

Deckt bisher gezielt `duplicate_engine.py` ab (Verschieben/Rückgängig
machen, Ordner einlesen, exakter Duplikat-Vergleich, Ähnliche-Bilder-
Erkennung inkl. Hash-Cache) - die Oberfläche (`main.py`) hat noch keine
automatisierten Tests. Jeder Test isoliert sich selbst über einen
temporären Ordner (`tmp_path`) sowie ein umgeleitetes `LOG_FILE`, greift
also nicht in eine parallel laufende App oder deren echte
Verschiebe-Historie ein (siehe `tests/conftest.py`).
