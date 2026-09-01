# Roadmap

Ideen für spätere Erweiterungen, nicht in der aktuellen Version enthalten:

- **Ähnliche Dokumente erkennen**: Textinhalt-Vergleich (z.B. Shingling)
  für Word/PDF - findet z.B. zwei Fassungen desselben Textes mit kleinen
  Änderungen.
- **Direktes Löschen statt Verschieben**: als zusätzliche, explizit zu
  bestätigende Option neben dem heutigen (sicheren) Verschieben in den
  „Duplikate“-Ordner.
- **Zielordner frei wählbar**: statt immer `Duplikate` als Unterordner der
  jeweiligen Quelle, wahlweise ein zentraler, frei wählbarer Zielordner
  für alle gefundenen Duplikate.
- **Ausschlussmuster**: bestimmte Dateitypen/Ordnernamen (z.B.
  `node_modules`, `.git`) von der Suche ausschließen können.
- **Datei-Vorschau**: kleiner eingebauter Viewer wie im Datei-Umbenenner,
  um Duplikate vor dem Verschieben anzusehen (v.a. bei Bildern hilfreich).
- **Mehrere Standardordner**: aktuell lässt sich nur ein einzelner Ordner
  als fester Standard speichern (wie beim Datei-Umbenenner) - später
  evtl. eine Liste mehrerer fester Quellen.
- **Terminal-freier Start ohne grauen Icon-Rand**: ein Versuch mit einem
  von Hand gebauten `.app`-Bundle (Info.plist + Launcher-Skript) zeigte
  bei mehreren Icon-Varianten und selbst nach Ad-hoc-Signierung weiterhin
  einen leichten grauen Rand um das Icon (vermutlich behandelt macOS
  unsignierte/nicht über Xcode gebaute App-Bundles beim Icon-Rendering
  grundsätzlich anders als normale Dateien mit eigenem Finder-Icon - dort
  klappt es einwandfrei, siehe `App öffnen.command`). Zurückgestellt -
  „App öffnen.command“ bleibt der empfohlene Startweg. Für später denkbar:
  richtige Code-Signierung mit Apple Developer ID, oder Apples neues
  Icon-Composer-Format (Xcode 16+) statt eines einfachen `.icns`.
