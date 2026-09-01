# Roadmap

## Für morgen (2026-09-02)

- **App-Bundle: zweiter Start soll bestehendes Fenster hervorholen statt
  nichts zu tun.** Aktuell: läuft die App bereits und man doppelklickt
  erneut auf die `.app`, hüpft das Dock-Icon kurz, ohne dass etwas
  passiert (kein neues Fenster, bestehendes wird nicht in den
  Vordergrund geholt). Lösung: `<key>LSMultipleInstancesProhibited</key>
  <true/>` in `Datei-Duplikatfinder.app/Contents/Info.plist` ergänzen -
  ein macOS-Bordmittel, das LaunchServices genau dafür anweist, keinen
  zweiten Prozess zu starten, sondern stattdessen die laufende Instanz zu
  aktivieren/nach vorne zu holen. Kein eigener IPC-Code nötig. Setzt
  voraus, dass das App-Bundle wieder existiert (siehe Punkt zum
  Terminal-freien Start unten, aktuell zurückgestellt) - beide Punkte
  hängen also zusammen und sollten zusammen angegangen werden.
- **Bug: Häkchen im Ergebnisbereich unsichtbar.** Die An-/Abwähl-Häkchen
  in der ersten Spalte der Ergebnis-Tabelle werden aktuell nicht
  dargestellt (evtl. eine Nebenwirkung von `app.setStyle("Fusion")` +
  der Dark-Palette - Fusion-Checkboxen brauchen teils zusätzliche
  Palette-Rollen/Icons, um sichtbar zu bleiben; zu prüfen auch im
  hellen Modus). Muss vor der nächsten Verschieben-Aktion behoben
  werden, da die Auswahl sonst nicht mehr nachvollziehbar ist.
- **Direktes Löschen statt Verschieben**: technisch problemlos machbar
  (z.B. `Path.unlink()` statt `shutil.move()` in
  `move_to_duplicates_folder()`/eine neue Schwesterfunktion). Als
  zusätzliche, explizit zu bestätigende Option neben dem heutigen
  (sicheren) Verschieben - ausgewählte Dateien würden dann direkt in
  ihrem jeweiligen Quellordner gelöscht statt in „Duplikate“/den
  Zielordner verschoben. Empfehlung fürs Gespräch morgen: über den
  macOS-Papierkorb löschen (wiederherstellbar) statt endgültig, damit
  die App ihre bisherige "nichts geht verloren"-Linie beibehält - dafür
  bräuchte es entweder ein Zusatzpaket (z.B. `send2trash`) oder einen
  AppleScript-/`NSWorkspace`-Aufruf wie beim App-Icon-Setzen.
- **Ähnliche Dokumente erkennen**: Textinhalt-Vergleich (z.B. Shingling)
  für Word/PDF - findet z.B. zwei Fassungen desselben Textes mit kleinen
  Änderungen.
- **Ausschlussmuster**: bestimmte Dateitypen/Ordnernamen (z.B.
  `node_modules`, `.git`) von der Suche ausschließen können.
- **Mehrere Standardordner**: aktuell lässt sich nur ein einzelner Ordner
  als fester Standard speichern (wie beim Datei-Umbenenner) - später
  evtl. eine Liste mehrerer fester Quellen.
- **Sprachumschaltung Deutsch/Englisch**: alle Texte (Buttons, Tooltips,
  Hilfetexte, Meldungen) auch auf Englisch, mit Umschalter für den Nutzer.
  Technisch gut machbar, aber aufwändig, da aktuell jeder Text fest im Code
  steht - am ehesten über ein einfaches eigenes Wörterbuch (`translations.py`
  mit `t("schlüssel")`-Funktion statt Qt-eigener `.ts`/`.qm`-Infrastruktur,
  die zusätzliches Werkzeug bräuchte). Sprachwechsel würde vermutlich erst
  nach Neustart greifen (wie der Standardordner gespeichert), da alle Texte
  live neu zu setzen deutlich aufwändiger wäre.
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
