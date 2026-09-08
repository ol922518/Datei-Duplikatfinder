"""
translations.py
----------------
Deutsch/Englisch-Texte der Oberfläche - siehe ROADMAP.md
"Sprachumschaltung Deutsch/Englisch" für Hintergrund und Architektur. Der
eigentliche Mechanismus (t()/set_language()/Sprache lesen) liegt geteilt mit
dem file_renamer in qt_app_kit.i18n; hier steht nur das TEXTS-Wörterbuch
dieser App - analog zu file_renamers eigenem translations.py.

Migriert (07.09.2026, vollständig in einem Zug, anders als beim
schrittweisen Vorgehen im file_renamer): document_viewer.py, main.py.
Die "viewer_*"-Schlüssel sind wortgleich aus file_renamers translations.py
übernommen, da der Viewer ursprünglich 1:1 von dort kopiert wurde und
dieselben Kern-Texte weiterhin verwendet.

Noch NICHT migriert (weiterhin fest auf Deutsch): duplicate_engine.py -
enthält aber ohnehin keine direkt sichtbaren UI-Texte (nur Rohdaten wie
Fehlermeldungen, die main.py in eigene, übersetzte Meldungen einbettet).

Schlüssel-Konvention: "<datei>_<beschreibung>", damit bei einem Fund per
Volltextsuche sofort klar ist, wo der Text verwendet wird.
"""

from __future__ import annotations

from qt_app_kit.i18n import Texts

