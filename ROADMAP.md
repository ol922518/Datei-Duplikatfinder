# Roadmap

Sammlung von Ideen und offenen Punkten für künftige Sitzungen. Diese
Liste ist offen und wird laufend ergänzt/aufgeräumt.

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
