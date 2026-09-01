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
3. **„🔍 Auf Duplikate prüfen“** – durchsucht die Quelle(n) in einem
   Hintergrund-Thread (die Oberfläche bleibt währenddessen bedienbar) und
   zeigt den Fortschritt an.
4. **Ergebnis** – je gefundene Duplikat-Gruppe eine Zeile mit Anzahl
   Dateien und einsparbarem Speicherplatz, darunter aufgeklappt die
   einzelnen Dateien mit Pfad, Größe und Änderungsdatum. Die **älteste
   Datei** je Gruppe ist mit „🟢 Original“ markiert und ihr Häkchen
   standardmäßig **nicht** gesetzt – alle anderen Dateien der Gruppe sind
   angehakt. Über **„☑ Alle auswählen“**/„☐ Alle abwählen“ lässt sich das
   für alle Zeilen auf einmal umschalten, **„↺ Auswahl zurücksetzen“**
   stellt die ursprüngliche Vorauswahl (älteste Datei = Original) wieder
   her.
5. **„🗂 Ausgewählte in 'Duplikate'-Ordner verschieben“** – verschiebt alle
   angehakten Dateien in einen Unterordner `Duplikate` der jeweiligen
   Quelle (die Ordnerstruktur darunter bleibt erhalten). Nichts wird
   gelöscht. **„↺ Verschieben rückgängig machen“** macht die zuletzt
   durchgeführte Aktion wieder vollständig rückgängig.

## Vergleichskriterium

Zwei Dateien gelten als Duplikat, wenn sie **exakt denselben Inhalt**
haben - unabhängig vom Dateinamen. Geprüft wird gestuft, um bei vielen/
großen Dateien nicht unnötig viel lesen zu müssen:

1. **Dateigröße** – schnellster erster Filter.
2. **Teil-Prüfsumme** (erste 64 KB) – filtert die meisten restlichen
   Nicht-Duplikate heraus, ohne die ganze Datei zu lesen.
3. **Volle Prüfsumme** (SHA-256) – nur noch für die verbliebenen
   Kandidaten berechnet, das ist die verlässliche Bestätigung.

0-Byte-Dateien werden ignoriert. Ähnliche, aber nicht bit-identische
Dateien (z.B. dasselbe Foto in anderer Auflösung/Kompression) werden
aktuell **nicht** erkannt – siehe [ROADMAP.md](ROADMAP.md).

## Projektstruktur

- `main.py` – Oberfläche (PySide6)
- `duplicate_engine.py` – Scan-/Hash-/Verschiebe-Logik, unabhängig von der Oberfläche
- `qt_widgets.py` – wiederverwendbare UI-Bausteine (identisch zum Datei-Umbenenner)