TEXTS: Texts = {
    # -- Sprachumschalter (main.py) --------------------------------------
    "language_switch_button": {"de": "🌐 DE/EN", "en": "🌐 DE/EN"},
    "language_switch_tooltip": {
        "de": "Wechselt die Sprache der Oberfläche (wirkt erst nach einem Neustart der App).",
        "en": "Switches the interface language (takes effect only after restarting the app).",
    },
    "language_switch_restart_title": {"de": "Neustart nötig", "en": "Restart required"},
    "language_switch_restart_text": {
        "de": "Die Sprache wurde gespeichert und gilt ab dem nächsten Start der App.",
        "en": "The language has been saved and takes effect the next time the app starts.",
    },

    # -- document_viewer.py: Titel/Zoom-Leiste ----------------------------
    # (wortgleich aus file_renamer/translations.py übernommen)
    "viewer_title_default": {"de": "Vorschau", "en": "Preview"},
    "viewer_zoom_out_tooltip": {"de": "Verkleinert die Vorschau.", "en": "Shrinks the preview."},
    "viewer_zoom_in_tooltip": {"de": "Vergrößert die Vorschau.", "en": "Enlarges the preview."},
    "viewer_zoom_fit_button": {"de": "↺ Einpassen", "en": "↺ Fit"},
    "viewer_zoom_fit_tooltip": {
        "de": "Setzt den Zoom zurück, sodass die Vorschau wieder in den verfügbaren Platz passt.",
        "en": "Resets the zoom so the preview fits the available space again.",
    },
    "viewer_zoom_auto": {"de": "Auto", "en": "Auto"},

    # -- document_viewer.py: Foto-Metadaten-Zeile -------------------------
    "viewer_geocode_button": {"de": "🌐 Ort ermitteln", "en": "🌐 Look up location"},
    "viewer_geocode_tooltip": {
        "de": (
            "Fragt den Ortsnamen zu den GPS-Koordinaten dieses Fotos online bei "
            "OpenStreetMap ab (einzige Stelle in der App, die dafür Internet braucht - "
            "geschieht nur auf diesen Klick hin, nie automatisch). Danach über 'Vorschau "
            "aktualisieren' als Baustein {ort} nutzbar."
        ),
        "en": (
            "Looks up the place name for this photo's GPS coordinates online via "
            "OpenStreetMap (the only place in the app that needs internet for this - "
            "happens only on this click, never automatically). Afterwards usable as the "
            "{ort} building block via 'Refresh preview'."
        ),
    },
    "viewer_geocode_searching": {"de": "Suche…", "en": "Searching…"},
    "viewer_geocode_no_internet": {"de": "⚠ Kein Internet?", "en": "⚠ No internet?"},
    "viewer_geocode_not_found": {"de": "⚠ Kein Ort gefunden", "en": "⚠ No location found"},

    # -- document_viewer.py: Leer-/Hinweis-/Fehlertexte -------------------
    "viewer_empty_hint": {
        "de": "Zeile in der Tabelle auswählen, um eine Vorschau zu sehen.",
        "en": "Select a row in the table to see a preview.",
    },
    "viewer_file_not_found": {"de": "Datei nicht gefunden:\n{name}", "en": "File not found:\n{name}"},
    "viewer_pdf_open_failed": {
        "de": "PDF konnte nicht geöffnet werden:\n{name}",
        "en": "Could not open PDF:\n{name}",
    },
    "viewer_no_preview": {
        "de": "Keine Vorschau verfügbar für:\n{name}",
        "en": "No preview available for:\n{name}",
    },
    "viewer_read_failed": {
        "de": "Datei konnte nicht gelesen werden:\n{error}",
        "en": "Could not read file:\n{error}",
    },
    "viewer_docx_missing_package": {
        "de": "Keine Vorschau möglich: Paket 'python-docx' ist nicht installiert.",
        "en": "No preview possible: package 'python-docx' is not installed.",
    },
    "viewer_docx_read_failed": {
        "de": "Word-Datei konnte nicht gelesen werden:\n{error}",
        "en": "Could not read Word file:\n{error}",
    },
    "viewer_docx_empty": {"de": "(leeres Dokument)", "en": "(empty document)"},

    # -- document_viewer.py: Video --------------------------------------
    "viewer_video_play_tooltip": {"de": "Wiedergabe starten/pausieren.", "en": "Start/pause playback."},
    "viewer_video_error": {
        "de": "Video konnte nicht abgespielt werden:\n{name}\n{error}",
        "en": "Could not play video:\n{name}\n{error}",
    },

    # -- main.py: Fenster/Hilfetexte ---------------------------------------
    "main_window_title": {"de": "Datei-Duplikatfinder", "en": "File Duplicate Finder"},
    "main_recursive_help": {
        "de": (
            "Bezieht beim Scannen auch alle Unterordner der gewählten Quelle(n) mit ein - "
            "abschalten, um wirklich nur die Dateien direkt im gewählten Ordner zu "
            "vergleichen (ohne dessen Unterordner)."
        ),
        "en": (
            "Also includes all subfolders of the chosen source(s) when scanning - "
            "turn off to compare only the files directly in the chosen folder "
            "(without its subfolders)."
        ),
    },
    "main_compare_help_title": {"de": "Vergleichskriterium", "en": "Comparison criterion"},
    "main_compare_help": {
        "de": (
            "Zwei Dateien gelten als Duplikat, wenn sie exakt denselben Inhalt haben - "
            "geprüft über Dateigröße und einen SHA-256-Prüfsummen-Vergleich (nicht über "
            "den Dateinamen: 'Foto.jpg' und 'IMG_0231.jpg' mit identischem Inhalt werden "
            "erkannt). Innerhalb jeder Gruppe gilt die älteste Datei als Vorschlag fürs "
            "Original (Häkchen davor deshalb standardmäßig leer) - das lässt sich pro "
            "Datei per Häkchen anpassen."
        ),
        "en": (
            "Two files count as duplicates if they have exactly the same content - "
            "checked via file size and a SHA-256 checksum comparison (not via the "
            "file name: 'Foto.jpg' and 'IMG_0231.jpg' with identical content are "
            "detected). Within each group, the oldest file is the suggested original "
            "(its checkbox is therefore unchecked by default) - adjustable per file "
            "via its checkbox."
        ),
    },
    "main_target_folder_help_title": {"de": "Zielordner", "en": "Target folder"},
    "main_target_folder_help": {
        "de": (
            "Standardmäßig landet jede verschobene Datei im 'Duplikate'-Unterordner "
            "ihrer jeweiligen Quelle (Ordnerstruktur bleibt dabei erhalten). Über "
            "'Ändern…' lässt sich stattdessen ein einziger, zentraler Zielordner "
            "festlegen, in den dann alle verschobenen Duplikate wandern - egal aus "
            "welcher Quelle sie stammen. Die Einstellung wird gemerkt (auch über "
            "einen Neustart hinweg) und gilt für alle künftigen 'Verschieben'-"
            "Aktionen, bis sie über '↺ Standard' wieder zurückgesetzt wird."
        ),
        "en": (
            "By default, every moved file ends up in the 'Duplikate' subfolder of "
            "its respective source (folder structure is preserved). Via "
            "'Change…' you can instead set a single, central target folder that "
            "all moved duplicates go to - regardless of which source they came "
            "from. The setting is remembered (even across a restart) and applies "
            "to all future 'Move' actions until it's reset via '↺ Default'."
        ),
    },
    "main_similar_help_title": {"de": "Ähnliche Bilder", "en": "Similar images"},
    "main_similar_help": {
        "de": (
            "Findet zusätzlich Bilder, die sich zwar leicht unterscheiden (andere "
            "Auflösung, erneut komprimiert, minimal bearbeitet), aber ganz ähnlich "
            "aussehen - über einen Bildvergleich (Perceptual Hashing), nicht über "
            "exakte Prüfsummen. Kann daher auch mal Bilder als 'ähnlich' einstufen, "
            "die bei genauerem Hinsehen doch unterschiedlich sind - vor dem "
            "Verschieben bitte prüfen. Innerhalb jeder Gruppe gilt die größte Datei "
            "als Vorschlag (vermutlich beste Qualität). Braucht das Paket 'Pillow' "
            "(siehe requirements.txt) - ohne das Paket bleibt die Option wirkungslos."
        ),
        "en": (
            "Additionally finds images that differ slightly (different "
            "resolution, re-compressed, minimally edited) but look quite similar - "
            "via an image comparison (perceptual hashing), not exact checksums. "
            "May therefore sometimes classify images as 'similar' that turn out "
            "different on closer inspection - please check before moving. Within "
            "each group, the largest file is the suggested keeper (presumably best "
            "quality). Needs the 'Pillow' package (see requirements.txt) - without "
            "it the option has no effect."
        ),
    },
    "main_dropzone_default_text": {
        "de": "📂 Ordner (oder Dateien) hierher ziehen  –  oder hier klicken zum Auswählen",
        "en": "📂 Drag folders (or files) here  –  or click here to choose",
    },
    "main_dropzone_tooltip": {
        "de": "Ordner/Dateien hierher ziehen oder klicken, um sie über den Ordner-Auswahldialog zu laden.",
        "en": "Drag folders/files here or click to load them via the folder picker.",
    },
    "main_hint_text": {
        "de": (
            "Tipp: Häkchen markiert eine Datei zum Verschieben - je Gruppe ist die älteste "
            "Datei standardmäßig abgewählt (Original). Zeile auswählen zeigt die Datei in der "
            "Vorschau rechts. Verschobene Dateien landen im Unterordner 'Duplikate' der "
            "jeweiligen Quelle (oder im festgelegten Zielordner) und lassen sich per "
            "'Verschieben rückgängig machen' wiederherstellen."
        ),
        "en": (
            "Tip: The checkbox marks a file for moving - within each group, the oldest "
            "file is unchecked by default (original). Selecting a row shows the file in "
            "the preview on the right. Moved files end up in the 'Duplikate' subfolder of "
            "their respective source (or the configured target folder) and can be "
            "restored via 'Undo move'."
        ),
    },

    # -- main.py: untere Buttonzeile ----------------------------------------
    "main_move_button": {"de": "🗂 Ausgewählte in 'Duplikate'-Ordner verschieben", "en": "🗂 Move selected to 'Duplikate' folder"},
    "main_move_tooltip": {
        "de": "Verschiebt alle angehakten Dateien in einen 'Duplikate'-Unterordner ihrer jeweiligen Quelle.",
        "en": "Moves all checked files into a 'Duplikate' subfolder of their respective source.",
    },
    "main_undo_button": {"de": "↺ Verschieben rückgängig machen", "en": "↺ Undo move"},
    "main_undo_tooltip": {
        "de": "Macht die zuletzt durchgeführte Verschiebe-Aktion wieder rückgängig.",
        "en": "Undoes the most recently performed move action.",
    },
    "main_delete_checked_button": {"de": "🗑 Angehakte löschen", "en": "🗑 Delete checked"},
    "main_delete_checked_tooltip": {
        "de": (
            "Verschiebt alle angehakten Dateien in den Papierkorb - dieselbe "
            "Auswahl wie beim Verschieben-Button oben, nur als Löschen statt "
            "Verschieben."
        ),
        "en": (
            "Moves all checked files to the trash - the same selection as the "
            "Move button above, just deleting instead of moving."
        ),
    },
    "main_delete_unavailable_tooltip": {
        "de": "Nicht verfügbar - dafür fehlt das Paket 'send2trash' (siehe requirements.txt: pip install -r requirements.txt).",
        "en": "Not available - the package 'send2trash' is missing for this (see requirements.txt: pip install -r requirements.txt).",
    },

    # -- main.py: Quellordner-Bereich ----------------------------------------
    "main_source_frame_title": {"de": "Quellordner", "en": "Source folder"},
    "main_reset_source_tooltip": {
        "de": (
            "Setzt die aktuelle Quellauswahl zurück. Ist bereits nichts geladen, wird "
            "stattdessen der feste Standardordner (sofern festgelegt) erneut geladen."
        ),
        "en": (
            "Resets the current source selection. If nothing is loaded already, the "
            "fixed default folder (if set) is loaded again instead."
        ),
    },
    "main_set_default_tooltip": {
        "de": "Merkt sich den aktuell geladenen Ordner dauerhaft als Standard - wird künftig bei jedem App-Start automatisch geladen.",
        "en": "Remembers the currently loaded folder as the default - will be loaded automatically on every app start from now on.",
    },
    "main_clear_default_tooltip": {
        "de": "Entfernt den festgelegten Standardordner - beim nächsten Start wird kein Ordner mehr automatisch geladen.",
        "en": "Removes the configured default folder - no folder will be loaded automatically on the next start.",
    },
    "main_no_default_folder": {"de": "Kein Standardordner festgelegt", "en": "No default folder set"},

    # -- main.py: Optionen-Bereich -------------------------------------------
    "main_options_frame_title": {"de": "Optionen", "en": "Options"},
    "main_recursive_check": {"de": "Unterordner einbeziehen (rekursiv)", "en": "Include subfolders (recursive)"},
    "main_similar_check": {
        "de": "🖼️ Ähnliche Bilder zusätzlich erkennen (experimentell)",
        "en": "🖼️ Also detect similar images (experimental)",
    },
    "main_pillow_missing": {
        "de": "(Paket 'Pillow' fehlt - siehe requirements.txt)",
        "en": "(package 'Pillow' missing - see requirements.txt)",
    },
    "main_choose_target_button": {"de": "Ändern…", "en": "Change…"},
    "main_choose_target_tooltip": {
        "de": "Legt einen zentralen Ordner fest, in den alle verschobenen Duplikate landen - egal aus welcher Quelle.",
        "en": "Sets a central folder that all moved duplicates land in - regardless of source.",
    },
    "main_reset_target_button": {"de": "↺ Standard", "en": "↺ Default"},
    "main_reset_target_tooltip": {
        "de": "Zurück zum Standard: jede Datei landet im 'Duplikate'-Unterordner ihrer jeweiligen Quelle.",
        "en": "Back to default: every file ends up in the 'Duplikate' subfolder of its respective source.",
    },

    # -- main.py: Ergebnis-Bereich --------------------------------------------
    "main_result_frame_title": {"de": "Ergebnis", "en": "Result"},
    "main_scan_button": {"de": "🔍 Auf Duplikate prüfen", "en": "🔍 Check for duplicates"},
    "main_select_all_button": {"de": "☑ Alle auswählen", "en": "☑ Select all"},
    "main_select_all_tooltip": {
        "de": "Hakt alle gefundenen Duplikate an - sie werden dann beim Verschieben berücksichtigt.",
        "en": "Checks all found duplicates - they will then be included when moving.",
    },
    "main_select_none_button": {"de": "☐ Alle abwählen", "en": "☐ Select none"},
    "main_reset_check_button": {
        "de": "↺ Auswahl zurücksetzen (Original behalten)",
        "en": "↺ Reset selection (keep original)",
    },
    "main_reset_check_tooltip": {
        "de": "Stellt je Gruppe die Vorauswahl wieder her: älteste Datei abgewählt (Original), restliche angehakt.",
        "en": "Restores the default selection per group: oldest file unchecked (original), the rest checked.",
    },
    "main_col_name": {"de": "Datei", "en": "File"},
    "main_col_folder": {"de": "Ordner", "en": "Folder"},
    "main_col_size": {"de": "Größe", "en": "Size"},
    "main_col_modified": {"de": "Geändert am", "en": "Modified"},
    "main_delete_selected_button": {"de": "🗑 Markierte Zeilen löschen", "en": "🗑 Delete selected rows"},
    "main_delete_selected_tooltip": {
        "de": (
            "Verschiebt die im Baum markierten (angeklickten) Dateien in den "
            "Papierkorb - unabhängig vom Häkchen zum Verschieben. Mehrfachauswahl per "
            "Shift-Klick (zusammenhängend) oder Cmd-Klick (einzeln) möglich."
        ),
        "en": (
            "Moves the files selected (clicked) in the tree to the trash - independent "
            "of the move checkbox. Multi-selection via shift-click (contiguous) or "
            "cmd-click (individual) is possible."
        ),
    },
    "main_reveal_button": {"de": "📂 Ablageort öffnen", "en": "📂 Reveal in Finder"},
    "main_reveal_tooltip": {
        "de": "Öffnet den Finder am Ort der aktuell in der Vorschau gezeigten Datei (markiert sie dort).",
        "en": "Opens the Finder at the location of the file currently shown in the preview (selects it there).",
    },

    # -- main.py: Quellordner laden -------------------------------------------
    "main_choose_folder_dialog_title": {"de": "Ordner zum Prüfen auswählen", "en": "Select folder to check"},
    "main_no_unique_folder_title": {"de": "Kein eindeutiger Ordner", "en": "No unique folder"},
    "main_no_unique_folder_text": {
        "de": (
            "Bitte zuerst genau einen Ordner laden (nicht mehrere/gemischte Quellen), "
            "um ihn als Standard festzulegen."
        ),
        "en": (
            "Please load exactly one folder first (not several/mixed sources), "
            "in order to set it as the default."
        ),
    },
    "main_default_folder_saved_title": {"de": "Gespeichert", "en": "Saved"},
    "main_default_folder_saved_text": {
        "de": "'{folder}' wird künftig beim Start automatisch geladen.",
        "en": "'{folder}' will be loaded automatically on startup from now on.",
    },
    "main_summary_multiple_sources": {"de": "{count} Quellen ausgewählt", "en": "{count} sources selected"},

    # -- main.py: Zielordner-Auswahl ------------------------------------------
    "main_choose_target_dialog_title": {
        "de": "Zentralen Zielordner für Duplikate wählen",
        "en": "Select central target folder for duplicates",
    },
    "main_target_folder_set": {"de": "🗂 Zielordner: {folder}", "en": "🗂 Target folder: {folder}"},
    "main_target_folder_default": {
        "de": "🗂 Zielordner: 'Duplikate'-Unterordner je Quelle (Standard)",
        "en": "🗂 Target folder: 'Duplikate' subfolder per source (default)",
    },

    # -- main.py: Scan starten -------------------------------------------------
    "main_no_source_title": {"de": "Kein Quellordner", "en": "No source folder"},
    "main_no_source_text": {
        "de": "Bitte zuerst einen Ordner (oder Dateien) auswählen.",
        "en": "Please select a folder (or files) first.",
    },
    "main_missing_package_title": {"de": "Paket fehlt", "en": "Package missing"},
    "main_missing_package_text": {
        "de": (
            "Für 'Ähnliche Bilder erkennen' fehlt das Python-Paket 'Pillow' "
            "(siehe requirements.txt). Der Scan läuft ohne diese Option weiter."
        ),
        "en": (
            "The Python package 'Pillow' is missing for 'Detect similar images' "
            "(see requirements.txt). The scan continues without this option."
        ),
    },
    "main_scanning_status": {"de": "Durchsuche Quelle(n) …", "en": "Searching source(s) …"},

    # -- main.py: Scan-Fortschritt -----------------------------------------------
    "main_progress_partial": {"de": "Teil-Prüfsummen", "en": "Partial checksums"},
    "main_progress_full": {"de": "Volle Prüfsummen", "en": "Full checksums"},
    "main_progress_phash": {"de": "Bildvergleich", "en": "Image comparison"},
    "main_progress_with_total": {"de": "{label}: {done}/{total} …", "en": "{label}: {done}/{total} …"},
    "main_progress_no_total": {"de": "{label} …", "en": "{label} …"},

    # -- main.py: Scan fertig -----------------------------------------------------
    "main_scan_done_none": {"de": "Fertig - keine Duplikate gefunden.", "en": "Done - no duplicates found."},
    "main_count_exact": {"de": "{count} exakt", "en": "{count} exact"},
    "main_count_similar_suffix": {"de": ", {count} ähnlich", "en": ", {count} similar"},
    "main_scan_done_summary": {
        "de": "Fertig - {groups} Gruppe(n) ({breakdown}), {files} Datei(en), {wasted} einsparbar.",
        "en": "Done - {groups} group(s) ({breakdown}), {files} file(s), {wasted} to save.",
    },
    "main_scan_failed_status": {"de": "Fehler beim Scannen.", "en": "Error while scanning."},
    "main_no_access_title": {"de": "Kein Zugriff", "en": "No access"},
    "main_no_access_text": {
        "de": (
            "Beim Durchsuchen ist ein Fehler aufgetreten (evtl. fehlende Berechtigung "
            "unter Systemeinstellungen → Datenschutz & Sicherheit → "
            "Festplattenvollzugriff):\n\n{message}"
        ),
        "en": (
            "An error occurred while searching (possibly missing permission "
            "under System Settings → Privacy & Security → "
            "Full Disk Access):\n\n{message}"
        ),
    },
    "main_unexpected_error_title": {"de": "Unerwarteter Fehler", "en": "Unexpected error"},
    "main_unexpected_error_text": {
        "de": (
            "Es ist ein unerwarteter Fehler aufgetreten:\n\n{message}\n\n"
            "Der vollständige technische Fehlerbericht wird zusätzlich in "
            "'.app_launch.log' im Projektordner protokolliert, sofern die Datei "
            "beschreibbar ist."
        ),
        "en": (
            "An unexpected error occurred:\n\n{message}\n\n"
            "The full technical error report is additionally logged to "
            "'.app_launch.log' in the project folder, provided that file is "
            "writable."
        ),
    },

    # -- main.py: Ergebnis-Baum (Gruppen-Label/Badges) ------------------------
    "main_similar_group_label": {"de": "🖼️ Ähnliche Bilder {index} — {count} Dateien", "en": "🖼️ Similar images {index} — {count} files"},
    "main_similarity_suffix": {"de": " — ~{percent}% ähnlich", "en": " — ~{percent}% similar"},
    "main_wasted_suffix": {"de": " — {wasted} einsparbar", "en": " — {wasted} to save"},
    "main_exact_group_label": {"de": "Gruppe {index} — {count} Dateien", "en": "Group {index} — {count} files"},
    "main_original_tooltip_similar": {
        "de": "Wird als beste Qualität vorgeschlagen (größte Datei der Gruppe) - abwählbar/anders wählbar.",
        "en": "Suggested as the best quality (largest file in the group) - can be unchecked/changed.",
    },
    "main_original_badge_similar": {"de": "🖼️ Beste Qualität  ", "en": "🖼️ Best quality  "},
    "main_original_tooltip_exact": {
        "de": "Wird als Original vorgeschlagen (älteste Datei der Gruppe) - abwählbar/anders wählbar.",
        "en": "Suggested as the original (oldest file in the group) - can be unchecked/changed.",
    },
    "main_original_badge_exact": {"de": "🟢 Original  ", "en": "🟢 Original  "},

    # -- main.py: Ablageort öffnen ---------------------------------------------
    "main_no_selection_title": {"de": "Keine Auswahl", "en": "No selection"},
    "main_reveal_no_selection_text": {
        "de": "Bitte zuerst eine Datei im Baum auswählen.",
        "en": "Please select a file in the tree first.",
    },
    "main_not_found_title": {"de": "Nicht gefunden", "en": "Not found"},
    "main_not_found_text": {"de": "'{name}' existiert nicht mehr.", "en": "'{name}' no longer exists."},

    # -- main.py: Verschieben ------------------------------------------------
    "main_default_destination": {
        "de": "den jeweiligen 'Duplikate'-Unterordner",
        "en": "the respective 'Duplikate' subfolder",
    },
    "main_confirm_move_title": {"de": "Duplikate verschieben", "en": "Move duplicates"},
    "main_confirm_move_text": {
        "de": "{count} Datei(en) ({size}) nach {destination} verschieben?",
        "en": "Move {count} file(s) ({size}) to {destination}?",
    },
    "main_verb_moved": {"de": "verschoben", "en": "moved"},
    "main_move_success_status": {"de": "{count} Datei(en) verschoben.", "en": "{count} file(s) moved."},
    "main_undo_log_warning_title": {"de": "Rückgängig eingeschränkt", "en": "Undo limited"},

    # -- main.py: Rückgängig machen -------------------------------------------
    "main_verb_restored": {"de": "wiederhergestellt", "en": "restored"},

    # -- main.py: Markierte/Angehakte Zeilen löschen --------------------------
    "main_no_selection_text": {
        "de": (
            "Bitte zuerst eine oder mehrere Zeilen im Baum markieren "
            "(anklicken, mit Shift/Cmd für mehrere)."
        ),
        "en": (
            "Please select one or more rows in the tree first "
            "(click, with shift/cmd for multiple)."
        ),
    },
    "main_more_files_suffix": {"de": "\n… und {count} weitere", "en": "\n… and {count} more"},
    "main_confirm_trash_title": {"de": "In den Papierkorb verschieben", "en": "Move to trash"},
    "main_confirm_trash_text": {
        "de": "{count} Datei(en) werden in den Papierkorb verschoben:\n\n{names}\n\nFortfahren?",
        "en": "{count} file(s) will be moved to the trash:\n\n{names}\n\nContinue?",
    },
    "main_confirm_trash_checked_text": {
        "de": "{count} angehakte Datei(en) werden in den Papierkorb verschoben:\n\n{names}\n\nFortfahren?",
        "en": "{count} checked file(s) will be moved to the trash:\n\n{names}\n\nContinue?",
    },
    "main_verb_trashed": {"de": "in den Papierkorb verschoben", "en": "moved to the trash"},
}
