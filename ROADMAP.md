# Roadmap

Sammlung von Ideen und offenen Punkten für künftige Sitzungen. Diese
Liste ist offen und wird laufend ergänzt/aufgeräumt.

## Terminal-freier Start ohne grauen Icon-Rand (Stand 07.09.2026: neuer Versuch, Bestätigung ausstehend)

Ein früherer Versuch mit einem von Hand gebauten `.app`-Bundle
(Info.plist + Launcher-Skript) zeigte bei mehreren Icon-Varianten und
selbst nach Ad-hoc-Signierung einen leichten grauen Rand um das Icon -
deshalb zurückgestellt, „App öffnen.command“ blieb der Startweg.

**Korrektur einer früheren (falschen) Notiz hier:** zuvor stand an
dieser Stelle, der gleiche Ansatz habe beim Geschwisterprojekt
[Dateien-Recycler](../Dateien-Recycler) "auf Anhieb sauber" funktioniert
- das stimmt laut dortiger Commit-Nachricht (`f37265c`) nicht: der graue
Rand trat dort ebenfalls auf, der Nutzer hat ihn manuell selbst behoben
(vermutlich über Finder → Informationen → Icon kopieren/einfügen).
Kein reiner Icon-Cache-Zufall also, sondern ein wiederkehrendes Muster
bei selbstgebauten, unsignierten Bundles.

**Neuer Ansatz (07.09.2026):** genau diesen manuellen Finder-Trick jetzt
automatisiert nachgebaut, statt sich nur auf `CFBundleIconFile` im
Info.plist zu verlassen (das war schon immer die vermutete Fehlerquelle
für den Rand). `Datei-Duplikatfinder.app` existiert wieder (Info.plist +
Launcher-Skript, gleiche Struktur wie beim Dateien-Recycler, frische
Bundle-ID `build.fim.datei-duplikatfinder-2`), zusätzlich wurde das Icon
per `NSWorkspace.setIcon_forFile_options_()` direkt auf den Bundle-Ordner
gesetzt - derselbe Mechanismus, mit dem „App öffnen.command“ schon immer
sein sauberes Icon bekommt (Finder-eigenes „Benutzerdefiniertes Symbol“,
technisch eine versteckte `Icon`-Datei + `com.apple.FinderInfo`-Attribut,
komplett unabhängig vom `CFBundleIconFile`-Rendering). `GetFileInfo`
bestätigt das gesetzte Custom-Icon-Flag; Icon-Cache geleert, Dock/Finder
neu gestartet. **Noch nicht visuell im Finder bestätigt** - nächster
Schritt: Nutzer prüft, ob der graue Rand jetzt wirklich weg ist.

## App-Bundle: zweiter Start holt bestehendes Fenster hervor ✅ (07.09.2026)

Vorher: lief die App bereits und man doppelklickte erneut auf die
`.app`, hüpfte das Dock-Icon kurz, ohne dass etwas passierte. Behoben
über `<key>LSMultipleInstancesProhibited</key><true/>` in
`Datei-Duplikatfinder.app/Contents/Info.plist` - ein macOS-Bordmittel,
das LaunchServices anweist, keinen zweiten Prozess zu starten, sondern
die laufende Instanz zu aktivieren. Getestet: zweiter `open`-Aufruf
startete keinen neuen Prozess (Prozesszahl blieb bei 1).

## Ähnliche Dokumente erkennen (Textinhalt-Vergleich)

Analog zur bereits vorhandenen „Ähnliche Bilder“-Erkennung (Perceptual
Hashing), aber für Text: Word-/PDF-Dokumente mit stark ähnlichem, aber
nicht identischem Inhalt finden (z.B. zwei Fassungen desselben Textes
mit kleinen Änderungen) - über einen Textinhalt-Vergleich wie Shingling
(überlappende Wort-n-Gramme + Ähnlichkeitsmaß, ähnlich der
dHash-Idee bei Bildern). Noch nicht begonnen.

## Ausschlussmuster für die Suche

Bestimmte Ordnernamen (z.B. `node_modules`) oder Dateitypen von der
Suche ausschließen können.

**Teilweise bereits abgedeckt:** versteckte Ordner (z.B. `.git`) werden
schon automatisch übersprungen, sofern „versteckte Dateien einbeziehen“
nicht aktiv ist (siehe `list_files()` in
[duplicate_engine.py](duplicate_engine.py) - prüft alle Pfadteile, nicht
nur den Dateinamen). Offen ist noch ein **frei konfigurierbares**
Ausschlussmuster für nicht-versteckte, aber unerwünschte Ordnernamen wie
`node_modules` sowie für Dateiendungen.

## Mehrere Standardordner

Aktuell lässt sich nur ein einzelner Ordner als fester Standard
speichern (wie beim Datei-Umbenenner) - später evtl. eine Liste
mehrerer fester Quellen.

## Sprachumschaltung Deutsch/Englisch

Alle Texte (Buttons, Tooltips, Hilfetexte, Meldungen) auch auf Englisch,
mit Umschalter für den Nutzer. Technisch gut machbar, aber aufwändig, da
aktuell jeder Text fest im Code steht - am ehesten über ein einfaches
eigenes Wörterbuch (`translations.py` mit `t("schlüssel")`-Funktion
statt Qt-eigener `.ts`/`.qm`-Infrastruktur, die zusätzliches Werkzeug
bräuchte). Sprachwechsel würde vermutlich erst nach Neustart greifen
(wie der Standardordner gespeichert), da alle Texte live neu zu setzen
deutlich aufwändiger wäre.

Der [file_renamer](../file_renamer) steht vor demselben Bedarf (dort
bereits mit Architektur-Entscheidung und Grundgerüst-Plan in dessen
eigener ROADMAP.md) - da beide Projekte dieselbe Qt-Basis
([qt-app-kit](../qt-app-kit)) teilen, könnte der eigentliche
Übersetzungs-Mechanismus (nicht die Texte selbst) als gemeinsames,
wiederverwendbares Stück gebaut werden.

## O(n²)-Grenze bei „Ähnliche Bilder“ (nur bei sehr großen Sammlungen relevant)

Der paarweise Ähnlichkeitsvergleich in `scan_for_similar_images()`
vergleicht aktuell jedes Bildpaar einzeln (`O(n²)`) - laut Benchmark
(07.09.2026) bei 10.000 Bildern rund 7s, bei 50.000 Bildern
hochgerechnet rund 3 Minuten für diesen Schritt allein. Läuft im
Hintergrund-Thread (blockiert die Oberfläche nicht), wird aber ab
mehreren zehntausend Bildern spürbar langsam. Aktuell kein akuter
Bedarf - falls doch relevant: Vor-Bucketing nach Hash-Präfix (ähnlich
Locality-Sensitive-Hashing) würde die Anzahl nötiger Vergleiche deutlich
reduzieren, analog zum bereits gestuften Vorgehen bei exakten
Duplikaten (Größe → Teil-Hash → voller Hash).

**Priorität: niedrig** - reine Beobachtung, kein gemeldetes Problem.
