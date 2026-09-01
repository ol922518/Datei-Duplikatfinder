# Roadmap

Ideen für spätere Erweiterungen, nicht in der aktuellen Version enthalten:

- **Ähnliche Bilder erkennen (Near-Duplicates)**: Perceptual Hashing
  (pHash/dHash) zusätzlich zum exakten SHA-256-Vergleich, um z.B.
  verkleinerte oder neu komprimierte Kopien eines Fotos zu finden.
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
